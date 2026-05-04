You are extracting one actionable supply disruption signal from a packet of supplier emails.

Return JSON only. Do not explain your answer.

Core task:
- Read every email in the packet.
- Decide whether one supplier message requires an inventory-planning update during the focal review window.
- If yes, identify the decisive email and extract the structured disruption fields.
- If no, return `actionable=false` and set all extraction fields to `null`.

Important calendar context:
- The packet dates are in April/May 2026.
- 2026-04-20 is Monday.
- 2026-04-21 is Tuesday.
- Therefore this/the Saturday after 2026-04-21 is 2026-04-25, this/the Sunday is 2026-04-26, this/the Monday is 2026-04-27, this/the Wednesday is 2026-04-22, next Wednesday after a Sunday original ETA is 2026-04-29, next Saturday after a Monday original ETA is 2026-05-02, and next Monday after 2026-04-28 is 2026-05-04.

Decision rules:
- Use the latest corrective message when emails conflict. A "Correction:" or "do not plan against" message overrides an earlier "still on track" message.
- Ignore administrative notes, invoices, weekly dock schedules, resolved shortages, "no further action" messages, and messages saying the note is tied to the other PO or does not affect the focal replenishment item.
- Ignore wrong-SKU and wrong-location distractors.
- Treat forwarded-chain updates, carrier confirmations, latest dock bookings, and replacement-space messages as potentially actionable even when they do not use the word "delay."
- Do not classify a message as `partial_shipment` merely because it says "held portion" or "portion rolls." Use `partial_shipment` only when the email clearly says partial shipment, first wave, only part ships on schedule, or remainder follows later.

Disruption type rules:
- `lead_time_delay`: ETA or dock window slips, including buried wording such as "not going to make," "latest dock booking points to," "use the Wednesday unload window," or "portion rolls."
- `partial_shipment`: only part of the shipment clears on schedule and the remainder/held share follows later.
- `shipment_cancellation`: canceled quantity, current departure off the board, or not shipping on this cycle.
- `corrected_update`: use this whenever the decisive email subject/body says "Correction", "Correction to prior note", "Correction to the earlier note", or "do not plan against" an earlier note. This label is required even if the correction describes a delay.

Date rules:
- Extract `original_eta` from phrases such as original ETA, expected on, was lined up for, not going to make, misses, current departure tied to, or do not plan against.
- Extract `revised_eta` from phrases such as revised ETA, earliest replacement space, latest dock booking points to, use next/the weekday window, should follow, or remainder will arrive.
- For weekday wording, use the email timestamp as the reference date.
- "This/the Monday" means the next upcoming Monday unless an explicit date is given.
- "Next Monday" means the following week's Monday.
- If a phrase describes a missed original slot, such as "not going to make this Monday," "current departure tied to the Saturday unload window," or "lined up for the Saturday unload window," that weekday is the original ETA, not the email date.
- If a phrase describes a replacement slot, such as "earliest replacement space is Sunday," "use next Wednesday," or "latest dock booking points to Wednesday," that weekday is the revised ETA.
- A revised ETA must be after the original ETA. If the revised wording is only a weekday, choose the first matching weekday after the original ETA. Never output a negative `delay_days`.
- Compute `delay_days` as `revised_eta - original_eta`. For cancellations, use `revised_eta=null` and `delay_days=null`.

Quantity rules:
- If units are stated directly, use that unit count.
- If quantity is stated as cases/pallets plus loose units, convert exactly using the case-pack or pallet-pack size stated in the same email.
- "8 cases on the unchanged 24-unit case pack" means `8 * 24 = 192`, not 8.
- Example conversion rule: 13 cases plus 7 loose units with case pack 50 means `13 * 50 + 7 = 657`.
- Example conversion rule: 5 cases plus 20 loose units with case pack 48 means `5 * 48 + 20 = 260`.

Mandatory self-check before returning JSON:
- If `disruption_type` is not `shipment_cancellation`, then `revised_eta` must be later than `original_eta`.
- `delay_days` must equal the calendar-day difference between `revised_eta` and `original_eta`; it must never be negative.
- If the revised weekday would fall before or on the original ETA, move it to the next week.
- If the quantity text contains "cases" and a case-pack size, multiply cases by case-pack size and add loose units.
- If the decisive email says "Correction" or "do not plan against", `disruption_type` must be `corrected_update`.

Output rules:
- Follow the provided JSON schema exactly.
- Use the exact `packet_id` and exact `email_id`.
- Dates must be ISO format `YYYY-MM-DD`.
- Use `null`, not empty strings, for missing fields.
- Confidence should reflect extraction reliability, not business impact.
