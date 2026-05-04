from __future__ import annotations

import csv
import json
import math
import os
import random
import statistics
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from rule_based_extractor import CRITICAL_KEYS, extract_packet, read_jsonl, score_predictions, write_jsonl


SEED = 230
BASE_DATE = date(2026, 4, 20)
BASE_DATETIME = datetime(2026, 4, 20, 0, 0, 0)
SERVICE_Z = 1.645

SIM_RUNS = int(os.environ.get("CUTOFF_SIM_RUNS", "100"))
HORIZON_DAYS = int(os.environ.get("CUTOFF_HORIZON_DAYS", "10"))

# Cost basis:
# - Human labor is anchored to BLS logistician wages: $80,880/year ~= $38.9/hour.
#   A 1.30 loaded-labor multiplier gives roughly $50/hour.
# - Gemini Flash-Lite token prices are cents or less for these packets, so LLM/rule
#   costs are modeled as small all-in automated processing costs rather than labor costs.
LOADED_PLANNER_HOURLY_COST = float(os.environ.get("CUTOFF_LOADED_PLANNER_HOURLY_COST", "50.0"))
HUMAN_REVIEW_MINUTES = float(os.environ.get("CUTOFF_HUMAN_REVIEW_MINUTES", "30.0"))
HYBRID_APPROVAL_MINUTES = float(os.environ.get("CUTOFF_HYBRID_APPROVAL_MINUTES", "10.0"))

LLM_PROCESSING_COST = float(os.environ.get("CUTOFF_LLM_PROCESSING_COST", "0.25"))
RULE_PROCESSING_COST = float(os.environ.get("CUTOFF_RULE_PROCESSING_COST", "0.10"))
HUMAN_PROCESSING_COST = float(
    os.environ.get("CUTOFF_HUMAN_PROCESSING_COST", str(LOADED_PLANNER_HOURLY_COST * HUMAN_REVIEW_MINUTES / 60.0))
)
HYBRID_PROCESSING_COST = float(
    os.environ.get(
        "CUTOFF_HYBRID_PROCESSING_COST",
        str(LLM_PROCESSING_COST + LOADED_PLANNER_HOURLY_COST * HYBRID_APPROVAL_MINUTES / 60.0),
    )
)

LLM_DELAY_DAYS = float(os.environ.get("CUTOFF_LLM_DELAY_DAYS", "0.05"))
RULE_DELAY_DAYS = float(os.environ.get("CUTOFF_RULE_DELAY_DAYS", "0.05"))
HUMAN_DELAY_DISTRIBUTION = [(0.5, 0.20), (1.0, 0.35), (2.0, 0.30), (3.0, 0.15)]
HYBRID_APPROVAL_DISTRIBUTION = [(0.25, 0.50), (0.5, 0.35), (1.0, 0.15)]

HUMAN_MISS_BY_NOISE = {"low": 0.04, "medium": 0.10, "high": 0.18}
SLACK_TIERS = {
    "easy": (3.0, 5.0, 0.25),
    "moderate": (1.5, 3.0, 0.35),
    "tight": (0.5, 1.5, 0.30),
    "near_impossible": (0.0, 0.5, 0.10),
}

ARMS = ["oracle", "llm_agent", "rule_system", "human_planner", "hybrid_llm_human"]


@dataclass
class ArmRun:
    arm: str
    action: str
    total_cost: float
    stockout_cost: float
    holding_cost: float
    action_cost: float
    processing_cost: float
    service_level: float
    service_loss_vs_baseline: float
    shortage_units: float
    holding_units: float
    detection_delay_days: float
    detected_before_cutoff: bool
    missed_signal: bool
    extraction_exact: bool


