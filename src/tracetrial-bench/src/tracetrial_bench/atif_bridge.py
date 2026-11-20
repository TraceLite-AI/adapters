"""Convert Harbor ATIF trajectories (/logs/agent/trajectory.json) into
TraceTrial-Bench normalized event streams for trace-grounded rule verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def convert_atif_to_tracetrial_events(atif_path: Path) -> list[dict[str, Any]]:
    """Translate a Harbor ATIF ``trajectory.json`` file into TraceTrial-Bench's
    normalized ``events.json`` list (``run_started``, ``assistant_message``,
    ``tool``, ``run_finished``)."""
    if not atif_path.is_file():
        return []
    try:
        doc = json.loads(atif_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []

    steps = doc.get("steps") if isinstance(doc, dict) else None
    if not isinstance(steps, list):
        return []

    events: list[dict[str, Any]] = [
        {"seq": 0, "event_type": "run_started", "source": "harbor_atif"}
    ]
    seq = 1
    for step in steps:
        if not isinstance(step, dict):
            continue
        source = str(step.get("source") or "")
        message = step.get("message")
        if source == "agent" and isinstance(message, str) and message.strip():
            events.append(
                {
                    "seq": seq,
                    "event_type": "assistant_message",
                    "content": message,
                    "text": message,
                }
            )
            seq += 1

        tool_calls = step.get("tool_calls")
        observation = step.get("observation")
        obs_results: dict[str, Any] = {}
        if isinstance(observation, dict):
            for res in observation.get("results") or []:
                if isinstance(res, dict) and res.get("source_call_id"):
                    obs_results[str(res["source_call_id"])] = res.get("content", "")

        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                call_id = str(tc.get("tool_call_id") or f"call-{seq:04d}")
                fn_name = str(tc.get("function_name") or tc.get("name") or "tool")
                args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
                out_content = obs_results.get(call_id, "")
                if not isinstance(out_content, str):
                    out_content = json.dumps(out_content, ensure_ascii=False)
                events.append(
                    {
                        "seq": seq,
                        "event_type": "tool",
                        "tool_call": {
                            "call_id": call_id,
                            "name": fn_name,
                            "tool_name": fn_name,
                            "arguments": args,
                        },
                        "tool_result": {
                            "call_id": call_id,
                            "content": out_content,
                            "error": None,
                        },
                    }
                )
                seq += 1

    events.append(
        {"seq": seq, "event_type": "run_finished", "status": "completed"}
    )
    return events
