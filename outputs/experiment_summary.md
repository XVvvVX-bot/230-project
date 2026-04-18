# Experiment Summary

## Trial-Set Design

- Scored packets: 60
- Emails per packet: {5: 20, 6: 20, 8: 20}
- SKU/location records per packet: {3: 19, 4: 17, 5: 24}
- Actionable pattern counts: {'lead_time_delay': 12, 'partial_shipment': 12, 'shipment_cancellation': 12, 'corrected_update': 12, 'ambiguous_buried_delay': 12}
- Noise tiers: {'low': 20, 'medium': 20, 'high': 20}
- Distractor types: irrelevant_chatter, wrong_sku, resolved_issue, admin_note
- System response time (hours): 4.0
- Human response time (hours): 8.0
- Human missed-email risk: 0.120

## Extraction Accuracy

| Metric | Value |
|---|---:|
| Actionable-email identification accuracy | 0.950 |
| Focal SKU exact-match accuracy | 0.950 |
| Location exact-match accuracy | 0.950 |
| Disruption-type exact-match accuracy | 0.733 |
| Mean absolute delay error (days) | 0.744 |
| Mean absolute quantity error | 71.439 |
| Packet-level exact match | 0.450 |

## End-to-End Decision Performance

| Arm | Mean cost increment vs gold | Mean service level | Mean stockout cost | Mean holding cost | Mean pre-response shortage cost |
|---|---:|---:|---:|---:|---:|
| Gold omnipotent | 0.00 | 1.000 | 0.00 | 0.00 | 0.00 |
| LLM instant | 59.79 | 0.969 | 13.10 | 26.71 | 0.00 |
| System-based operation | 223.24 | 0.370 | 221.35 | 1.89 | 10.31 |
| Human planner only | 223.24 | 0.370 | 221.35 | 1.89 | 49.70 |

## Robustness by Noise Tier

| Noise tier | LLM exact match | Mean LLM cost increment | Mean system cost increment | Mean human cost increment |
|---|---:|---:|---:|---:|
| low | 0.800 | 55.04 | 215.95 | 215.95 |
| medium | 0.350 | 61.35 | 237.06 | 237.06 |
| high | 0.200 | 62.99 | 216.70 | 216.70 |

## Top Failure Modes

- Misread delay or affected quantity: observed in 26 scored packets; average LLM cost increment vs gold = 63.8.
- Missed corrective or decisive email: observed in 3 scored packets; average LLM cost increment vs gold = 79.6.
