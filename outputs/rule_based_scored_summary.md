# Rule-Based Extractor Evaluation

## Design

- Input file: `data\scored_packets.jsonl`
- Packets: 60
- Calibration rule: this parser was designed against pilot packets only.
- Realistic system interpretation: ERP scope supplies the focal SKU/location; deterministic text rules parse supplier emails into the same JSON schema used by the LLM.
- The parser does not read `gold`, `thread_type`, or `is_actionable` during extraction.

## Accuracy

| Metric | Accuracy |
|---|---:|
| Packet exact match | 0.600 |
| actionable | 0.833 |
| decisive_email_id | 0.833 |
| focal_sku | 0.833 |
| affected_location | 0.833 |
| disruption_type | 0.833 |
| original_eta | 0.683 |
| revised_eta | 0.750 |
| delay_days | 0.650 |
| quantity_affected | 0.833 |

## Misses

| Packet | Pattern | Noise | Main difference |
|---|---|---|---|
| S005 | lead_time_delay | medium | original_eta, delay_days |
| S007 | lead_time_delay | medium | original_eta, delay_days |
| S008 | lead_time_delay | medium | revised_eta, delay_days |
| S009 | lead_time_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S010 | lead_time_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S011 | lead_time_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S012 | lead_time_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S022 | partial_shipment | high | revised_eta, delay_days |
| S031 | shipment_cancellation | medium | original_eta |
| S034 | shipment_cancellation | high | original_eta |
| S036 | shipment_cancellation | high | original_eta |
| S041 | corrected_update | medium | original_eta, delay_days |
| S043 | corrected_update | medium | revised_eta, delay_days |
| S044 | corrected_update | medium | original_eta, delay_days |
| S047 | corrected_update | high | original_eta, delay_days |
| S049 | ambiguous_buried_delay | low | revised_eta, delay_days |
| S052 | ambiguous_buried_delay | low | revised_eta, delay_days |
| S054 | ambiguous_buried_delay | medium | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S055 | ambiguous_buried_delay | medium | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S056 | ambiguous_buried_delay | medium | original_eta, delay_days |
| S057 | ambiguous_buried_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S058 | ambiguous_buried_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S059 | ambiguous_buried_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S060 | ambiguous_buried_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |