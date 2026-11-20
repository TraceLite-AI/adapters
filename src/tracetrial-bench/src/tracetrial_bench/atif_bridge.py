"""Convert Harbor ATIF trajectories into TraceTrial-Bench normalized event streams."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_EXIT_RE = re.compile(
    r"(?:exit(?:ed)?(?:\s+with)?(?:\s+code)?|exit[_ -]?code[\"']?\s*[:=]?)\s*(-?\d+)\b",
    re.IGNORECASE,
)


def convert_atif_to_tracetrial_bundle(
    atif_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Translate an ATIF ``trajectory.json`` into TraceTrial-Bench's:
    ``(events_list, summary_dict, execution_probe_evidence_dict)``."""
    if not atif_path.is_file():
        return [], {}, {}
    try:
        doc = json.loads(atif_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return [], {}, {}

    steps = doc.get("steps") if isinstance(doc, dict) else None
    if not isinstance(steps, list):
        return [], {}, {}

    events: list[dict[str, Any]] = [
        {"seq": 1, "event_type": "run_started", "source": "harbor_atif"}
    ]
    post_tool_obs: list[dict[str, Any]] = []
    seq = 2

    for step in steps:
        if not isinstance(step, dict):
            continue
        source = str(step.get("source") or "")
        message = step.get("message")

        tool_calls = step.get("tool_calls")
        observation = step.get("observation")
        obs_results: dict[str, dict[str, Any]] = {}
        if isinstance(observation, dict):
            for res in observation.get("results") or []:
                if isinstance(res, dict) and res.get("source_call_id"):
                    obs_results[str(res["source_call_id"])] = res

        if isinstance(tool_calls, list) and tool_calls:
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
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                call_id = str(tc.get("tool_call_id") or f"call-{seq:04d}")
                fn_name = str(tc.get("function_name") or tc.get("name") or "tool")
                args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
                res_obj = obs_results.get(call_id, {})
                out_content = res_obj.get("content", "")
                if not isinstance(out_content, str):
                    out_content = json.dumps(out_content, ensure_ascii=False)
                extra = res_obj.get("extra") if isinstance(res_obj.get("extra"), dict) else {}
                exit_code = extra.get("exit_code")
                if not isinstance(exit_code, int) or isinstance(exit_code, bool):
                    m = _EXIT_RE.search(out_content)
                    exit_code = int(m.group(1)) if m else 0
                is_err = extra.get("is_error")
                if not isinstance(is_err, bool):
                    is_err = exit_code != 0

                tool_result_payload: dict[str, Any] = {
                    "call_id": call_id,
                    "tool_call_id": call_id,
                    "tool_name": fn_name,
                    "content": out_content,
                    "exit_code": exit_code,
                    "error": is_err,
                    "status": "failed" if is_err else "completed",
                }
                events.append(
                    {
                        "seq": seq,
                        "event_type": "tool",
                        "tool_call": {
                            "call_id": call_id,
                            "tool_call_id": call_id,
                            "name": fn_name,
                            "tool_name": fn_name,
                            "provider_executed": True,
                            "arguments": args,
                        },
                        "tool_result": tool_result_payload,
                    }
                )
                post_tool_obs.append(
                    {
                        "tool_call_id": call_id,
                        "tool_name": fn_name,
                        "arguments": args,
                        "exit_code": exit_code,
                        "error": is_err,
                        "status": "failed" if is_err else "completed",
                    }
                )
                seq += 1
        elif source == "agent" and isinstance(message, str) and message.strip():
            events.append(
                {
                    "seq": seq,
                    "event_type": "assistant_message",
                    "content": message,
                    "text": message,
                }
            )
            seq += 1

    events.append(
        {"seq": seq, "event_type": "run_finished", "status": "completed"}
    )
    summary = {
        "trace_complete": True,
        "status": "finished",
        "timed_out": False,
        "error_type": None,
        "last_event_seq": len(events),
    }
    probe = {"post_tool_observations": post_tool_obs}
    return events, summary, probe


def convert_atif_to_tracetrial_events(atif_path: Path) -> list[dict[str, Any]]:
    events, _, _ = convert_atif_to_tracetrial_bundle(atif_path)
    return events
