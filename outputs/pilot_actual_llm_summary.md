# Rule-Based Extractor Pilot Evaluation

## Design

- Input file: `data\pilot_packets.jsonl`
- Pilot packets: 12
- Calibration rule: this parser was designed against pilot packets only.
- Realistic system interpretation: ERP scope supplies the focal SKU/location; deterministic text rules parse supplier emails into the same JSON schema used by the LLM.
- The parser does not read `gold`, `thread_type`, or `is_actionable` during extraction.

## Pilot Accuracy

| Metric | Accuracy |
|---|---:|
| Packet exact match | 0.833 |
| actionable | 1.000 |
| decisive_email_id | 1.000 |
| focal_sku | 1.000 |
| affected_location | 1.000 |
| disruption_type | 1.000 |
| original_eta | 0.917 |
| revised_eta | 0.917 |
| delay_days | 0.917 |
| quantity_affected | 1.000 |

## Misses

| Packet | Pattern | Noise | Main difference |
|---|---|---|---|
| P002 | lead_time_delay | high | original_eta, revised_eta |
| P003 | partial_shipment | medium | delay_days |