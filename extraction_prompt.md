You are extracting an actionable supply disruption signal from a packet of supplier emails.

Return JSON only. Do not explain your answer.

Task:
- Read the full packet of emails.
- Decide whether there is an actionable disruption affecting the focal planning window.
- If yes, identify the decisive email and extract the structured fields.
- Prefer the latest corrective message when multiple emails conflict.
- Ignore distractors involving the wrong SKU, the wrong location, or already-resolved issues.
- Infer dates when suppliers use relative timing such as weekday slots, "this Friday," or "next Thursday's truck."
- Infer affected quantity when suppliers describe case packs, pallet counts, or held balances instead of plain unit totals.

Output rules:
- Follow the provided JSON schema exactly.
- If there is no actionable disruption, set `actionable` to `false` and leave extraction fields `null`.
- Use the exact `email_id` of the decisive email when one exists.
- `disruption_type` must be one of:
  - `lead_time_delay`
  - `partial_shipment`
  - `shipment_cancellation`
  - `corrected_update`

Fields to extract:
- actionable
- decisive_email_id
- focal_sku
- affected_location
- disruption_type
- original_eta
- revised_eta
- delay_days
- quantity_affected
- confidence
