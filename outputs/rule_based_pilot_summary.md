# Rule-Based Extractor Evaluation

## Design

- Input file: `data\pilot_packets.jsonl`
- Packets: 12
- Calibration rule: this parser was designed against pilot packets only.
- Realistic system interpretation: ERP scope supplies the focal SKU/location; deterministic text rules parse supplier emails into the same JSON schema used by the LLM.
- The parser does not read `gold`, `thread_type`, or `is_actionable` during extraction.

## Accuracy

| Metric | Accuracy |
|---|---:|
| Packet exact match | 0.833 |
| actionable | 0.833 |
| decisive_email_id | 0.833 |
| focal_sku | 0.833 |
| affected_location | 0.833 |
| disruption_type | 0.833 |
| original_eta | 0.833 |
| revised_eta | 0.833 |
| delay_days | 0.833 |
| quantity_affected | 0.833 |

## Misses

| Packet | Pattern | Noise | Main difference |
|---|---|---|---|
| P002 | lead_time_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| P009 | ambiguous_buried_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |