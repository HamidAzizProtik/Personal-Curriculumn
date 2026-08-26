from enum import Enum


class Phase(Enum):
    PROBE = "PROBE"      # prerequisite calibration via structured probes
    PLAN = "PLAN"        # build the lesson DAG (generate_mermaid_dag)
    TEACH = "TEACH"      # walk the DAG node-by-node with verification
    COMPLETE = "COMPLETE"


# Minimum PROBE thoroughness. The harness refuses to leave PROBE until the
# model has assessed enough DISTINCT prerequisite strands with enough quizzes,
# so calibration is real and the planner has an exact boundary to work from.
MIN_PROBE_STRANDS = 4
MIN_PROBE_QUIZZES = 6
# Ceilings so PROBE can never drag on forever. Breadth (distinct strands) is
# still enforced via the minimums above; these just cap total volume so the
# student isn't quizzed into oblivion.
MAX_PROBE_QUIZZES = 14        # hard stop for the whole PROBE phase
MAX_PROBES_PER_STRAND = 4     # depth ceiling: bounds the binary-search per strand

# Gate tools that advance the machine. Forward tools are blocked until the
# matching gate passes, so the model physically cannot wing it / skip ahead.
GATE_TOOLS = {"complete_probe", "complete_plan", "complete_node"}

# Tools permitted in each phase. Any tool not listed for the current phase is
# BLOCKED and the model receives an error function response forcing compliance.
_PHASE_TOOLS = {
    Phase.PROBE: {
        "probe_prerequisite", "log_to_obsidian", "research_topic",
        "record_source", "record_calibration", "complete_probe",
    },
    Phase.PLAN: {
        "generate_mermaid_dag", "log_to_obsidian", "research_topic",
        "record_source", "ask_quiz", "practice_problem", "record_calibration",
        "complete_plan",
    },
    Phase.TEACH: {
        "ask_quiz", "log_to_obsidian", "research_topic",
        "record_source", "generate_diagram", "generate_mermaid_dag",
        "practice_problem", "record_calibration", "complete_node",
    },
}


