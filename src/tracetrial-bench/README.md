# TraceTrial-Bench Adapter

## Overview

This adapter translates **[TraceTrial-Bench](https://github.com/TraceLite-AI/TraceTrial-Bench)** (*Trial by Trace: Benchmarking AI Agent Harnesses for Reliability and Failure Attribution*, [arXiv:2610.32285](https://arxiv.org/abs/2610.32285)) into Harbor's containerized task format.

> **Status (`Draft / WIP`):** Task generation, strict workspace/verifier isolation, and the Harbor ATIF (`trajectory.json`) → TraceTrial-Bench event-stream bridge are implemented and covered by unit tests. `parity_experiment.json` is intentionally left empty (`[]`) pending maintainer alignment on multi-turn `simulated-user` wiring, Unix-socket business simulator daemons, and 3-run matched parity experiments.

## What is TraceTrial-Bench?

TraceTrial-Bench is a trace-grounded benchmark that isolates **AI agent harness engineering quality** from underlying LLM capability across **6 capability families** (`C`: Context & Compaction, `E`: Execution & Sandbox, `G`: Safety & Guardrails, `L`: Long-Horizon Recovery, `O`: Sub-agent Orchestration, `T`: Tool Protocol & MCP Fidelity). Each task pairs untouched real-world workspace artifacts with a layered `0..100` verifier (`HarnessScore` + `AgentScore`) over workspace outputs and execution traces.

- **Repository:** <https://github.com/TraceLite-AI/TraceTrial-Bench> (pinned commit `4f94ae64a8e99ef8806200ffdcf496c9d7390f76`)
- **Dataset:** <https://huggingface.co/datasets/TraceLite-AI/TraceTrial-Bench>
- **License:** MIT

## Adapter Features

- **Pinned upstream source (`4f94ae64a8`):** Sparse-clones `Task/` and `verifier/` from `TraceLite-AI/TraceTrial-Bench` (or reads `--source-dir` offline).
- **Strict workspace isolation:** Copies only `Task/<id>/workspace/` into `environment/workspace/`; `verifier/` is staged exclusively under `tests/verifier/` so evaluation rules never enter the agent image.
- **ATIF trajectory bridge (`atif_bridge.py` / `verify.py`):** Converts Harbor's native `/logs/agent/trajectory.json` (ATIF) into TraceTrial-Bench's normalized `events.json` schema before running `verifier/run.sh`, writing continuous `[0.0, 1.0]` rewards to `/logs/verifier/reward.txt`.
- **Split selection:** Supports `--split single-turn` (69 single-turn tasks, default) and `--split all` (all 96 repository tasks including `fixed_turns` and `simulator` tasks).

## Installation

```bash
cd src/tracetrial-bench
uv sync
```

## Usage

```bash
# List all 69 single-turn tasks
uv run tracetrial-bench --list-tasks

# Generate 5 tasks into datasets/tracetrial-bench
uv run tracetrial-bench --output-dir ../../datasets/tracetrial-bench --limit 5 --overwrite

# Generate specific task IDs from a local TraceTrial-Bench checkout
uv run tracetrial-bench \
  --source-dir /path/to/TraceTrial-Bench \
  --task-ids C1-escalation-export-001 \
  --output-dir ../../datasets/tracetrial-bench \
  --overwrite
```

## Generated Task Structure

```text
datasets/tracetrial-bench/<task-id-lower>/
├── task.toml                 # Harbor task metadata (tracelite-ai/tracetrial-bench__<id>)
├── instruction.md            # Verbatim prompt.md from TraceTrial-Bench
├── environment/
│   ├── Dockerfile            # Isolated workspace image (no verifier files)
│   ├── entrypoint_sim.sh
│   └── workspace/            # Verbatim Task/<id>/workspace/
├── solution/
│   └── solve.sh              # Placeholder (open oracle design question in Draft PR)
└── tests/
    ├── Dockerfile            # Dedicated separate verifier image (Harbor #3712)
    ├── test.sh               # Entrypoint writing /logs/verifier/reward.txt
    ├── verify.py             # ATIF -> TraceTrial event bridge + rule scorer
    └── verifier/             # Untouched Task/<id>/verifier/ scripts & YAML specs
```

## Run Evaluation

```bash
uv run harbor run -c src/tracetrial-bench/run_tracetrial-bench.yaml
```

## Comparison with Original Benchmark (Parity)

Parity runs have not been executed yet; this Draft PR coordinates methodology with Harbor maintainers first.

| Agent | Model | Metric | Number of Runs | Dataset Size | Original Performance | Harbor Performance |
| --- | --- | --- | --- | --- | --- | --- |
| TBD (pending coordination) | TBD | Overall Score (`[0, 1]`) | 3 | 69 (`single-turn`) | TBD | TBD |

```bash
# Planned parity reproduction command once methodology is confirmed:
uv run tracetrial-bench --output-dir ../../datasets/tracetrial-bench --split single-turn --overwrite
uv run harbor run -d datasets/tracetrial-bench -a claude-code -m anthropic/claude-sonnet-4-5 -n 3
```

## Notes & Caveats

1. **Multi-turn & simulated-user tasks (`27` tasks):** `23` `fixed_turns` tasks and `4` `simulator` tasks define multi-turn follow-up schedules in `turns.json`. Default `--split single-turn` selects the `69` single-turn tasks while we align on Harbor's `simulated-user` bridge.
2. **Unix-socket business simulators & LLM rubric layer:** Tasks with `business_simulator` (`simulator/server.py`) and `type: rubric` judge items in `agent_score.yaml` / `harness_score.yaml` currently run deterministic `type: rule` checks in `verify.py`; full sidecar simulator startup and optional LLM rubric scoring are queued for maintainer feedback.

## Troubleshooting

- **`Unknown TraceTrial-Bench task IDs`:** Task IDs are case-sensitive (`C1-escalation-export-001`); run `uv run tracetrial-bench --list-tasks --split all` to inspect valid IDs.
- **Offline environments:** Pass `--source-dir /path/to/TraceTrial-Bench` to avoid cloning from GitHub during task generation.

## Citation

```bibtex
@article{cao2026trialbytrace,
  title={Trial by Trace: Benchmarking AI Agent Harnesses for Reliability and Failure Attribution},
  author={Cao, Zhiyong and Zhu, Hengjie and Wang, Yongxin and Li, Xuchen and Li, Jintao and Liu, Shuxia and Liu, Dunqiang and Wang, Bo and Zhang, Kairan and Lin, Cong and Yu, JiangDi and Liu, Siyuan and Yao, Sijia and Wei, Yi-Liang and Ma, Lingxu and Wang, Aijia and Chen, Anxin and Wei, Zixian and Ruan, Xiang and Xu, Ruizhi and Shi, Ruqian and Xiao, Baihua and Zhou, Sicheng},
  journal={arXiv preprint arXiv:2610.32285},
  year={2026},
  url={https://arxiv.org/abs/2610.32285}
}
```

## Authors & Contributions

- **Benchmark Authors:** TraceLite AI (`https://tracelite.ai`, `https://github.com/TraceLite-AI/TraceTrial-Bench`)
- **Harbor Adapter Authors:** TraceLite-AI (`290594480+zsicheng0214@users.noreply.github.com`)
