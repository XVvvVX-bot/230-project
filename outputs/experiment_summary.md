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
- Human missed-email risk: 0.100

## Extraction Accuracy

| Metric | Value |
|---|---:|
| Actionable-email identification accuracy | 0.983 |
| Focal SKU exact-match accuracy | 0.883 |
| Location exact-match accuracy | 0.883 |
| Disruption-type exact-match accuracy | 0.983 |
| Mean absolute delay error (days) | 0.128 |
| Mean absolute quantity error | 2.169 |
| Packet-level exact match | 0.783 |

## End-to-End Decision Performance

| Arm | Mean cost increment vs gold | Mean service level | Mean stockout cost | Mean holding cost | Mean pre-response shortage cost |
|---|---:|---:|---:|---:|---:|
| Gold omnipotent | 0.00 | 1.000 | 0.00 | 0.00 | 0.00 |
| Rule-based instant | 85.38 | 0.890 | 55.98 | 21.72 | 0.00 |
| LLM simulated | 70.13 | 0.931 | 35.64 | 25.13 | 0.00 |
| LLM instant | 70.26 | 0.930 | 35.83 | 25.06 | 0.00 |
| System-based operation | 82.84 | 0.926 | 35.96 | 23.36 | 0.46 |
| Human planner only | 154.33 | 0.722 | 135.91 | 13.31 | 12.56 |

## Robustness by Noise Tier

| Noise tier | LLM exact match | Mean LLM cost increment | Mean system cost increment | Mean human cost increment |
|---|---:|---:|---:|---:|
| low | 0.950 | 64.85 | 78.49 | 149.41 |
| medium | 0.750 | 70.69 | 86.28 | 163.29 |
| high | 0.650 | 75.25 | 83.77 | 150.31 |

## Top Failure Modes

- Selected the wrong SKU/location: observed in 6 scored packets; average LLM cost increment vs gold = 85.6.
- Misread delay or affected quantity: observed in 4 scored packets; average LLM cost increment vs gold = 78.5.
- Missed corrective or decisive email: observed in 3 scored packets; average LLM cost increment vs gold = 88.7.
