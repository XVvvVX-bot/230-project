# LLM Email Extraction and Inventory Response Experiment

This repository packages the final experiment for the IEOR 230 project:

- the LLM is tested as an information-extraction layer over noisy supplier emails
- the downstream planning logic is fixed across arms
- operational value is measured through a stress-tested inventory simulation rather than a single stylized case

## What This Produces

Running `generate_packets.py` creates:

- `data/pilot_packets.jsonl`: 12 pilot packets for prompt/schema refinement
- `data/scored_packets.jsonl`: 60 scored multi-email, multi-SKU packets

Running `run_experiment.py` creates:

- `outputs/llm_requests.jsonl`: ready-to-use prompt payloads for a real LLM
- `outputs/demo_llm_predictions.jsonl`: simulated extraction outputs for a dry run
- `outputs/experiment_results.json`: full metrics and packet-level results
- `outputs/experiment_summary.md`: paper-ready summary tables and error analysis
- `outputs/performance_by_noise.svg`: figure for robustness by noise level

## Experiment Logic

The scored set uses:

- 60 packets
- 5 actionable disruption patterns
- 3 noise tiers
- 4 replicates per pattern-tier combination

Each packet contains:

- 5 to 8 emails
- 3 to 5 SKU/location records
- 1 actionable disruption thread
- distractors such as wrong-SKU chatter, resolved issues, and irrelevant supplier notes
- medium and high noise packets may express timing and quantity indirectly through weekday slots, relative dates, case packs, or pallet language rather than plain dates and unit counts

## Evaluation Arms

The simulation evaluates four arms:

1. `gold`: omniscient lower-bound benchmark with true disruption information and perfect scheduling
2. `llm_instant`: uses the LLM extraction immediately at time zero
3. `system_based_operation`: receives the correct structured update only after a configurable ERP delay
4. `human_planner_only`: receives the signal after a longer delay and may miss the actionable email entirely

Important: the LLM never chooses order quantities directly. It only extracts structured disruption fields.

## Simulation Design

After extraction, all arms enter the same downstream hourly simulation:

- horizon: `18` hours by default
- on-hand inventory: only `3` to `8` hours of demand cover
- on-order inventory: only `2` to `6` hours of demand cover
- reallocation feasible only within `1.5` hours
- expediting feasible only within `3` hours

This deliberately tight regime makes information timing economically meaningful. If an arm learns the disruption too late, it loses access to fast corrective actions and incurs stockout cost.

## Demo vs Real LLM

This package includes a `demo_llm_predictions.jsonl` file so the full pipeline can run locally without API access.

For the real experiment:

1. Keep the generated `outputs/llm_requests.jsonl`
2. Run those packets through one frozen LLM prompt
3. Save the model outputs as `outputs/actual_llm_predictions.jsonl` using the same JSONL schema as `demo_llm_predictions.jsonl`
4. Re-run `run_experiment.py`; if `actual_llm_predictions.jsonl` exists, the evaluator will use it automatically instead of the demo predictions

To call Gemini directly from `run_experiment.py`, copy `.env.example` to `.env` and set:

- `LLM_PROVIDER=gemini`
- `GEMINI_API_KEY=...`
- optional `GEMINI_MODEL` such as `gemini-2.5-flash-lite`
- optional `GEMINI_DELAY_SECONDS` to throttle between packets
- optional `GEMINI_MAX_RETRIES` and `GEMINI_TIMEOUT_SECONDS`
- experiment parameters such as `SYSTEM_RESPONSE_HOURS`, `HUMAN_RESPONSE_HOURS`, or `HUMAN_MISS_PROB`

## How To Run

1. Generate packet files if you want to refresh the synthetic dataset:

```powershell
python .\generate_packets.py
```

2. Evaluate the existing packet files:

```powershell
python .\run_experiment.py
```

To evaluate with Gemini over the existing scored packets:

```powershell
Copy-Item .env.example .env
# Fill in GEMINI_API_KEY in .env, then run:
python .\run_experiment.py
```

## Suggested Paper Use

You can lift the following directly into the report:

- trial-set design from `outputs/experiment_summary.md`
- extraction accuracy table
- four-arm decision performance table
- robustness discussion by noise tier
- the generated figure `outputs/performance_by_noise.svg`

## Assumptions

- Supplier email packets are synthetic but calibrated to course-style inventory settings
- Gold labels are generated from the synthetic scenario definition, which is equivalent to manual labeling for designed packets
- No API key is required to reproduce the local dry run
- The published repository excludes `.env` so no local secrets are committed
