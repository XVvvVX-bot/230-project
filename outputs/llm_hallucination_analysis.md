# LLM Hallucination / Confabulation Analysis

## Why hallucination matters in this experiment

In this project, the LLM is not allowed to choose the reorder, expedite, or reallocation action directly. Its role is narrower: read a noisy supplier-email packet and extract structured disruption fields. Hallucination is therefore not mainly a problem of the model inventing a long narrative. The more relevant risk is **schema-valid but semantically wrong extraction**: the output JSON looks usable, but one or more values are not supported by the email evidence.

This is consistent with the risk-management framing in NIST's Generative AI Profile, which treats confabulation as a generative-AI risk category and emphasizes testing and validation before deployment in consequential decision workflows. Google Gemini's structured-output documentation also makes the same practical point: a schema can enforce valid JSON format, but application code still needs to validate whether the values are correct for the business task.

Sources:

- NIST, [Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence), 2024.
- NIST, [AI Risk Management Framework 1.0](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10), 2023.
- Google AI for Developers, [Structured Outputs | Gemini API](https://ai.google.dev/gemini-api/docs/structured-output), last updated 2026.

## Evidence from the scored experiment

Gemini achieved a packet-level exact match of `61.7%` on the 60 held-out scored packets. That means `23` packets had at least one extraction error. The errors were not evenly distributed across fields:

| Error type | Count across 60 packets | Interpretation |
|---|---:|---|
| `delay_days` wrong | 13 | Most common failure; date arithmetic and relative-date interpretation are fragile. |
| `original_eta` wrong | 11 | The model sometimes anchored relative phrases to the email timestamp rather than the intended delivery window. |
| `revised_eta` wrong | 9 | Follow-up timing such as "next Sunday" or "Tuesday unload window" was sometimes mapped to the wrong calendar date. |
| `quantity_affected` wrong | 6 | Case-pack arithmetic was occasionally wrong. |
| Full actionable-thread miss | 1 | One high-noise packet was classified as not actionable even though the gold label contained a real delay. |

The strongest pattern is that hallucination is mostly **temporal** rather than entity-based. The model usually found the correct email, SKU, location, and disruption type, but it sometimes produced a wrong date or delay value after reading relative language.

## Error categories

| Category | Packets affected | Example packets | Operational risk |
|---|---:|---|---|
| Temporal inference error | 21 | `S021`, `S024`, `S058`, `S060` | Wrong delay length changes whether the policy expedites, reallocates, or waits. |
| Quantity arithmetic error | 6 | `S008`, `S011`, `S012`, `S021`, `S044`, `S059` | Wrong affected quantity changes reorder size and the expected shortage exposure. |
| False negative / missed disruption | 1 | `S059` | The policy receives no disruption signal and behaves as if the inbound order is still normal. |
| Thread/entity selection error | 1 | `S059` | The model failed to select the decisive actionable thread. |

## Representative examples

### 1. Relative-date hallucination can create impossible timing

Packet `S060` is a high-noise buried-delay case. The gold label is:

| Field | Gold | Gemini output |
|---|---:|---:|
| Original ETA | `2026-04-29` | `2026-04-22` |
| Revised ETA | `2026-05-05` | `2026-04-21` |
| Delay days | `6` | `-1` |

The model extracted a negative delay even though the supplier email described a later receiving window. This is an operational hallucination because the output is syntactically valid JSON but violates the business meaning of a delay. A production system should reject this with a rule such as:

```text
if disruption_type is delay-like, revised_eta must be later than original_eta.
```

### 2. Case-pack arithmetic can be wrong

Packet `S008` says the held portion is `11` cases plus `23` loose units with a `36`-unit case pack. The gold quantity is:

```text
11 * 36 + 23 = 419 units
```

Gemini output `407` units. This is not a formatting failure; it is a numerical extraction/calculation error. In inventory control, this can directly understate the affected quantity and reduce the reorder or expedite response.

### 3. High-noise packets can cause false negatives

Packet `S059` is the clearest example of a consequential miss. The gold label identifies an actionable buried delay for `SKU-522-A` into `DC-NORTH`, but Gemini returned:

```json
{
  "actionable": false,
  "decisive_email_id": null,
  "focal_sku": null,
  "affected_location": null,
  "disruption_type": null
}
```

This is costly because the downstream policy receives no disruption input. The model does not merely estimate a field incorrectly; it suppresses the entire exception signal.

## Noise sensitivity

Hallucination risk increases with packet complexity:

| Noise tier | Packets | Packet exact-match rate |
|---|---:|---:|
| Low | 20 | 85.0% |
| Medium | 20 | 55.0% |
| High | 20 | 45.0% |

This result supports a more nuanced conclusion than "LLMs work" or "LLMs fail." The LLM performs well when the decisive email is clear, but accuracy deteriorates when the packet includes buried timing language, relative dates, correction threads, or multiple distractors.

## Confidence is not reliable enough by itself

The model's self-reported confidence was poorly calibrated:

| Packet group | Average Gemini confidence |
|---|---:|
| Exact-match packets | 0.932 |
| Packets with at least one extraction error | 0.922 |

The difference is too small to use confidence as a stand-alone safety gate. In other words, the LLM often remains highly confident even when the extracted field values are wrong. The experiment should therefore frame confidence as a weak diagnostic, not a control mechanism.

## Implication for the experiment result

The hallucination analysis explains why the hybrid arm is strongest in the current experiment. The `llm_agent` arm benefits from immediate reading of supplier emails, but it still carries extraction-error risk. The `hybrid_llm_human` arm keeps the speed advantage while adding a targeted human review step, which helps catch high-impact hallucinations before the policy executes.

Current mean total cost by non-oracle arm:

| Arm | Mean total cost | Interpretation |
|---|---:|---|
| Hybrid LLM + Human | `$1,868.52` | Lowest non-oracle cost; balances speed and verification. |
| LLM Agent | `$1,913.06` | Fastest fully automated signal processing, but exposed to hallucinated fields. |
| Rule System | `$1,983.83` | Stable and cheap, but brittle on flexible language. |
| Human Planner | `$2,033.00` | Accurate when processed, but slower and exposed to missed-email risk. |

## Recommended report language

The report should not claim that LLMs are fully reliable autonomous planners. A stronger and more defensible claim is:

> The experiment shows that LLMs can improve supply-chain exception response when used as a fast information-extraction layer, but hallucination remains a material operational risk. In this setting, hallucination mainly appears as wrong dates, delay lengths, and affected quantities rather than invented prose. The best-performing design is therefore not full automation, but a hybrid workflow in which the LLM flags and structures disruption information while business-rule validation and selective human review check high-impact fields before inventory actions are executed.

## Practical controls

For a real deployment, the experiment suggests the following controls:

| Control | Purpose |
|---|---|
| Date-consistency validation | Reject negative or impossible delays. |
| Case-pack arithmetic validation | Recompute quantities from cases and loose units instead of trusting the LLM number directly. |
| Evidence trace requirement | Require the decisive email ID and source phrase for each critical field. |
| Human review for high-noise packets | Escalate correction threads, ambiguous timing, and high-value shortages. |
| Confidence calibration testing | Do not rely on model confidence until calibrated against held-out examples. |
| Post-deployment monitoring | Track packet-level exact match, field-level errors, and cost impact over time. |

