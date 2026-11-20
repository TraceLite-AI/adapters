#!/usr/bin/env python3
"""Separate Harbor verifier runner for TraceTrial-Bench tasks (#3712)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


TESTS_DIR = Path(__file__).resolve().parent
VERIFIER_SRC = TESTS_DIR / "verifier"
WORKSPACE_DIR = Path(os.environ.get("HARNESSBENCH_WORKSPACE", "/workspace"))
LOGS_VERIFIER = Path(os.environ.get("HARBOR_VERIFIER_LOG_DIR", "/logs/verifier"))
LOGS_AGENT = Path(os.environ.get("HARBOR_AGENT_LOG_DIR", "/logs/agent"))
LOGS_ARTIFACTS = Path(os.environ.get("HARBOR_ARTIFACTS_DIR", "/logs/artifacts"))

_EXIT_RE = re.compile(
    r"(?:exit(?:ed)?(?:\s+with)?(?:\s+code)?|exit[_ -]?code[\"']?\s*[:=]?)\s*(-?\d+)\b",
    re.IGNORECASE,
)


def _find_atif() -> Path | None:
    for candidate in (
        LOGS_AGENT / "trajectory.json",
        LOGS_ARTIFACTS / "trajectory.json",
    ):
        if candidate.is_file():
            return candidate
    return None


def _convert_atif(atif_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    try:
        doc = json.loads(atif_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return [], {}, {}
    steps = doc.get("steps") if isinstance(doc, dict) else None
    if not isinstance(steps, list):
        return [], {}, {}

    events: list[dict[str, Any]] = [{"seq": 1, "event_type": "run_started", "source": "harbor_atif"}]
    post_obs: list[dict[str, Any]] = []
    seq = 2

    for step in steps:
        if not isinstance(step, dict):
            continue
        source = str(step.get("source") or "")
        msg = step.get("message")
        obs_map: dict[str, dict[str, Any]] = {}
        obs = step.get("observation")
        if isinstance(obs, dict):
            for r in obs.get("results") or []:
                if isinstance(r, dict) and r.get("source_call_id"):
                    obs_map[str(r["source_call_id"])] = r
        tcs = step.get("tool_calls")
        if isinstance(tcs, list) and tcs:
            if source == "agent" and isinstance(msg, str) and msg.strip():
                events.append({"seq": seq, "event_type": "assistant_message", "content": msg, "text": msg})
                seq += 1
            for tc in tcs:
                if not isinstance(tc, dict):
                    continue
                cid = str(tc.get("tool_call_id") or f"call-{seq:04d}")
                fn = str(tc.get("function_name") or tc.get("name") or "tool")
                args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
                res_obj = obs_map.get(cid, {})
                out = res_obj.get("content", "")
                if not isinstance(out, str):
                    out = json.dumps(out, ensure_ascii=False)
                extra = res_obj.get("extra") if isinstance(res_obj.get("extra"), dict) else {}
                ec = extra.get("exit_code")
                if not isinstance(ec, int) or isinstance(ec, bool):
                    m = _EXIT_RE.search(out)
                    ec = int(m.group(1)) if m else 0
                is_err = extra.get("is_error")
                if not isinstance(is_err, bool):
                    is_err = ec != 0
                events.append(
                    {
                        "seq": seq,
                        "event_type": "tool",
                        "tool_call": {
                            "call_id": cid,
                            "tool_call_id": cid,
                            "name": fn,
                            "tool_name": fn,
                            "provider_executed": True,
                            "arguments": args,
                        },
                        "tool_result": {
                            "call_id": cid,
                            "tool_call_id": cid,
                            "tool_name": fn,
                            "content": out,
                            "exit_code": ec,
                            "error": is_err,
                            "status": "failed" if is_err else "completed",
                        },
                    }
                )
                post_obs.append(
                    {
                        "tool_call_id": cid,
                        "tool_name": fn,
                        "arguments": args,
                        "exit_code": ec,
                        "error": is_err,
                        "status": "failed" if is_err else "completed",
                    }
                )
                seq += 1
        elif source == "agent" and isinstance(msg, str) and msg.strip():
            events.append({"seq": seq, "event_type": "assistant_message", "content": msg, "text": msg})
            seq += 1

    events.append({"seq": seq, "event_type": "run_finished", "status": "completed"})
    summary = {
        "trace_complete": True,
        "status": "finished",
        "timed_out": False,
        "error_type": None,
        "last_event_seq": len(events),
    }
    return events, summary, {"post_tool_observations": post_obs}


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
    probe_dir = run_root / "artifacts" / "execution_probe"
    out_dir = run_root / "artifacts" / "verifier_output"
    agent_dir = run_root / "agent"
    for d in (trace_dir, probe_dir, out_dir, agent_dir):
        d.mkdir(parents=True, exist_ok=True)

    atif_file = _find_atif()
    if atif_file is not None:
        events, summary, probe = _convert_atif(atif_file)
        if events:
            (trace_dir / "events.json").write_text(
                json.dumps(events, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (trace_dir / "summary.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (probe_dir / "evidence.json").write_text(
                json.dumps(probe, indent=2, ensure_ascii=False) + "\n",
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
    cmd = (
        ["bash", str(entrypoint)]
        if entrypoint.exists()
        else ["python3", str(VERIFIER_SRC / "score.py"), "--workspace", str(WORKSPACE_DIR)]
    )
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
