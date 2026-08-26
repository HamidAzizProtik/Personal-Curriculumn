import os
import json
import time

_PROFILE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "learner_profile.json",
)


class LearnerModel:
    """A persistent, cross-session model of the student for a given topic.

    Stored as JSON on disk (one file, keyed by topic) so calibration and quiz
    performance survive between runs. The model is loaded at session start and
    injected into the system prompt so the tutor does NOT start cold every time.

    Calibration is auto-derived from structured `probe_prerequisite` results,
    giving an EXACT map of which named prerequisites are known vs missing.
    """

    def __init__(self, topic: str, record: dict = None):
        self.topic = topic
        self.data = record or self._blank(topic)
        self._store = {"topics": {}}

    @staticmethod
    def _blank(topic: str) -> dict:
        return {
            "topic": topic,
            "created": time.time(),
            "updated": time.time(),
            "sessions": 0,
            "calibration": {
                "probed": False,
                "estimated_level": None,
                "known_prerequisites": [],
                "knowledge_gaps": [],
            },
            "plan": {"dag": None, "planned": False},
            "probe_results": [],   # {prerequisite, correct, question, ts}
            "mastered_nodes": [],
            "quiz_history": [],    # {area, correct, ts}
        }

    @classmethod
    def load(cls, topic: str) -> "LearnerModel":
        store = {}
        if os.path.exists(_PROFILE_FILE):
            try:
                with open(_PROFILE_FILE, "r", encoding="utf-8") as f:
                    store = json.load(f)
            except Exception:
                store = {}
        topics = store.get("topics", {})
        rec = topics.get(topic) or topics.get(topic.lower())
        inst = cls(topic, rec)
        inst._store = store if isinstance(store, dict) else {"topics": {}}
        return inst

    # --- mutators ---------------------------------------------------------
    def record_session_start(self):
        self.data["sessions"] = self.data.get("sessions", 0) + 1

    def record_probe_result(self, prerequisite: str, correct: bool, question: str = "", difficulty: str = "medium"):
        """Record a structured PROBE result tied to a named prerequisite."""
        self.data.setdefault("probe_results", []).append({
            "prerequisite": prerequisite,
            "correct": correct,
            "question": question,
            "difficulty": difficulty,
            "ts": time.time(),
        })
        self.data.setdefault("quiz_history", []).append({
            "area": prerequisite,
            "correct": correct,
            "ts": time.time(),
        })

    def derive_calibration(self):
        """Auto-derive exact known/gap prerequisites from probe results."""
        results = self.data.get("probe_results", [])
        if not results:
            return
        known, gaps = [], []
        seen_k, seen_g = set(), set()
        for r in results:
            p = (r.get("prerequisite") or "").strip()
            if r.get("correct"):
                if p and p not in seen_k:
                    known.append(p)
                    seen_k.add(p)
            else:
                if p and p not in seen_g:
                    gaps.append(p)
                    seen_g.add(p)

        cal = self.data.setdefault("calibration", {})
        cal["probed"] = True
        cal["known_prerequisites"] = sorted(set(cal.get("known_prerequisites", [])) | set(known))
        cal["knowledge_gaps"] = sorted(set(cal.get("knowledge_gaps", [])) | set(gaps))

        total = len(results)
        passed = sum(1 for r in results if r.get("correct"))
        ratio = passed / total if total else 0.0
        if not cal.get("estimated_level"):
            if ratio >= 0.8:
                cal["estimated_level"] = "strong foundation (advanced)"
            elif ratio >= 0.5:
                cal["estimated_level"] = "intermediate"
            else:
                cal["estimated_level"] = "foundational gaps (beginner)"
        self.save()

    def record_calibration(self, known_prerequisites, knowledge_gaps, estimated_level):
        """Optional explicit override; merged with auto-derived results."""
        cal = self.data.setdefault("calibration", {})
        cal["probed"] = True
        if estimated_level:
            cal["estimated_level"] = estimated_level
        if known_prerequisites:
            cal["known_prerequisites"] = sorted(
                set(cal.get("known_prerequisites", [])) | set(known_prerequisites))
        if knowledge_gaps:
            cal["knowledge_gaps"] = sorted(
                set(cal.get("knowledge_gaps", [])) | set(knowledge_gaps))

    def record_plan(self, dag: str):
        plan = self.data.setdefault("plan", {})
        plan["dag"] = dag
        plan["planned"] = True

    def record_quiz(self, area: str, correct: bool):
        self.data.setdefault("quiz_history", []).append({
            "area": area,
            "correct": correct,
            "ts": time.time(),
        })

    def record_node_mastered(self, node: str):
        mastered = self.data.setdefault("mastered_nodes", [])
        if node and node not in mastered:
            mastered.append(node)

    # --- serialization ----------------------------------------------------
    def save(self):
        self.data["updated"] = time.time()
        self._store.setdefault("topics", {})[self.topic] = self.data
        try:
            with open(_PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2)
        except Exception:
            # Persistence is best-effort; never crash the tutor over it.
            pass

    # --- context generation ----------------------------------------------
    def context_prompt(self) -> str:
        """Render a compact, warm-start context block for the system prompt."""
        cal = self.data.get("calibration", {})
        quizzes = self.data.get("quiz_history", [])
        sessions = self.data.get("sessions", 0)

        if not quizzes and not cal.get("probed"):
            return (
                "PERSISTENT LEARNER MODEL: No prior learner profile found for "
                f"this topic ('{self.topic}'). Perform a full, thorough PROBE "
                "this session using `probe_prerequisite` on every strand, then "
                "call `record_calibration` (or let it auto-derive) so future "
                "sessions start warm."
            )

        total = len(quizzes)
        correct = sum(1 for q in quizzes if q.get("correct"))
        pct = f"{(correct / total * 100):.0f}%" if total else "n/a"

        weak = [q.get("area", "?") for q in quizzes if not q.get("correct")]
        known = cal.get("known_prerequisites") or []
        gaps = cal.get("knowledge_gaps") or []
        level = cal.get("estimated_level") or "uncalibrated"

        # Attach the deepest difficulty at which each gap failed.
        gap_depth = {}
        order = {"easy": 1, "medium": 2, "hard": 3}
        for r in self.data.get("probe_results", []):
            if not r.get("correct"):
                p = (r.get("prerequisite") or "").strip()
                d = (r.get("difficulty") or "medium")
                if p not in gap_depth or order.get(d, 2) > order.get(gap_depth[p], 2):
                    gap_depth[p] = d

        lines = [
            "PERSISTENT LEARNER MODEL (loaded from prior sessions — DO NOT re-probe "
            "what is already confirmed known):",
            f"- Topic: {self.topic}",
            f"- Estimated level: {level}",
            f"- Prior sessions: {sessions}",
            f"- Quiz performance: {total} quizzes, {correct} correct ({pct})",
        ]
        lines.append("- Previously KNOWN prerequisites (skip probing these): " +
                     (", ".join(known) if known else "none recorded"))
        if gaps:
            gap_str = ", ".join(
                f"{g} (failed at {gap_depth.get(g, '?')})" if g in gap_depth else g
                for g in gaps
            )
        else:
            gap_str = "none"
        lines.append("- Known knowledge GAPS (prioritize these first): " + gap_str)
        if weak:
            lines.append("- Weak areas from past sessions (revisit & re-quiz): " +
                         ", ".join(weak[-8:]))
        lines.append(
            "Start warm: skip probing confirmed-known prerequisites and prioritize "
            "the gaps above before introducing new material."
        )
        return "\n".join(lines)


