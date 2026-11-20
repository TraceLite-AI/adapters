#!/usr/bin/env python3
"""Isolated Harbor verifier runner for TraceTrial-Bench tasks.

1. Translates `/logs/agent/trajectory.json` (ATIF) into TraceTrial-Bench's
   `artifacts/trace/harbor/events.json` layout when present.
2. Runs the task's untouched `verifier/run.sh` (`score.py`) against `/workspace`.
3. Computes the continuous objective rule reward in `[0.0, 1.0]` and writes it
   to `/logs/verifier/reward.txt` (with full breakdown in `tracetrial_score.json`).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


TESTS_DIR = Path(__file__).resolve().parent
VERIFIER_SRC = TESTS_DIR / "verifier"
WORKSPACE_DIR = Path(os.environ.get("HARNESSBENCH_WORKSPACE", "/workspace"))
LOGS_VERIFIER = Path(os.environ.get("HARBOR_VERIFIER_LOG_DIR", "/logs/verifier"))
LOGS_AGENT = Path(os.environ.get("HARBOR_AGENT_LOG_DIR", "/logs/agent"))


def _convert_atif(atif_path: Path) -> list[dict[str, Any]]:
    if not atif_path.is_file():
        return []
    try:
        doc = json.loads(atif_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    steps = doc.get("steps") if isinstance(doc, dict) else None
    if not isinstance(steps, list):
        return []
    events: list[dict[str, Any]] = [{"seq": 0, "event_type": "run_started"}]
    seq = 1
    for step in steps:
        if not isinstance(step, dict):
            continue
        msg = step.get("message")
        if step.get("source") == "agent" and isinstance(msg, str) and msg.strip():
            events.append({"seq": seq, "event_type": "assistant_message", "content": msg, "text": msg})
            seq += 1
        obs_map: dict[str, Any] = {}
        obs = step.get("observation")
        if isinstance(obs, dict):
            for r in obs.get("results") or []:
                if isinstance(r, dict) and r.get("source_call_id"):
                    obs_map[str(r["source_call_id"])] = r.get("content", "")
        for tc in step.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            cid = str(tc.get("tool_call_id") or f"call-{seq:04d}")
            fn = str(tc.get("function_name") or tc.get("name") or "tool")
            args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
            out = obs_map.get(cid, "")
            if not isinstance(out, str):
                out = json.dumps(out, ensure_ascii=False)
            events.append(
                {
                    "seq": seq,
                    "event_type": "tool",
                    "tool_call": {"call_id": cid, "name": fn, "tool_name": fn, "arguments": args},
                    "tool_result": {"call_id": cid, "content": out, "error": None},
                }
            )
            seq += 1
    events.append({"seq": seq, "event_type": "run_finished", "status": "completed"})
    return events


def _score_from_payload(payload: dict[str, Any]) -> float:
    if isinstance(payload.get("score"), (int, float)):
        val = float(payload["score"])
        return val / 100.0 if val > 1.0 else max(0.0, min(1.0, val))
    if isinstance(payload.get("pass"), bool):
        return 1.0 if payload["pass"] else 0.0
    if isinstance(payload.get("passed"), bool):
        return 1.0 if payload["passed"] else 0.0
    rules = payload.get("rule_results")
    if isinstance(rules, dict):
        items: list[float] = []
        for layer_key in ("harness", "agent"):
            for entry in rules.get(layer_key) or []:
                if isinstance(entry, dict):
                    if isinstance(entry.get("score"), (int, float)):
                        items.append(float(entry["score"]))
                    elif isinstance(entry.get("passed"), bool):
                        items.append(1.0 if entry["passed"] else 0.0)
        if items:
            return max(0.0, min(1.0, sum(items) / len(items)))
    return 0.0


def main() -> int:
    LOGS_VERIFIER.mkdir(parents=True, exist_ok=True)
    run_root = LOGS_VERIFIER / "run_layout"
    trace_dir = run_root / "artifacts" / "trace" / "harbor"
    out_dir = run_root / "artifacts" / "verifier_output"
    agent_dir = run_root / "agent"
    for d in (trace_dir, out_dir, agent_dir):
        d.mkdir(parents=True, exist_ok=True)

    events = _convert_atif(LOGS_AGENT / "trajectory.json")
    if events:
        (trace_dir / "events.json").write_text(
            json.dumps(events, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    env = dict(os.environ)
    env["HARNESSBENCH_RUN_DIR"] = str(run_root)
    env["HARNESSBENCH_AGENT_DIR"] = str(agent_dir)
    env["HARNESSBENCH_WORKSPACE"] = str(WORKSPACE_DIR)
    env["WORKSPACE_PATH"] = str(WORKSPACE_DIR)
    env["HARNESSBENCH_VERIFIER_DIR"] = str(VERIFIER_SRC)
    env["HARNESSBENCH_OUTPUT_DIR"] = str(out_dir)

    entrypoint = VERIFIER_SRC / "run.sh"
    cmd = ["bash", str(entrypoint)] if entrypoint.exists() else ["python3", str(VERIFIER_SRC / "score.py"), "--workspace", str(WORKSPACE_DIR)]
    completed = subprocess.run(
        cmd,
        cwd=str(TESTS_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    reward = 0.0
    parsed_payload: dict[str, Any] = {
        "exit_code": completed.returncode,
        "stderr": completed.stderr[-2000:],
    }
    for candidate in reversed(completed.stdout.splitlines()):
        s = candidate.strip()
        if s.startswith("{"):
            try:
                parsed_payload = json.loads(s)
                reward = _score_from_payload(parsed_payload)
                break
            except json.JSONDecodeError:
                continue
    else:
        try:
            parsed_payload = json.loads(completed.stdout.strip())
            reward = _score_from_payload(parsed_payload)
        except json.JSONDecodeError:
            reward = 1.0 if completed.returncode == 0 and "PASS" in completed.stdout else 0.0

    (LOGS_VERIFIER / "tracetrial_score.json").write_text(
        json.dumps(parsed_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (LOGS_VERIFIER / "reward.txt").write_text(f"{reward:.6f}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
