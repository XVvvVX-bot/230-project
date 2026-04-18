from __future__ import annotations

import json
import random
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List


SEED = 230
BASE_DATE = date(2026, 4, 20)

ACTIONABLE_PATTERNS = [
    "lead_time_delay",
    "partial_shipment",
    "shipment_cancellation",
    "corrected_update",
    "ambiguous_buried_delay",
]

NOISE_TIERS = {
    "low": {"emails": 5, "distractors": 3, "ambiguity": "low"},
    "medium": {"emails": 6, "distractors": 4, "ambiguity": "medium"},
    "high": {"emails": 8, "distractors": 6, "ambiguity": "high"},
}

VENDORS = [
    "Atlas Components",
    "BluePeak Foods",
    "North Harbor Supply",
    "Keystone Distribution",
    "Pioneer Imports",
    "Summit Ingredients",
]

CONTACTS = [
    "Elena Ruiz",
    "Marcus Chen",
    "Priya Nair",
    "Liam Foster",
    "Jada Brooks",
    "Noah Patel",
]

LOCATIONS = ["DC-WEST", "DC-EAST", "DC-CENTRAL", "DC-SOUTH", "DC-NORTH"]
DISTRACTOR_TYPES = ["irrelevant_chatter", "wrong_sku", "resolved_issue", "admin_note"]


def iso(d: date) -> str:
    return d.isoformat()