def build_learner_tools(learner: LearnerModel):
    """Expose `probe_prerequisite` (structured, auto-mapped) and the optional
    `record_calibration` override."""
    from extensions.quiz import ask_quiz

    def probe_prerequisite(
        prerequisite: str,
        question: str,
        options: list[str],
        correct_idx: int,
        explanation: str,
        difficulty: str = "medium",
    ) -> str:
        """PROBE a specific prerequisite strand with a graded multiple-choice question.

        Use this (NOT `ask_quiz`) during the PROBE phase for EVERY prerequisite
        strand the lesson depends on, naming it exactly in `prerequisite`, and
        set `difficulty` (easy/medium/hard) to reflect how deep the probe went.
        Binary-search to the student's FAILURE boundary on each strand — probe
        deeper (hard) once they get the easy/medium ones right. The result is
        recorded against that precise prerequisite so the learner model maps
        exactly which prerequisites are known vs missing, and the planner can
        build a precise DAG. The harness enforces a minimum number of distinct
        strands and quizzes, so probe thoroughly and broadly.
        Returns the quiz result string.
        """
        res = ask_quiz(
            question=question,
            options=options,
            correct_idx=correct_idx,
            explanation=explanation,
        )
        correct = "Incorrect" not in res
        learner.record_probe_result(prerequisite, correct, question, difficulty)
        return res

    def record_calibration(
        known_prerequisites: list[str],
        knowledge_gaps: list[str],
        estimated_level: str = "",
    ) -> str:
        """Optionally override the auto-derived calibration.

        The harness already derives known/gap prerequisites automatically from
        your `probe_prerequisite` results. Use this only to refine the estimated
        level or add context the probes did not capture. SAVED to disk and
        reloaded next session. Returns a status string.
        """
        learner.record_calibration(
            known_prerequisites or [], knowledge_gaps or [], estimated_level or ""
        )
        learner.save()
        return ("Learner calibration saved and will persist across sessions. "
                f"Known: {len(known_prerequisites or [])}, Gaps: "
                f"{len(knowledge_gaps or [])}, Level: {estimated_level or 'auto-derived'}.")

    return [probe_prerequisite, record_calibration]
