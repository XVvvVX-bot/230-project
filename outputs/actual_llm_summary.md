# Extraction Prediction Evaluation

## Design

- Packet file: `data\scored_packets.jsonl`
- Prediction file: `outputs\actual_llm_predictions.jsonl`
- Packets scored: 60
- Exact match requires every required extraction field to match the gold label.

## Accuracy

| Metric | Accuracy |
|---|---:|
| Packet exact match | 0.617 |
| actionable | 0.983 |
| decisive_email_id | 0.983 |
| focal_sku | 0.983 |
| affected_location | 0.983 |
| disruption_type | 0.983 |
| original_eta | 0.817 |
| revised_eta | 0.850 |
| delay_days | 0.783 |
| quantity_affected | 0.900 |

## Misses

| Packet | Pattern | Noise | Main difference |
|---|---|---|---|
| S008 | lead_time_delay | medium | quantity_affected |
| S011 | lead_time_delay | high | revised_eta, delay_days, quantity_affected |
| S012 | lead_time_delay | high | original_eta, revised_eta, quantity_affected |
| S013 | partial_shipment | low | delay_days |
| S015 | partial_shipment | low | delay_days |
| S020 | partial_shipment | medium | delay_days |
| S021 | partial_shipment | high | revised_eta, delay_days, quantity_affected |
| S022 | partial_shipment | high | original_eta, revised_eta |
| S024 | partial_shipment | high | revised_eta, delay_days |
| S029 | shipment_cancellation | medium | original_eta |
| S031 | shipment_cancellation | medium | original_eta |
| S034 | shipment_cancellation | high | original_eta |
| S035 | shipment_cancellation | high | original_eta |
| S036 | shipment_cancellation | high | original_eta |
| S042 | corrected_update | medium | revised_eta, delay_days |
| S044 | corrected_update | medium | quantity_affected |
| S051 | ambiguous_buried_delay | low | delay_days |
| S054 | ambiguous_buried_delay | medium | delay_days |
| S055 | ambiguous_buried_delay | medium | delay_days |
| S056 | ambiguous_buried_delay | medium | original_eta, revised_eta |
| S058 | ambiguous_buried_delay | high | original_eta, delay_days |
| S059 | ambiguous_buried_delay | high | actionable, decisive_email_id, focal_sku, affected_location, disruption_type, original_eta, revised_eta, delay_days, quantity_affected |
| S060 | ambiguous_buried_delay | high | original_eta, revised_eta, delay_days |