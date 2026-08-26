"""Tiny file-backed JSON cache shared by the agents.

Used to avoid re-paying for expensive, deterministic generations (research
briefings, Mermaid DAGs, diagram plotting code) when the same inputs recur —
both within a session and across sessions. Failures are silently ignored so a
cache miss or corrupt file never affects the actual output.
"""
import os
import json
import hashlib

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache"
)


def _path(namespace: str, key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return os.path.join(CACHE_DIR, f"{namespace}_{h}.json")


def cache_get(namespace: str, key: str):
    try:
        with open(_path(namespace, key), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def cache_set(namespace: str, key: str, value) -> None:
    try:
        with open(_path(namespace, key), "w", encoding="utf-8") as f:
            json.dump(value, f)
    except Exception:
        pass