def write_json(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def normalize_signal(signal: Optional[Dict]) -> Dict:
    if not signal or not signal.get("actionable"):
        return empty_signal()
    required = ["focal_sku", "affected_location", "disruption_type"]
    if any(not signal.get(key) for key in required):
        return empty_signal()
    normalized = deepcopy(signal)
    normalized.setdefault("original_eta", None)
    normalized.setdefault("revised_eta", None)
    normalized.setdefault("delay_days", None)
    normalized.setdefault("quantity_affected", None)
    return normalized


def empty_signal() -> Dict:
    return {
        "actionable": False,
        "decisive_email_id": None,
        "focal_sku": None,
        "affected_location": None,
        "disruption_type": None,
        "original_eta": None,
        "revised_eta": None,
        "delay_days": None,
        "quantity_affected": None,
    }


def exact_match(packet: Dict, prediction: Dict) -> bool:
    return all(packet["gold"].get(key) == prediction.get(key) for key in CRITICAL_KEYS)


def day_from_iso(value: Optional[str], fallback: int) -> int:
    if not value:
        return max(1, fallback)
    return max(1, (date.fromisoformat(value) - BASE_DATE).days)


def signal_arrival_day(packet: Dict) -> float:
    decisive_id = packet["gold"]["decisive_email_id"]
    decisive_email = next((email for email in packet["emails"] if email["email_id"] == decisive_id), None)
    if not decisive_email:
        return 1.0
    timestamp = datetime.fromisoformat(decisive_email["timestamp"])
    return max(0.0, (timestamp - BASE_DATETIME).total_seconds() / 86400.0)


def assign_cutoff_design(packets: List[Dict]) -> Dict[str, Dict]:
    rng = random.Random(SEED + 5000)
    shuffled = [packet["packet_id"] for packet in packets]
    rng.shuffle(shuffled)
    n = len(shuffled)
    counts = {
        "easy": round(n * SLACK_TIERS["easy"][2]),
        "moderate": round(n * SLACK_TIERS["moderate"][2]),
        "tight": round(n * SLACK_TIERS["tight"][2]),
    }
    counts["near_impossible"] = n - sum(counts.values())

    packet_to_tier = {}
    idx = 0
    for tier, count in counts.items():
        for packet_id in shuffled[idx : idx + count]:
            packet_to_tier[packet_id] = tier
        idx += count

    design = {}
    for packet in packets:
        tier = packet_to_tier[packet["packet_id"]]
        low, high, _ = SLACK_TIERS[tier]
        slack_rng = random.Random(SEED + int(packet["packet_id"][1:]) * 97)
        slack = slack_rng.uniform(low, high)
        arrival = signal_arrival_day(packet)
        design[packet["packet_id"]] = {
            "signal_arrival_day": arrival,
            "cutoff_tier": tier,
            "cutoff_slack_days": slack,
            "action_cutoff_day": arrival + slack,
        }
    return design


def sample_distribution(rng: random.Random, distribution: List[Tuple[float, float]]) -> float:
    roll = rng.random()
    cumulative = 0.0
    for value, probability in distribution:
        cumulative += probability
        if roll <= cumulative:
            return value
    return distribution[-1][0]


def true_receipts(record: Dict, gold_signal: Dict) -> Dict[int, float]:
    original_day = day_from_iso(gold_signal.get("original_eta"), int(record["lead_time_days"]))
    total = float(record["on_order_qty"])
    affected = min(total, float(gold_signal.get("quantity_affected") or 0.0))
    unaffected = max(0.0, total - affected)
    events: Dict[int, float] = defaultdict(float)
    if unaffected > 0:
        events[original_day] += unaffected
    dtype = gold_signal.get("disruption_type")
    if dtype in {"lead_time_delay", "corrected_update", "partial_shipment"}:
        revised_day = day_from_iso(gold_signal.get("revised_eta"), original_day + int(gold_signal.get("delay_days") or 0))
        events[revised_day] += affected
    elif dtype == "shipment_cancellation":
        pass
    else:
        events[original_day] += affected
    return dict(events)


def baseline_receipts(record: Dict, gold_signal: Dict) -> Dict[int, float]:
    original_day = day_from_iso(gold_signal.get("original_eta"), int(record["lead_time_days"]))
    return {original_day: float(record["on_order_qty"])}


def usable_signal(record: Dict, signal: Dict) -> Dict:
    signal = normalize_signal(signal)
    if not signal["actionable"]:
        return empty_signal()
    if signal.get("focal_sku") != record["sku"] or signal.get("affected_location") != record["location"]:
        return empty_signal()
    qty = float(signal.get("quantity_affected") or 0.0)
    if qty <= 0:
        return empty_signal()
    dtype = signal.get("disruption_type")
    if dtype != "shipment_cancellation" and int(signal.get("delay_days") or 0) <= 0:
        return empty_signal()
    return signal


def action_for_signal(
    packet: Dict,
    record: Dict,
    signal: Dict,
    detection_day: float,
    cutoff_day: float,
) -> Tuple[str, Dict[int, float], float]:
    signal = usable_signal(record, signal)
    if not signal["actionable"]:
        return "no_signal", {}, 0.0

    qty = min(float(signal.get("quantity_affected") or 0.0), float(record["on_order_qty"]))
    if qty <= 0:
        return "no_action", {}, 0.0

    before_cutoff = detection_day <= cutoff_day
    if before_cutoff:
        if packet["surplus_pool_qty"] >= 0.35 * qty:
            delivered = min(qty, float(packet["surplus_pool_qty"]))
            arrival_day = math.ceil(detection_day + 0.5)
            return "reallocate", {arrival_day: delivered}, 25.0 + 0.35 * delivered
        arrival_day = math.ceil(detection_day + 2.0)
        return "expedite", {arrival_day: qty}, 40.0 + 0.85 * qty

    arrival_day = math.ceil(detection_day + float(record["lead_time_days"]))
    return "standard_reorder_late", {arrival_day: qty}, 10.0 + 0.12 * qty


def demand_path(packet_idx: int, run_idx: int, record: Dict) -> List[float]:
    rng = random.Random(SEED + packet_idx * 10000 + run_idx)
    mean = float(record["demand_mean"])
    std = max(0.01, float(record["demand_std"]))
    return [max(0.0, rng.gauss(mean, std)) for _ in range(HORIZON_DAYS)]


def protection_stock(record: Dict) -> float:
    review_days = 1
    protection_days = int(record["lead_time_days"]) + review_days
    return (
        float(record["demand_mean"]) * protection_days
        + SERVICE_Z * float(record["demand_std"]) * math.sqrt(protection_days)
    )


def calibrated_record(record: Dict) -> Dict:
    adjusted = deepcopy(record)
    baseline_supply = protection_stock(record)
    adjusted["current_inventory"] = max(float(record["current_inventory"]), 0.45 * baseline_supply)
    adjusted["on_order_qty"] = max(float(record["on_order_qty"]), 0.55 * baseline_supply)
    return adjusted


def simulate_inventory(record: Dict, receipts: Dict[int, float], action_events: Dict[int, float], demand: List[float]) -> Dict:
    inbound: Dict[int, float] = defaultdict(float)
    for day, qty in receipts.items():
        if 0 <= day < HORIZON_DAYS:
            inbound[int(day)] += float(qty)
    for day, qty in action_events.items():
        if 0 <= day < HORIZON_DAYS:
            inbound[int(day)] += float(qty)

    inventory = float(record["current_inventory"])
    shortage_cost = 0.0
    holding_cost = 0.0
    shortage_units = 0.0
    holding_units = 0.0
    total_demand = 0.0
    for day in range(HORIZON_DAYS):
        inventory += inbound.get(day, 0.0)
        daily_demand = demand[day]
        total_demand += daily_demand
        shortage = max(0.0, daily_demand - inventory)
        inventory = max(0.0, inventory - daily_demand)
        shortage_units += shortage
        holding_units += inventory
        shortage_cost += shortage * float(record["shortage_cost"])
        holding_cost += inventory * float(record["holding_cost"])

    service_level = 1.0 if total_demand <= 0 else max(0.0, 1.0 - shortage_units / total_demand)
    return {
        "shortage_cost": shortage_cost,
        "holding_cost": holding_cost,
        "shortage_units": shortage_units,
        "holding_units": holding_units,
        "service_level": service_level,
    }


def arm_signal(
    arm: str,
    packet: Dict,
    llm_prediction: Dict,
    rule_prediction: Dict,
    rng: random.Random,
) -> Tuple[Dict, bool]:
    if arm == "oracle":
        return deepcopy(packet["gold"]), False
    if arm == "llm_agent":
        return normalize_signal(llm_prediction), False
    if arm == "rule_system":
        return normalize_signal(rule_prediction), False
    if arm == "human_planner":
        missed = rng.random() < HUMAN_MISS_BY_NOISE[packet["noise_tier"]]
        return (empty_signal() if missed else deepcopy(packet["gold"])), missed
    if arm == "hybrid_llm_human":
        llm_signal = normalize_signal(llm_prediction)
        if not llm_signal["actionable"]:
            return empty_signal(), True
        if (
            llm_signal.get("decisive_email_id") == packet["gold"].get("decisive_email_id")
            and llm_signal.get("focal_sku") == packet["gold"].get("focal_sku")
            and llm_signal.get("affected_location") == packet["gold"].get("affected_location")
        ):
            return deepcopy(packet["gold"]), False
        return llm_signal, False
    raise ValueError(f"Unknown arm: {arm}")


def arm_detection_day(arm: str, design: Dict, rng: random.Random) -> float:
    arrival = design["signal_arrival_day"]
    if arm == "oracle":
        return arrival
    if arm == "llm_agent":
        return arrival + LLM_DELAY_DAYS
    if arm == "rule_system":
        return arrival + RULE_DELAY_DAYS
    if arm == "human_planner":
        return arrival + sample_distribution(rng, HUMAN_DELAY_DISTRIBUTION)
    if arm == "hybrid_llm_human":
        return arrival + LLM_DELAY_DAYS + sample_distribution(rng, HYBRID_APPROVAL_DISTRIBUTION)
    raise ValueError(f"Unknown arm: {arm}")


def processing_cost(arm: str) -> float:
    return {
        "oracle": 0.0,
        "llm_agent": LLM_PROCESSING_COST,
        "rule_system": RULE_PROCESSING_COST,
        "human_planner": HUMAN_PROCESSING_COST,
        "hybrid_llm_human": HYBRID_PROCESSING_COST,
    }[arm]


def simulate_arm(
    packet_idx: int,
    packet: Dict,
    arm: str,
    llm_prediction: Dict,
    rule_prediction: Dict,
    design: Dict,
    run_idx: int,
) -> ArmRun:
    record = calibrated_record(packet["inventory_records"][0])
    rng = random.Random(SEED + 800000 + packet_idx * 10000 + run_idx * 17 + ARMS.index(arm))
    signal, missed = arm_signal(arm, packet, llm_prediction, rule_prediction, rng)
    detection = arm_detection_day(arm, design, rng)
    before_cutoff = detection <= design["action_cutoff_day"]

    demand = demand_path(packet_idx, run_idx, record)
    baseline_metrics = simulate_inventory(
        record=record,
        receipts=baseline_receipts(record, packet["gold"]),
        action_events={},
        demand=demand,
    )

    if arm == "oracle":
        action = "perfect_schedule"
        inventory_metrics = {
            "shortage_cost": 0.0,
            "holding_cost": 0.0,
            "shortage_units": 0.0,
            "holding_units": 0.0,
            "service_level": 1.0,
        }
        action_cost = 0.0
    else:
        action, events, action_cost = action_for_signal(
            packet=packet,
            record=record,
            signal=signal,
            detection_day=detection,
            cutoff_day=design["action_cutoff_day"],
        )
        inventory_metrics = simulate_inventory(
            record=record,
            receipts=true_receipts(record, packet["gold"]),
            action_events=events,
            demand=demand,
        )

    proc_cost = processing_cost(arm)
    total = inventory_metrics["shortage_cost"] + inventory_metrics["holding_cost"] + action_cost + proc_cost
    prediction = llm_prediction if arm in {"llm_agent", "hybrid_llm_human"} else rule_prediction
    if arm in {"oracle", "human_planner"}:
        extraction_is_exact = not missed
    else:
        extraction_is_exact = exact_match(packet, prediction)
    return ArmRun(
        arm=arm,
        action=action,
        total_cost=total,
        stockout_cost=inventory_metrics["shortage_cost"],
        holding_cost=inventory_metrics["holding_cost"],
        action_cost=action_cost,
        processing_cost=proc_cost,
        service_level=inventory_metrics["service_level"],
        service_loss_vs_baseline=max(0.0, baseline_metrics["service_level"] - inventory_metrics["service_level"]),
        shortage_units=inventory_metrics["shortage_units"],
        holding_units=inventory_metrics["holding_units"],
        detection_delay_days=detection - design["signal_arrival_day"],
        detected_before_cutoff=before_cutoff,
        missed_signal=missed,
        extraction_exact=extraction_is_exact,
    )


def summarize(rows: List[Dict], group_keys: List[str]) -> List[Dict]:
    groups: Dict[Tuple, List[Dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in group_keys)].append(row)

    output = []
    for key, group in sorted(groups.items()):
        item = {name: value for name, value in zip(group_keys, key)}
        item.update(
            {
                "runs": len(group),
                "mean_total_cost": statistics.mean(row["total_cost"] for row in group),
                "mean_cost_gap_vs_oracle": statistics.mean(row["cost_gap_vs_oracle"] for row in group),
                "mean_stockout_cost": statistics.mean(row["stockout_cost"] for row in group),
                "mean_holding_cost": statistics.mean(row["holding_cost"] for row in group),
                "mean_action_cost": statistics.mean(row["action_cost"] for row in group),
                "mean_processing_cost": statistics.mean(row["processing_cost"] for row in group),
                "mean_service_level": statistics.mean(row["service_level"] for row in group),
                "mean_service_loss_vs_baseline": statistics.mean(row["service_loss_vs_baseline"] for row in group),
                "before_cutoff_rate": statistics.mean(1.0 if row["detected_before_cutoff"] else 0.0 for row in group),
                "miss_rate": statistics.mean(1.0 if row["missed_signal"] else 0.0 for row in group),
                "extraction_exact_rate": statistics.mean(1.0 if row["extraction_exact"] else 0.0 for row in group),
            }
        )
        output.append(item)
    return output


def build_markdown(results: Dict) -> str:
    arm_rows = results["arm_summary"]
    by_pattern = results["by_pattern"]
    by_cutoff = results["by_cutoff_tier"]
    extraction = results["extraction_accuracy"]
    tier_counts = Counter(item["cutoff_tier"] for item in results["cutoff_design"].values())

    lines = [
        "# Cutoff-Based Exception Response Experiment",
        "",
        "## Design",
        "",
        f"- Scored packets: {results['scored_packet_count']}",
        f"- Simulation runs per packet-arm: {SIM_RUNS}",
        f"- Horizon: {HORIZON_DAYS} days",
        f"- Cutoff tier counts: {dict(sorted(tier_counts.items()))}",
        "- System arm: deterministic rule-based email extraction calibrated only on pilot packets.",
        "- LLM arm: current Gemini predictions from `outputs/actual_llm_predictions.jsonl`.",
        "- Human arm: gold interpretation after stochastic queue delay and noise-dependent miss risk.",
        "- Hybrid arm: LLM triage followed by human correction when the LLM identifies the right email/SKU/location.",
        "- Oracle is a perfect lower-bound benchmark and should not be treated as a realistic operating arm.",
        f"- Processing cost basis: planner labor is ${LOADED_PLANNER_HOURLY_COST:.2f}/hour loaded; human review is {HUMAN_REVIEW_MINUTES:.0f} minutes; hybrid approval is {HYBRID_APPROVAL_MINUTES:.0f} minutes.",
        f"- Automated processing costs: LLM ${LLM_PROCESSING_COST:.2f} per packet; rule system ${RULE_PROCESSING_COST:.2f} per packet.",
        "",
        "## Extraction Accuracy",
        "",
        "| Extractor | Packet exact | Decisive email | Type | Original ETA | Revised ETA | Delay | Quantity |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ["llm_agent", "rule_system"]:
        metric = extraction[name]
        fields = metric["field_accuracy"]
        lines.append(
            f"| {name} | {metric['packet_exact_match']:.3f} | {fields['decisive_email_id']:.3f} | "
            f"{fields['disruption_type']:.3f} | {fields['original_eta']:.3f} | "
            f"{fields['revised_eta']:.3f} | {fields['delay_days']:.3f} | {fields['quantity_affected']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Arm Performance",
            "",
            "| Arm | Mean total cost | Gap vs oracle | Service level | Service loss vs baseline | Stockout cost | Holding cost | Action cost | Processing cost | Before-cutoff rate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in arm_rows:
        lines.append(
            f"| {row['arm']} | {row['mean_total_cost']:.2f} | {row['mean_cost_gap_vs_oracle']:.2f} | "
            f"{row['mean_service_level']:.3f} | {row['mean_service_loss_vs_baseline']:.3f} | {row['mean_stockout_cost']:.2f} | "
            f"{row['mean_holding_cost']:.2f} | {row['mean_action_cost']:.2f} | "
            f"{row['mean_processing_cost']:.2f} | {row['before_cutoff_rate']:.3f} |"
        )

    lines.extend(["", "## Pattern Breakdown", ""])
    lines.extend(["| Pattern | Arm | Mean total cost | Service level | Exact/miss rate |", "|---|---|---:|---:|---:|"])
    for row in by_pattern:
        if row["arm"] == "oracle":
            continue
        lines.append(
            f"| {row['pattern']} | {row['arm']} | {row['mean_total_cost']:.2f} | "
            f"{row['mean_service_level']:.3f} | {row['extraction_exact_rate']:.3f} |"
        )

    lines.extend(["", "## Cutoff Breakdown", ""])
    lines.extend(["| Cutoff tier | Arm | Mean total cost | Before-cutoff rate | Service level |", "|---|---|---:|---:|---:|"])
    for row in by_cutoff:
        if row["arm"] == "oracle":
            continue
        lines.append(
            f"| {row['cutoff_tier']} | {row['arm']} | {row['mean_total_cost']:.2f} | "
            f"{row['before_cutoff_rate']:.3f} | {row['mean_service_level']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This design makes timing matter through action cutoffs rather than compressing physical lead times into hours.",
            "- The simulation uses a 10-day horizon and calibrated initial supply so absolute service levels remain interpretable.",
            "- Service loss is reported against a no-disruption baseline using the same demand path.",
            "- The rule-based system is a strong automatic baseline on known templates, but it is brittle when supplier language is buried or corrected.",
            "- The pure LLM arm reflects the current Gemini extraction quality; the hybrid arm estimates the value of using LLMs as fast triage plus human verification.",
            "- The fair adoption comparison is among LLM, rule-system, human, and hybrid arms; oracle is only a lower-bound reference.",
        ]
    )
    return "\n".join(lines)


def write_svg(path: Path, arm_rows: List[Dict]) -> None:
    rows = [row for row in arm_rows if row["arm"] != "oracle"]
    width, height = 760, 420
    margin_left, margin_bottom, margin_top = 80, 70, 45
    chart_w = width - margin_left - 40
    chart_h = height - margin_top - margin_bottom
    max_cost = max(row["mean_total_cost"] for row in rows) or 1.0
    colors = {
        "llm_agent": "#2f6f9f",
        "rule_system": "#8b8f39",
        "human_planner": "#b75d3c",
        "hybrid_llm_human": "#4f7d45",
    }
    bar_w = chart_w / (len(rows) * 1.6)
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>",
        "<style>text{font-family:Arial,sans-serif;font-size:13px}.axis{stroke:#222;stroke-width:1.4}.grid{stroke:#ddd}</style>",
        f"<text x='{width / 2}' y='27' text-anchor='middle'>Mean Total Cost by Operating Arm</text>",
        f"<line x1='{margin_left}' y1='{height-margin_bottom}' x2='{width-35}' y2='{height-margin_bottom}' class='axis'/>",
        f"<line x1='{margin_left}' y1='{margin_top}' x2='{margin_left}' y2='{height-margin_bottom}' class='axis'/>",
    ]
    for i in range(5):
        value = max_cost * i / 4
        y = height - margin_bottom - (value / max_cost) * chart_h
        parts.append(f"<line x1='{margin_left}' y1='{y:.1f}' x2='{width-35}' y2='{y:.1f}' class='grid'/>")
        parts.append(f"<text x='{margin_left-8}' y='{y+4:.1f}' text-anchor='end'>{value:.0f}</text>")
    for idx, row in enumerate(rows):
        x = margin_left + 35 + idx * (bar_w * 1.6)
        bar_h = row["mean_total_cost"] / max_cost * chart_h
        y = height - margin_bottom - bar_h
        parts.append(
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_w:.1f}' height='{bar_h:.1f}' fill='{colors[row['arm']]}'/>"
        )
        label = row["arm"].replace("_", " ")
        parts.append(f"<text x='{x + bar_w / 2:.1f}' y='{height-margin_bottom+20}' text-anchor='middle'>{label}</text>")
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    outputs_dir = root / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    packets = read_jsonl(data_dir / "scored_packets.jsonl")
    llm_predictions = {row["packet_id"]: row for row in read_jsonl(outputs_dir / "actual_llm_predictions.jsonl")}
    rule_predictions = [extract_packet(packet) for packet in packets]
    write_jsonl(outputs_dir / "rule_based_scored_predictions.jsonl", rule_predictions)
    rule_prediction_map = {row["packet_id"]: row for row in rule_predictions}

    cutoff_design = assign_cutoff_design(packets)
    detail_rows = []
    for packet_idx, packet in enumerate(packets):
        oracle_cost_by_run = {}
        for run_idx in range(SIM_RUNS):
            run_results = {}
            for arm in ARMS:
                result = simulate_arm(
                    packet_idx=packet_idx,
                    packet=packet,
                    arm=arm,
                    llm_prediction=llm_predictions[packet["packet_id"]],
                    rule_prediction=rule_prediction_map[packet["packet_id"]],
                    design=cutoff_design[packet["packet_id"]],
                    run_idx=run_idx,
                )
                run_results[arm] = result
            oracle_cost_by_run[run_idx] = run_results["oracle"].total_cost
            for arm, result in run_results.items():
                detail_rows.append(
                    {
                        "packet_id": packet["packet_id"],
                        "pattern": packet["pattern"],
                        "noise_tier": packet["noise_tier"],
                        "cutoff_tier": cutoff_design[packet["packet_id"]]["cutoff_tier"],
                        "run_idx": run_idx,
                        "arm": arm,
                        "action": result.action,
                        "total_cost": result.total_cost,
                        "cost_gap_vs_oracle": result.total_cost - oracle_cost_by_run[run_idx],
                        "stockout_cost": result.stockout_cost,
                        "holding_cost": result.holding_cost,
                        "action_cost": result.action_cost,
                        "processing_cost": result.processing_cost,
                        "service_level": result.service_level,
                        "service_loss_vs_baseline": result.service_loss_vs_baseline,
                        "shortage_units": result.shortage_units,
                        "holding_units": result.holding_units,
                        "detection_delay_days": result.detection_delay_days,
                        "detected_before_cutoff": result.detected_before_cutoff,
                        "missed_signal": result.missed_signal,
                        "extraction_exact": result.extraction_exact,
                    }
                )

    arm_summary = summarize(detail_rows, ["arm"])
    by_pattern = summarize(detail_rows, ["pattern", "arm"])
    by_cutoff = summarize(detail_rows, ["cutoff_tier", "arm"])
    by_noise = summarize(detail_rows, ["noise_tier", "arm"])
    extraction_accuracy = {
        "llm_agent": score_predictions(packets, list(llm_predictions.values())),
        "rule_system": score_predictions(packets, rule_predictions),
    }
    for metric in extraction_accuracy.values():
        metric.pop("misses", None)

    results = {
        "seed": SEED,
        "scored_packet_count": len(packets),
        "simulation_runs_per_packet_arm": SIM_RUNS,
        "horizon_days": HORIZON_DAYS,
        "arms": ARMS,
        "costs": {
            "loaded_planner_hourly_cost": LOADED_PLANNER_HOURLY_COST,
            "human_review_minutes": HUMAN_REVIEW_MINUTES,
            "hybrid_approval_minutes": HYBRID_APPROVAL_MINUTES,
            "llm_processing_cost": LLM_PROCESSING_COST,
            "rule_processing_cost": RULE_PROCESSING_COST,
            "human_processing_cost": HUMAN_PROCESSING_COST,
            "hybrid_processing_cost": HYBRID_PROCESSING_COST,
        },
        "latency_design": {
            "llm_delay_days": LLM_DELAY_DAYS,
            "rule_delay_days": RULE_DELAY_DAYS,
            "human_delay_distribution": HUMAN_DELAY_DISTRIBUTION,
            "hybrid_approval_distribution": HYBRID_APPROVAL_DISTRIBUTION,
            "human_miss_by_noise": HUMAN_MISS_BY_NOISE,
        },
        "cutoff_design": cutoff_design,
        "extraction_accuracy": extraction_accuracy,
        "arm_summary": arm_summary,
        "by_pattern": by_pattern,
        "by_cutoff_tier": by_cutoff,
        "by_noise": by_noise,
    }

    write_json(outputs_dir / "cutoff_experiment_results.json", results)
    write_csv(outputs_dir / "cutoff_experiment_arm_summary.csv", arm_summary)
    write_csv(outputs_dir / "cutoff_experiment_by_pattern.csv", by_pattern)
    write_csv(outputs_dir / "cutoff_experiment_by_cutoff.csv", by_cutoff)
    (outputs_dir / "cutoff_experiment_summary.md").write_text(build_markdown(results), encoding="utf-8")

    print("Cutoff experiment artifacts written to:")
    print(f"- {outputs_dir / 'cutoff_experiment_summary.md'}")
    print(f"- {outputs_dir / 'cutoff_experiment_results.json'}")
    print(f"- {outputs_dir / 'cutoff_experiment_arm_summary.csv'}")
    print(f"- {outputs_dir / 'cutoff_experiment_by_pattern.csv'}")
    print(f"- {outputs_dir / 'cutoff_experiment_by_cutoff.csv'}")


if __name__ == "__main__":
    main()