def ensure_data_dir(root: Path) -> Path:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def write_jsonl(path: Path, rows: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_inventory_records(rng: random.Random, focal_sku: str, focal_location: str, n_records: int) -> List[Dict]:
    other_locations = [loc for loc in LOCATIONS if loc != focal_location]
    records = []

    demand_mean = rng.randint(80, 145)
    demand_sd = max(12, int(round(demand_mean * rng.uniform(0.18, 0.32))))
    lead_time = rng.randint(5, 9)
    on_hand = rng.randint(int(0.25 * demand_mean * lead_time), int(0.55 * demand_mean * lead_time))
    on_order = rng.randint(int(0.45 * demand_mean * lead_time), int(0.85 * demand_mean * lead_time))
    shortage_cost = round(rng.uniform(2.5, 5.0), 2)
    holding_cost = round(rng.uniform(0.3, 0.9), 2)

    records.append(
        {
            "sku": focal_sku,
            "location": focal_location,
            "demand_mean": demand_mean,
            "demand_std": demand_sd,
            "lead_time_days": lead_time,
            "current_inventory": on_hand,
            "on_order_qty": on_order,
            "shortage_cost": shortage_cost,
            "holding_cost": holding_cost,
        }
    )

    if n_records >= 2:
        records.append(
            {
                "sku": focal_sku,
                "location": rng.choice(other_locations),
                "demand_mean": max(40, demand_mean - rng.randint(5, 30)),
                "demand_std": max(10, demand_sd - rng.randint(0, 5)),
                "lead_time_days": max(4, lead_time - rng.randint(0, 2)),
                "current_inventory": rng.randint(int(0.8 * on_hand), int(1.15 * on_hand)),
                "on_order_qty": rng.randint(int(0.3 * on_order), int(0.8 * on_order)),
                "shortage_cost": shortage_cost,
                "holding_cost": holding_cost,
            }
        )

    while len(records) < n_records:
        sku = f"SKU-{rng.randint(100,999)}-{chr(65 + len(records))}"
        location = rng.choice(LOCATIONS)
        dm = rng.randint(60, 140)
        ds = max(10, int(round(dm * rng.uniform(0.15, 0.3))))
        lt = rng.randint(4, 10)
        records.append(
            {
                "sku": sku,
                "location": location,
                "demand_mean": dm,
                "demand_std": ds,
                "lead_time_days": lt,
                "current_inventory": rng.randint(int(0.25 * dm * lt), int(0.65 * dm * lt)),
                "on_order_qty": rng.randint(int(0.35 * dm * lt), int(0.9 * dm * lt)),
                "shortage_cost": round(rng.uniform(1.2, 3.5), 2),
                "holding_cost": round(rng.uniform(0.25, 0.8), 2),
            }
        )

    return records


def decisive_subject(pattern: str, sku: str) -> str:
    mapping = {
        "lead_time_delay": f"Updated ETA for {sku}",
        "partial_shipment": f"Partial shipment notice for {sku}",
        "shipment_cancellation": f"Shipment cancellation on {sku}",
        "corrected_update": f"Correction: revised timing for {sku}",
        "ambiguous_buried_delay": f"Thread update on PO status for {sku}",
    }
    return mapping[pattern]


def weekday_name(d: date) -> str:
    return d.strftime("%A")


def date_hint(target: date, anchor: date, tier: str, rng: random.Random, allow_explicit: bool = True) -> str:
    weekday = weekday_name(target)
    delta = (target - anchor).days
    if tier == "low":
        return iso(target)

    if delta <= 7:
        relative = f"this {weekday.lower()}"
    elif delta <= 14:
        relative = f"next {weekday.lower()}"
    else:
        relative = f"the {weekday.lower()} after next"

    if tier == "medium":
        options = [
            f"{relative} ({iso(target)})" if allow_explicit else relative,
            f"the {weekday.lower()} slot" if not allow_explicit else f"the {weekday.lower()} slot on {iso(target)}",
            relative,
        ]
        return rng.choice(options)

    options = [
        f"{relative}'s truck",
        f"the {weekday.lower()} unload window",
        f"{relative}",
    ]
    return rng.choice(options)


def quantity_hint(quantity: int, tier: str, rng: random.Random) -> str:
    if tier == "low":
        return f"{quantity} units"

    pack_sizes = [6, 8, 10, 12, 15, 20, 24, 25, 30, 36, 40, 48, 50]
    pack = rng.choice(pack_sizes)
    cases, loose = divmod(quantity, pack)

    if tier == "medium":
        if cases >= 2 and loose == 0:
            return f"{cases} cases at {pack} units each"
        if cases >= 1:
            return f"{cases} cases plus {loose} loose units on the usual {pack}-unit case pack"
        return f"{quantity} loose units"

    if cases >= 2 and loose == 0:
        return f"{cases} cases on the unchanged {pack}-unit case pack"
    if cases >= 1:
        return f"{cases} cases plus {loose} loose units, with case pack still at {pack}"
    return f"{quantity} loose units"


def distractor_email(
    rng: random.Random,
    packet_id: str,
    email_idx: int,
    sku_choices: List[str],
    focal_location: str,
    focal_eta: date,
    noise_tier: str,
) -> Dict:
    kind = rng.choice(DISTRACTOR_TYPES)
    wrong_sku = rng.choice([sku for sku in sku_choices if sku])
    sender = rng.choice(CONTACTS)
    vendor = rng.choice(VENDORS)
    ts = BASE_DATE + timedelta(hours=email_idx * 3 + rng.randint(0, 2))

    if kind == "irrelevant_chatter":
        subject = f"Weekly dock schedule for {focal_location}"
        body = (
            f"Hi team,\n\nSharing next week's dock windows and pallet counts. "
            f"No changes to confirmed inbound orders at this time.\n\nThanks,\n{sender}"
        )
    elif kind == "wrong_sku":
        subject = f"ETA slip for {wrong_sku}"
        if noise_tier == "low":
            body = (
                f"Please note {wrong_sku} is now expected on {iso(focal_eta + timedelta(days=2))}. "
                f"This note does not affect the focal replenishment item.\n\n{sender}"
            )
        else:
            shifted = focal_eta + timedelta(days=2)
            body = (
                f"For {wrong_sku}, we are now looking at {date_hint(shifted, BASE_DATE + timedelta(days=1), noise_tier, rng, allow_explicit=False)}. "
                f"This is tied to the other PO, not the focal planning line.\n\n{sender}"
            )
    elif kind == "resolved_issue":
        subject = f"Resolved shortage on {wrong_sku}"
        if noise_tier == "low":
            body = (
                f"The backlog on {wrong_sku} has been cleared and the original ETA of "
                f"{iso(focal_eta)} stands. No further action is needed.\n\n{sender}"
            )
        else:
            body = (
                f"The hold on {wrong_sku} is cleared. Keep {date_hint(focal_eta, BASE_DATE + timedelta(days=1), noise_tier, rng, allow_explicit=False)} as the receipt window; "
                f"nothing else needs to move on that line.\n\n{sender}"
            )
    else:
        subject = f"Invoice and customs reference for {vendor}"
        body = (
            f"Attached are the customs and invoice details for last week's shipment. "
            f"This is an administrative note only.\n\n{sender}"
        )

    return {
        "email_id": f"{packet_id}-E{email_idx:02d}",
        "thread_type": kind,
        "from": f"{sender} <{sender.lower().replace(' ', '.')}@{vendor.lower().replace(' ', '')}.com>",
        "subject": subject,
        "timestamp": f"{iso(ts)}T{(8 + email_idx) % 24:02d}:00:00",
        "body": body,
        "is_actionable": False,
    }


def build_actionable_thread(
    rng: random.Random,
    packet_id: str,
    pattern: str,
    focal_record: Dict,
    noise_tier: str,
    email_start_idx: int,
) -> Dict:
    sku = focal_record["sku"]
    location = focal_record["location"]
    base_eta = BASE_DATE + timedelta(days=focal_record["lead_time_days"])
    quantity_affected = min(
        focal_record["on_order_qty"],
        max(60, int(round(focal_record["on_order_qty"] * rng.uniform(0.50, 0.95)))),
    )
    delay_days = rng.randint(3, 6)
    revised_eta = base_eta + timedelta(days=delay_days)
    sender = rng.choice(CONTACTS)
    vendor = rng.choice(VENDORS)
    email_anchor = BASE_DATE + timedelta(days=1)
    original_hint = date_hint(base_eta, email_anchor, noise_tier, rng, allow_explicit=noise_tier == "medium")
    revised_hint = date_hint(revised_eta, email_anchor, noise_tier, rng, allow_explicit=noise_tier == "medium")
    qty_hint = quantity_hint(quantity_affected, noise_tier, rng)

    decisive_email = {
        "email_id": f"{packet_id}-E{email_start_idx:02d}",
        "thread_type": "actionable",
        "from": f"{sender} <{sender.lower().replace(' ', '.')}@{vendor.lower().replace(' ', '')}.com>",
        "subject": decisive_subject(pattern, sku),
        "timestamp": f"{iso(BASE_DATE + timedelta(days=1))}T09:00:00",
        "body": "",
        "is_actionable": True,
    }

    disruption_type = pattern

    if pattern == "lead_time_delay":
        if noise_tier == "low":
            decisive_email["body"] = (
                f"Team,\n\nThe inbound order for {sku} into {location} is delayed. "
                f"Original ETA was {iso(base_eta)} and the revised ETA is {iso(revised_eta)}. "
                f"The impacted quantity is {quantity_affected} units.\n\nRegards,\n{sender}"
            )
        else:
            decisive_email["body"] = (
                f"Team,\n\nWe are not going to make {original_hint} for {sku} into {location}. "
                f"Earliest replacement space is {revised_hint}. "
                f"The held portion is {qty_hint}.\n\nRegards,\n{sender}"
            )
    elif pattern == "partial_shipment":
        if noise_tier == "low":
            decisive_email["body"] = (
                f"Please note only a partial shipment will leave on schedule for {sku} into {location}. "
                f"{quantity_affected} units will miss the original ETA of {iso(base_eta)}. "
                f"The remainder will arrive on {iso(revised_eta)}.\n\n{sender}"
            )
        else:
            decisive_email["body"] = (
                f"Only the first wave will clear for {sku} into {location}. "
                f"The held portion is {qty_hint}; that share misses {original_hint} and should follow on {revised_hint}.\n\n{sender}"
            )
        disruption_type = "partial_shipment"
    elif pattern == "shipment_cancellation":
        if noise_tier == "low":
            decisive_email["body"] = (
                f"We have to cancel {quantity_affected} units on the current shipment for {sku} to {location}. "
                f"The canceled quantity will not arrive on {iso(base_eta)} and must be rescheduled.\n\n{sender}"
            )
        else:
            decisive_email["body"] = (
                f"The current departure tied to the {original_hint} window is off the board for {sku} into {location}. "
                f"For planning purposes, the held portion is {qty_hint}, and it is not shipping on this cycle.\n\n{sender}"
            )
        revised_eta = None
        delay_days = None
        disruption_type = "shipment_cancellation"
    elif pattern == "corrected_update":
        first_email = deepcopy(decisive_email)
        first_email["email_id"] = f"{packet_id}-E{email_start_idx:02d}"
        first_email["subject"] = f"Initial ETA note for {sku}"
        first_email["timestamp"] = f"{iso(BASE_DATE + timedelta(days=1))}T08:00:00"
        first_email["body"] = (
            f"Initial note: the order for {sku} to {location} is still on track for {iso(base_eta)}. "
            f"Please ignore if a formal correction follows.\n\n{sender}"
        )
        decisive_email["email_id"] = f"{packet_id}-E{email_start_idx + 1:02d}"
        decisive_email["timestamp"] = f"{iso(BASE_DATE + timedelta(days=1))}T10:00:00"
        if noise_tier == "low":
            decisive_email["body"] = (
                f"Correction to prior note: {sku} to {location} is delayed by {delay_days} days. "
                f"Original ETA {iso(base_eta)}; revised ETA {iso(revised_eta)}. "
                f"Affected quantity: {quantity_affected} units.\n\n{sender}"
            )
        else:
            decisive_email["body"] = (
                f"Correction to the earlier note: do not plan against the {original_hint} receipt for {sku} into {location}. "
                f"Use {revised_hint} instead. "
                f"The impacted portion is the same held balance as before: {qty_hint}.\n\n{sender}"
            )
        return {
            "emails": [first_email, decisive_email],
            "gold": {
                "actionable": True,
                "decisive_email_id": decisive_email["email_id"],
                "focal_sku": sku,
                "affected_location": location,
                "disruption_type": "corrected_update",
                "original_eta": iso(base_eta),
                "revised_eta": iso(revised_eta),
                "delay_days": delay_days,
                "quantity_affected": quantity_affected,
            },
            "contradiction_present": True,
            "ambiguity_level": noise_tier,
        }
    else:
        buried_phrase = [
            f"the receiving team should now work off {revised_hint}",
            f"the latest dock booking points to {revised_hint}",
            f"if planning needs a firm date, use {revised_hint}",
        ]
        if noise_tier == "low":
            decisive_email["body"] = (
                f"Forwarded chain below. The PO for {sku} into {location} was expected on {iso(base_eta)}. "
                f"After carrier confirmation, {rng.choice(buried_phrase)}. "
                f"The delayed quantity is {quantity_affected} units. "
                f"Please update planning only if this affects the coming review cycle.\n\n{sender}"
            )
        else:
            decisive_email["body"] = (
                f"Forwarded chain below. The PO for {sku} into {location} had been lined up for {original_hint}. "
                f"After carrier confirmation, {rng.choice(buried_phrase)}. "
                f"The portion that rolls is not the whole PO; the held portion is {qty_hint}. "
                f"Please update planning only if this affects the coming review cycle.\n\n{sender}"
            )
        disruption_type = "lead_time_delay"

    return {
        "emails": [decisive_email],
        "gold": {
            "actionable": True,
            "decisive_email_id": decisive_email["email_id"],
            "focal_sku": sku,
            "affected_location": location,
            "disruption_type": disruption_type,
            "original_eta": iso(base_eta),
            "revised_eta": iso(revised_eta) if revised_eta else None,
            "delay_days": delay_days,
            "quantity_affected": quantity_affected,
        },
        "contradiction_present": pattern == "corrected_update",
        "ambiguity_level": noise_tier,
    }


def generate_packet(packet_id: str, split: str, pattern: str, noise_tier: str, replicate: int, rng: random.Random) -> Dict:
    focal_sku = f"SKU-{rng.randint(200,899)}-A"
    focal_location = rng.choice(LOCATIONS)
    n_records = rng.randint(3, 5)
    inventory_records = build_inventory_records(rng, focal_sku, focal_location, n_records)
    focal_record = inventory_records[0]
    actionable = build_actionable_thread(rng, packet_id, pattern, focal_record, noise_tier, email_start_idx=1)

    sku_choices = [record["sku"] for record in inventory_records]
    base_eta = BASE_DATE + timedelta(days=focal_record["lead_time_days"])
    target_email_count = NOISE_TIERS[noise_tier]["emails"]
    emails = actionable["emails"][:]

    next_idx = len(emails) + 1
    while len(emails) < target_email_count:
        emails.append(distractor_email(rng, packet_id, next_idx, sku_choices, focal_location, base_eta, noise_tier))
        next_idx += 1

    rng.shuffle(emails)
    emails = sorted(emails, key=lambda x: x["timestamp"])

    for idx, email in enumerate(emails, 1):
        if not email["email_id"].startswith(packet_id):
            email["email_id"] = f"{packet_id}-E{idx:02d}"
        elif email["email_id"] != f"{packet_id}-E{idx:02d}" and not email["is_actionable"]:
            email["email_id"] = f"{packet_id}-E{idx:02d}"

    old_to_new = {}
    for idx, email in enumerate(emails, 1):
        previous = email["email_id"]
        new_id = f"{packet_id}-E{idx:02d}"
        old_to_new[previous] = new_id
        email["email_id"] = new_id

    gold = actionable["gold"]
    gold["decisive_email_id"] = old_to_new.get(gold["decisive_email_id"], gold["decisive_email_id"])

    return {
        "packet_id": packet_id,
        "split": split,
        "pattern": pattern,
        "noise_tier": noise_tier,
        "replicate": replicate,
        "packet_metadata": {
            "num_emails": len(emails),
            "num_sku_locations": len(inventory_records),
            "distractor_count": len(emails) - len(actionable["emails"]),
            "contradiction_present": actionable["contradiction_present"],
            "ambiguity_level": actionable["ambiguity_level"],
        },
        "inventory_records": inventory_records,
        "surplus_pool_qty": rng.randint(60, 260),
        "emails": emails,
        "gold": gold,
    }


def generate_dataset() -> Dict[str, List[Dict]]:
    rng = random.Random(SEED)
    scored = []
    packet_num = 1
    for pattern in ACTIONABLE_PATTERNS:
        for noise_tier in NOISE_TIERS:
            for replicate in range(1, 5):
                packet_id = f"S{packet_num:03d}"
                scored.append(generate_packet(packet_id, "scored", pattern, noise_tier, replicate, rng))
                packet_num += 1

    pilot_specs = [
        ("lead_time_delay", "low"),
        ("lead_time_delay", "high"),
        ("partial_shipment", "medium"),
        ("shipment_cancellation", "low"),
        ("shipment_cancellation", "high"),
        ("corrected_update", "medium"),
        ("corrected_update", "high"),
        ("ambiguous_buried_delay", "low"),
        ("ambiguous_buried_delay", "high"),
        ("partial_shipment", "low"),
        ("lead_time_delay", "medium"),
        ("corrected_update", "low"),
    ]
    pilot = []
    for idx, (pattern, noise_tier) in enumerate(pilot_specs, 1):
        packet_id = f"P{idx:03d}"
        pilot.append(generate_packet(packet_id, "pilot", pattern, noise_tier, idx, rng))

    return {"pilot": pilot, "scored": scored}


def main() -> None:
    root = Path(__file__).resolve().parent
    data_dir = ensure_data_dir(root)
    dataset = generate_dataset()
    write_jsonl(data_dir / "pilot_packets.jsonl", dataset["pilot"])
    write_jsonl(data_dir / "scored_packets.jsonl", dataset["scored"])

    print("Packet files written to:")
    print(f"- {data_dir / 'pilot_packets.jsonl'}")
    print(f"- {data_dir / 'scored_packets.jsonl'}")


if __name__ == "__main__":
    main()
