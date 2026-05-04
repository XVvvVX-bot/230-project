# LLM Supplier-Email Extraction and Cutoff Response Experiment

This folder contains the final IEOR 230 experiment. The project tests whether LLM-based email extraction improves supply-chain exception response when supplier disruption signals arrive as noisy unstructured emails.

## Final Experiment

The final experiment is `run_cutoff_experiment.py`.

It compares:

- `llm_agent`: Gemini extracts the disruption signal immediately.
- `rule_system`: a deterministic rule-based parser extracts supplier email fields automatically.
- `human_planner`: a human planner receives the true signal after stochastic queue delay and possible missed-email risk.
- `hybrid_llm_human`: Gemini triages the email quickly, then a human verifies/corrects the flagged case.
- `oracle`: an infeasible perfect benchmark used only as a lower-bound reference.

The LLM never chooses inventory actions directly. It only extracts structured fields. The same action logic then decides whether to reallocate, expedite, reorder late, or do nothing.

## Key Files

- `data/pilot_packets.jsonl`: 12 pilot packets used only for prompt/rule tuning.
- `data/scored_packets.jsonl`: 60 scored packets used for final evaluation.
- `extraction_prompt.md`: final Gemini prompt.
- `extraction_schema.json`: required JSON output schema.
- `gemini_inference.py`: Gemini API helper.
- `prepare_llm_requests.py`: creates pilot/scored request JSONL files.
- `run_gemini_requests.py`: runs Gemini on prepared request files.
- `rule_based_extractor.py`: deterministic system-arm parser calibrated on pilot packets.
- `score_extraction_predictions.py`: scores extraction outputs against gold labels.
- `run_cutoff_experiment.py`: final operational experiment.
- `make_visualizations.py`: regenerates report-ready charts.

## Main Outputs

- `outputs/actual_llm_predictions.jsonl`: current Gemini scored predictions.
- `outputs/actual_llm_summary.md`: Gemini scored extraction accuracy.
- `outputs/rule_based_scored_predictions.jsonl`: rule-based scored predictions.
- `outputs/rule_based_scored_summary.md`: rule-based scored extraction accuracy.
- `outputs/cutoff_experiment_summary.md`: final experiment summary for the report.
- `outputs/llm_hallucination_analysis.md`: analysis of LLM hallucination/confabulation risks in the extraction layer.
- `outputs/cutoff_experiment_results.json`: full final experiment results.
- `outputs/cutoff_experiment_arm_summary.csv`: arm-level comparison.
- `outputs/cutoff_experiment_by_pattern.csv`: performance by disruption pattern.
- `outputs/cutoff_experiment_by_cutoff.csv`: performance by cutoff tier.

Report-ready charts are in `visualizations/`.

The Overleaf-ready final report is in `report/main.tex` with citations in `report/references.bib`.

## How To Rerun

1. Prepare Gemini requests from the current prompt:

```powershell
python .\prepare_llm_requests.py
```

2. Optional: rerun Gemini on the pilot set:

```powershell
python .\run_gemini_requests.py --requests outputs\pilot_llm_requests.jsonl --output outputs\pilot_actual_llm_predictions.jsonl --overwrite
python .\score_extraction_predictions.py --packets data\pilot_packets.jsonl --predictions outputs\pilot_actual_llm_predictions.jsonl --summary outputs\pilot_actual_llm_summary.md
```

3. Rerun Gemini on the scored set:

```powershell
python .\run_gemini_requests.py --requests outputs\llm_requests.jsonl --output outputs\actual_llm_predictions.jsonl --overwrite
python .\score_extraction_predictions.py --packets data\scored_packets.jsonl --predictions outputs\actual_llm_predictions.jsonl --summary outputs\actual_llm_summary.md
```

4. Rerun rule-based extraction and the final experiment:

```powershell
python .\rule_based_extractor.py --input data\scored_packets.jsonl --output outputs\rule_based_scored_predictions.jsonl --summary outputs\rule_based_scored_summary.md
python .\run_cutoff_experiment.py
```

5. Regenerate visualizations:

```powershell
python .\make_visualizations.py
```

## Current Result

The final cutoff experiment uses a 10-day horizon and reports service loss relative to a no-disruption baseline. In the current run:

- `hybrid_llm_human` has the lowest total cost.
- `llm_agent` beats both `rule_system` and `human_planner` overall.
- `rule_system` remains competitive on cleaner template-like cases.
- LLM and hybrid workflows are strongest when language is buried, corrected, or time-sensitive.

## Cost Basis

Processing costs are base-case assumptions, not measured company accounting data.

- Human planner cost is anchored to BLS logistician wages. The model uses a loaded planner rate of `$50/hour`, approximately the BLS median logistician wage plus benefits/overhead.
- Human-only review assumes `30` minutes per exception, so the processing cost is `$25`.
- Hybrid approval assumes `10` minutes of planner review plus LLM processing, so the processing cost is `$8.58`.
- Gemini and rule-system automated costs are modeled as low all-in per-exception processing costs: `$0.25` for LLM extraction and `$0.10` for rule extraction. This reflects that Gemini Flash-Lite token prices are cents or less for these packet sizes, while still allowing small integration/logging overhead.

## Assumptions

- Supplier email packets are synthetic but designed from realistic disruption patterns.
- Pilot packets are used for prompt/rule tuning; scored packets are the held-out evaluation set.
- `.env` is intentionally excluded from Git and should contain local Gemini credentials only.