class PhaseMachine:
    """A hard, orchestrator-side state machine for the tutor.

    Enforcement (not just prompting):
      * PROBE -> PLAN -> TEACH ordering is gate-guarded.
      * PROBE has a minimum depth (distinct strands + total quizzes).
      * PLAN requires a fact-check (`research_topic`) before `complete_plan`.
      * TEACH is strictly one node at a time: after a node's quiz PASSES, the
        model MUST call `complete_node()` before it may introduce the next
        node's material; each node also requires a `research_topic` verification
        before it can be completed (constant verification).
    """

    def __init__(self):
        self.phase = Phase.PROBE
        self.probe_quiz_count = 0
        self.probe_strands = set()
        self.dag_generated = False
        self.plan_researched = False
        self.node_index = 0
        self.node_passed = False       # last node-verification quiz result
        self.node_researched = False   # research done for the current node
        self.probe_strand_counts = {}  # strand -> number of times probed
        self.probe_budget_exhausted = False  # True once MAX_PROBE_QUIZZES hit

    # --- gate transitions -------------------------------------------------
    def complete_probe(self, learner=None) -> str:
        if self.phase != Phase.PROBE:
            return (f"BLOCKED: complete_probe is only valid in the PROBE phase. "
                    f"Current phase is {self.phase.value}.")
        # Minimums met, OR the hard budget cap was reached (forced stop so the
        # session can never hang inside PROBE). Breadth is guaranteed by the
        # MIN_PROBE_STRANDS floor; depth by per-strand binary search.
        mins_met = (len(self.probe_strands) >= MIN_PROBE_STRANDS
                    and self.probe_quiz_count >= MIN_PROBE_QUIZZES)
        if not (mins_met or self.probe_budget_exhausted):
            return (f"BLOCKED: PROBE must be thorough. Assessed "
                    f"{len(self.probe_strands)} strands / {self.probe_quiz_count} "
                    f"quizzes; minimum required: {MIN_PROBE_STRANDS} distinct "
                    f"strands and {MIN_PROBE_QUIZZES} quizzes (ceiling "
                    f"{MAX_PROBE_QUIZZES}). Cover the breadth of the topic, then "
                    f"call complete_probe.")
        if learner is not None:
            learner.derive_calibration()
        self.phase = Phase.PLAN
        cap_note = (" (ended at probe budget cap; calibration may be partial — "
                    "later sessions will deepen it)") if self.probe_budget_exhausted else ""
        return ("PROBE phase complete" + cap_note + ". Phase is now PLAN. You MAY "
                "now call `generate_mermaid_dag` to build the lesson DAG (and you "
                "MUST call `research_topic` to fact-check it before "
                "`complete_plan`).")

    def complete_plan(self) -> str:
        if self.phase != Phase.PLAN:
            return (f"BLOCKED: complete_plan is only valid in the PLAN phase. "
                    f"Current phase is {self.phase.value}.")
        if not self.dag_generated:
            return ("BLOCKED: you must call `generate_mermaid_dag` and log the "
                    "resulting DAG before completing PLAN.")
        if not self.plan_researched:
            return ("BLOCKED: you must call `research_topic` to fact-check and "
                    "verify the plan before `complete_plan` (constant "
                    "verification).")
        self.phase = Phase.TEACH
        self.node_index = 1
        self.node_passed = False
        self.node_researched = False
        return ("PLAN phase complete. Phase is now TEACH, starting at node 1. "
                "Teach ONE node at a time: explain it (log_to_obsidian), "
                "optionally `generate_diagram`, verify with `ask_quiz`, then call "
                "`complete_node()` before moving to the next node. Each node "
                "requires a `research_topic` verification before completion.")

    def complete_node(self) -> str:
        if self.phase != Phase.TEACH:
            return (f"BLOCKED: complete_node is only valid in the TEACH phase. "
                    f"Current phase is {self.phase.value}.")
        if not self.node_passed:
            return ("BLOCKED: you can only call `complete_node()` after the "
                    "current node's verification quiz is PASSED. Re-teach and "
                    "re-quiz until the student passes.")
        if not self.node_researched:
            return ("BLOCKED: you must call `research_topic` to verify this "
                    "node's claims before completing it (constant verification).")
        finished = self.node_index
        self.node_index += 1
        self.node_passed = False
        self.node_researched = False
        return (f"Node {finished} complete. Now teaching node {self.node_index}. "
                "Explain it, optionally `generate_diagram`, verify with "
                "`ask_quiz`, then `complete_node()` again before the next node.")

    # --- signals from the orchestrator -----------------------------------
    def mark_probe_call(self, strand: str):
        if self.phase == Phase.PROBE:
            self.probe_quiz_count += 1
            if strand:
                self.probe_strands.add(strand)
                self.probe_strand_counts[strand] = (
                    self.probe_strand_counts.get(strand, 0) + 1)
            if self.probe_quiz_count >= MAX_PROBE_QUIZZES:
                self.probe_budget_exhausted = True

    def mark_researched(self):
        if self.phase == Phase.PLAN:
            self.plan_researched = True
        elif self.phase == Phase.TEACH:
            self.node_researched = True

    def mark_dag_generated(self):
        self.dag_generated = True

    def record_quiz_outcome(self, correct: bool):
        if self.phase == Phase.TEACH:
            # A node-verification quiz result: pass unlocks complete_node,
            # fail re-locks the node until the student passes a retry.
            self.node_passed = correct

    # --- enforcement ------------------------------------------------------
    def can_execute(self, tool_name: str, args: dict = None):
        """Return (allowed, message). If not allowed, `message` is a BLOCKED
        notice the orchestrator returns as the tool's function response,
        forcing the model back into the phase contract."""
        if tool_name == "probe_prerequisite":
            if self.probe_budget_exhausted:
                return False, (
                    f"BLOCKED: PROBE budget exhausted "
                    f"({MAX_PROBE_QUIZZES} quizzes / {MAX_PROBES_PER_STRAND} per "
                    f"strand). Call `complete_probe` now to advance to PLAN.")
            strand = (args or {}).get("prerequisite") if args else None
            if strand and self.probe_strand_counts.get(strand, 0) >= MAX_PROBES_PER_STRAND:
                return False, (
                    f"BLOCKED: strand '{strand}' has already been probed "
                    f"{MAX_PROBES_PER_STRAND} times (binary-search ceiling). "
                    f"Probe a NEW distinct strand for breadth, or call "
                    f"`complete_probe`.")
        if tool_name in GATE_TOOLS:
            return True, ""

        allowed_set = _PHASE_TOOLS.get(self.phase, set())
        if tool_name not in allowed_set:
            return False, (
                f"BLOCKED: tool `{tool_name}` is not permitted in the "
                f"{self.phase.value} phase. Follow the phase contract: "
                f"PROBE (probe_prerequisite on every strand) -> complete_probe "
                f"-> PLAN (generate_mermaid_dag + research_topic) -> "
                f"complete_plan -> TEACH (one node at a time, complete_node)."
            )

        if self.phase == Phase.TEACH:
            # Once a node's quiz passes, no NEW material may appear until the
            # node is formally closed with complete_node. This is what stops
            # the model from dumping the whole lesson at once.
            if tool_name in ("log_to_obsidian", "generate_diagram") and self.node_passed:
                return False, (
                    "BLOCKED: the current node's verification quiz PASSED, but "
                    "you must call `complete_node()` before introducing the next "
                    "node's material. Teach one node at a time."
                )

        return True, ""


def build_phase_tools(pm: PhaseMachine, learner=None):
    """Build the gate tool functions bound to a PhaseMachine instance."""

    def complete_probe() -> str:
        """End the PROBE phase. Call ONLY after probing enough distinct prerequisite strands (harness enforces minimum depth + caps). Calibration auto-derives from results."""
        return pm.complete_probe(learner)

    def complete_plan() -> str:
        """End the PLAN phase. Call ONLY after `generate_mermaid_dag` (logged) + a `research_topic` fact-check. Teaching is blocked until this passes."""
        return pm.complete_plan()

    def complete_node() -> str:
        """Close the current node. Call ONLY after its `ask_quiz` PASSED and its claims were verified with `research_topic`. Unlocks the next node (one-at-a-time)."""
        return pm.complete_node()

    return [complete_probe, complete_plan, complete_node]
