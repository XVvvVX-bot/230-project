# Cutoff-Based Exception Response Experiment

## Design

- Scored packets: 60
- Simulation runs per packet-arm: 100
- Horizon: 10 days
- Cutoff tier counts: {'easy': 15, 'moderate': 21, 'near_impossible': 6, 'tight': 18}
- System arm: deterministic rule-based email extraction calibrated only on pilot packets.
- LLM arm: current Gemini predictions from `outputs/actual_llm_predictions.jsonl`.
- Human arm: gold interpretation after stochastic queue delay and noise-dependent miss risk.
- Hybrid arm: LLM triage followed by human correction when the LLM identifies the right email/SKU/location.
- Oracle is a perfect lower-bound benchmark and should not be treated as a realistic operating arm.
- Processing cost basis: planner labor is $50.00/hour loaded; human review is 30 minutes; hybrid approval is 10 minutes.
- Automated processing costs: LLM $0.25 per packet; rule system $0.10 per packet.

## Extraction Accuracy

| Extractor | Packet exact | Decisive email | Type | Original ETA | Revised ETA | Delay | Quantity |
|---|---:|---:|---:|---:|---:|---:|---:|
| llm_agent | 0.617 | 0.983 | 0.983 | 0.817 | 0.850 | 0.783 | 0.900 |
| rule_system | 0.600 | 0.833 | 0.833 | 0.683 | 0.750 | 0.650 | 0.833 |

## Arm Performance

| Arm | Mean total cost | Gap vs oracle | Service level | Service loss vs baseline | Stockout cost | Holding cost | Action cost | Processing cost | Before-cutoff rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| human_planner | 2033.00 | 2033.00 | 0.711 | 0.050 | 1167.42 | 715.62 | 124.96 | 25.00 | 0.613 |
| hybrid_llm_human | 1868.52 | 1868.52 | 0.793 | 0.024 | 850.43 | 834.39 | 175.11 | 8.58 | 0.873 |
| llm_agent | 1913.06 | 1913.06 | 0.806 | 0.025 | 804.83 | 918.30 | 189.68 | 0.25 | 1.000 |
| oracle | 0.00 | 0.00 | 1.000 | 0.000 | 0.00 | 0.00 | 0.00 | 0.00 | 1.000 |
| rule_system | 1983.83 | 1983.83 | 0.752 | 0.045 | 996.54 | 836.64 | 150.54 | 0.10 | 1.000 |

## Pattern Breakdown

| Pattern | Arm | Mean total cost | Service level | Exact/miss rate |
|---|---|---:|---:|---:|
| ambiguous_buried_delay | human_planner | 2136.64 | 0.734 | 0.897 |
| ambiguous_buried_delay | hybrid_llm_human | 2015.15 | 0.809 | 0.417 |
| ambiguous_buried_delay | llm_agent | 1990.19 | 0.837 | 0.417 |
| ambiguous_buried_delay | rule_system | 2111.94 | 0.722 | 0.250 |
| corrected_update | human_planner | 1970.45 | 0.695 | 0.878 |
| corrected_update | hybrid_llm_human | 1766.17 | 0.787 | 0.833 |
| corrected_update | llm_agent | 1814.80 | 0.830 | 0.833 |
| corrected_update | rule_system | 1898.01 | 0.786 | 0.667 |
| lead_time_delay | human_planner | 1880.40 | 0.673 | 0.903 |
| lead_time_delay | hybrid_llm_human | 1708.34 | 0.751 | 0.750 |
| lead_time_delay | llm_agent | 1749.89 | 0.757 | 0.750 |
| lead_time_delay | rule_system | 1914.03 | 0.647 | 0.417 |
| partial_shipment | human_planner | 1950.06 | 0.765 | 0.888 |
| partial_shipment | hybrid_llm_human | 1792.45 | 0.837 | 0.500 |
| partial_shipment | llm_agent | 1896.55 | 0.806 | 0.500 |
| partial_shipment | rule_system | 1881.47 | 0.805 | 0.917 |
| shipment_cancellation | human_planner | 2227.46 | 0.689 | 0.903 |
| shipment_cancellation | hybrid_llm_human | 2060.47 | 0.783 | 0.583 |
| shipment_cancellation | llm_agent | 2113.85 | 0.802 | 0.583 |
| shipment_cancellation | rule_system | 2113.70 | 0.802 | 0.750 |

## Cutoff Breakdown

| Cutoff tier | Arm | Mean total cost | Before-cutoff rate | Service level |
|---|---|---:|---:|---:|
| easy | human_planner | 1800.90 | 1.000 | 0.756 |
| easy | hybrid_llm_human | 1736.71 | 1.000 | 0.779 |
| easy | llm_agent | 1789.77 | 1.000 | 0.779 |
| easy | rule_system | 1874.14 | 1.000 | 0.723 |
| moderate | human_planner | 2082.24 | 0.746 | 0.727 |
| moderate | hybrid_llm_human | 1887.93 | 1.000 | 0.806 |
| moderate | llm_agent | 1990.58 | 1.000 | 0.785 |
| moderate | rule_system | 2079.79 | 1.000 | 0.733 |
| near_impossible | human_planner | 2087.23 | 0.000 | 0.624 |
| near_impossible | hybrid_llm_human | 1926.35 | 0.175 | 0.694 |
| near_impossible | llm_agent | 1711.21 | 1.000 | 0.873 |
| near_impossible | rule_system | 1814.42 | 1.000 | 0.802 |
| tight | human_planner | 2150.91 | 0.341 | 0.684 |
| tight | hybrid_llm_human | 1936.43 | 0.853 | 0.824 |
| tight | llm_agent | 1992.64 | 1.000 | 0.830 |
| tight | rule_system | 2019.75 | 1.000 | 0.783 |

## Interpretation

- This design makes timing matter through action cutoffs rather than compressing physical lead times into hours.
- The simulation uses a 10-day horizon and calibrated initial supply so absolute service levels remain interpretable.
- Service loss is reported against a no-disruption baseline using the same demand path.
- The rule-based system is a strong automatic baseline on known templates, but it is brittle when supplier language is buried or corrected.
- The pure LLM arm reflects the current Gemini extraction quality; the hybrid arm estimates the value of using LLMs as fast triage plus human verification.
- The fair adoption comparison is among LLM, rule-system, human, and hybrid arms; oracle is only a lower-bound reference.