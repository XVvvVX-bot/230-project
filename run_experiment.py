from __future__ import annotations

import json
import math
import os
import random
import statistics
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from gemini_inference import DEFAULT_GEMINI_MODEL, run_gemini_predictions


SEED = 230
SERVICE_Z = 1.645
REVIEW_PERIOD_DAYS = 1
SIM_RUNS = 100
DISTRACTOR_TYPES = ["irrelevant_chatter", "wrong_sku", "resolved_issue", "admin_note"]


@dataclass
class PolicyOutcome:
    action: str
    reorder_qty: int
    target_base_stock: int
    effective_on_order: int
    effective_lead_time: int
    mean_cost: float
    std_cost: float
    ci95_low: float
    ci95_high: float
    mean_service_level: float
    mean_stockout_cost: float
    mean_holding_cost: float
    mean_action_cost: float
    mean_pre_response_shortage_cost: float
    mean_total_shortage_units: float
    mean_total_holding_units: float
    mean_response_delay_hours: float
    realized_miss_rate: float


@dataclass
class ExperimentConfig:
    system_response_hours: float
    human_response_hours: float
    human_miss_prob: float
    human_ambiguity_miss_multiplier: float
    horizon_hours: int
    cover_min_hours: float
    cover_max_hours: float
    on_order_min_hours: float
    on_order_max_hours: float
    base_arrival_scale_hours: float
    base_arrival_min_hours: float
    base_arrival_max_hours: float
    delay_scale_hours: float
    delay_min_hours: float
    reallocate_cutoff_hours: float
    expedite_cutoff_hours: float
    expedite_arrival_hours: float
    reorder_arrival_hours: float
    reorder_fill_rate: float


def iso(d: date) -> str:
    return d.isoformat()


def ensure_dirs(root: Path) -> Dict[str, Path]:
    data_dir = root / "data"
    outputs_dir = root / "outputs"
    data_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return {"data": data_dir, "outputs": outputs_dir}


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def write_jsonl(path: Path, rows: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_existing_packets(data_dir: Path) -> Dict[str, List[Dict]]:
    scored_path = data_dir / "scored_packets.jsonl"
    if not scored_path.exists():
        raise FileNotFoundError(
            f"Missing scored packet file: {scored_path}. Run generate_packets.py first or place an existing scored_packets.jsonl in the data folder."
        )

    dataset = {"scored": read_jsonl(scored_path)}
    pilot_path = data_dir / "pilot_packets.jsonl"
    dataset["pilot"] = read_jsonl(pilot_path) if pilot_path.exists() else []
    return dataset


def load_experiment_config() -> ExperimentConfig:
    return ExperimentConfig(
        system_response_hours=float(os.environ.get("SYSTEM_RESPONSE_HOURS", "4")),
        human_response_hours=float(os.environ.get("HUMAN_RESPONSE_HOURS", "8")),
        human_miss_prob=float(os.environ.get("HUMAN_MISS_PROB", "0.1")),
        human_ambiguity_miss_multiplier=float(os.environ.get("HUMAN_AMBIGUITY_MISS_MULTIPLIER", "0.7")),
        horizon_hours=int(os.environ.get("HORIZON_HOURS", "24")),
        cover_min_hours=float(os.environ.get("COVER_MIN_HOURS", "6")),
        cover_max_hours=float(os.environ.get("COVER_MAX_HOURS", "18")),
        on_order_min_hours=float(os.environ.get("ON_ORDER_MIN_HOURS", "4")),
        on_order_max_hours=float(os.environ.get("ON_ORDER_MAX_HOURS", "12")),
        base_arrival_scale_hours=float(os.environ.get("BASE_ARRIVAL_SCALE_HOURS", "1.5")),
        base_arrival_min_hours=float(os.environ.get("BASE_ARRIVAL_MIN_HOURS", "4")),
        base_arrival_max_hours=float(os.environ.get("BASE_ARRIVAL_MAX_HOURS", "12")),
        delay_scale_hours=float(os.environ.get("DELAY_SCALE_HOURS", "2.0")),
        delay_min_hours=float(os.environ.get("DELAY_MIN_HOURS", "2")),
        reallocate_cutoff_hours=float(os.environ.get("REALLOCATE_CUTOFF_HOURS", "3")),
        expedite_cutoff_hours=float(os.environ.get("EXPEDITE_CUTOFF_HOURS", "6")),
        expedite_arrival_hours=float(os.environ.get("EXPEDITE_ARRIVAL_HOURS", "2")),
        reorder_arrival_hours=float(os.environ.get("REORDER_ARRIVAL_HOURS", "12")),
        reorder_fill_rate=float(os.environ.get("REORDER_FILL_RATE", "0.85")),
    )


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


def format_packet_for_prompt(packet: Dict) -> str:
    lines = [
        f"packet_id: {packet['packet_id']}",
        f"inventory_scope: {packet['inventory_records'][0]['location']}",
        "emails:",
    ]
    for email in packet["emails"]:
        lines.extend(
            [
                f"- email_id: {email['email_id']}",
                f"  from: {email['from']}",
                f"  subject: {email['subject']}",
                f"  timestamp: {email['timestamp']}",
                "  body: |",
            ]
        )
        for body_line in email["body"].splitlines():
            lines.append(f"    {body_line}")
    return "\n".join(lines)


def packet_prompt_requests(packets: List[Dict], prompt_text: str, schema: Dict) -> List[Dict]:
    requests = []
    for packet in packets:
        requests.append(
            {
                "packet_id": packet["packet_id"],
                "schema": schema,
                "messages": [
                    {"role": "system", "content": prompt_text},
                    {"role": "user", "content": format_packet_for_prompt(packet)},
                ],
            }
        )
    return requests


def demo_llm_prediction(packet: Dict, rng: random.Random) -> Dict:
    gold = packet["gold"]
    prediction = {
        "packet_id": packet["packet_id"],
        "actionable": gold["actionable"],
        "decisive_email_id": gold["decisive_email_id"],
        "focal_sku": gold["focal_sku"],
        "affected_location": gold["affected_location"],
        "disruption_type": gold["disruption_type"],
        "original_eta": gold["original_eta"],
        "revised_eta": gold["revised_eta"],
        "delay_days": gold["delay_days"],
        "quantity_affected": gold["quantity_affected"],
        "confidence": 0.88,
    }

    error_rate = {"low": 0.08, "medium": 0.18, "high": 0.30}[packet["noise_tier"]]
    if packet["pattern"] == "corrected_update":
        error_rate += 0.08
    if packet["pattern"] == "ambiguous_buried_delay":
        error_rate += 0.10

    roll = rng.random()
    if roll < error_rate / 3:
        wrong_email = rng.choice([e["email_id"] for e in packet["emails"] if e["email_id"] != gold["decisive_email_id"]])
        prediction["decisive_email_id"] = wrong_email
        if packet["pattern"] == "corrected_update":
            prediction["actionable"] = False
            prediction["focal_sku"] = None
            prediction["affected_location"] = None
            prediction["disruption_type"] = None
            prediction["original_eta"] = None
            prediction["revised_eta"] = None
            prediction["delay_days"] = None
            prediction["quantity_affected"] = None
        elif packet["pattern"] == "ambiguous_buried_delay" and packet["noise_tier"] == "high":
            prediction["delay_days"] = max(0, (prediction["delay_days"] or 0) - 3)
            if gold["original_eta"]:
                prediction["revised_eta"] = gold["original_eta"]
        prediction["confidence"] = 0.54
    elif roll < 2 * error_rate / 3:
        alt = rng.choice([rec for rec in packet["inventory_records"] if rec["sku"] != gold["focal_sku"]])
        prediction["focal_sku"] = alt["sku"]
        prediction["affected_location"] = alt["location"]
        prediction["confidence"] = 0.58
    elif roll < error_rate:
        if prediction["delay_days"] is not None:
            prediction["delay_days"] = max(1, prediction["delay_days"] + rng.choice([-2, -1, 1, 2]))
            prediction["revised_eta"] = iso(date.fromisoformat(gold["original_eta"]) + timedelta(days=prediction["delay_days"]))
        prediction["quantity_affected"] = max(10, prediction["quantity_affected"] + rng.randint(-40, 40))
        prediction["confidence"] = 0.61

    return prediction


def base_stock_level(demand_mean: float, demand_std: float, lead_time_days: int) -> int:
    target = demand_mean * (lead_time_days + REVIEW_PERIOD_DAYS) + SERVICE_Z * demand_std * math.sqrt(
        lead_time_days + REVIEW_PERIOD_DAYS
    )
    return max(0, int(math.ceil(target)))


def normalize_signal(signal: Optional[Dict]) -> Dict:
    if signal is None:
        return empty_signal()
    normalized = deepcopy(signal)
    required = ["actionable", "focal_sku", "affected_location", "disruption_type"]
    if not normalized.get("actionable"):
        return empty_signal()
    if any(normalized.get(field) in (None, "") for field in required):
        return empty_signal()
    return normalized


def extract_signal_for_arm(packet: Dict, arm: str, prediction: Optional[Dict]) -> Dict:
    if arm in {"gold", "system_based_operation", "human_planner_only"}:
        return deepcopy(packet["gold"])
    if arm == "llm_instant":
        return normalize_signal(prediction)
    return empty_signal()


def apply_signal_to_record(record: Dict, signal: Dict) -> Dict:
    rec = deepcopy(record)
    rec["effective_on_order"] = rec["on_order_qty"]
    rec["effective_lead_time"] = rec["lead_time_days"]

    if not signal["actionable"]:
        return rec
    if signal["focal_sku"] != rec["sku"] or signal["affected_location"] != rec["location"]:
        return rec

    qty = signal["quantity_affected"] or 0
    if signal["disruption_type"] in {"lead_time_delay", "corrected_update"}:
        rec["effective_lead_time"] = rec["lead_time_days"] + int(signal["delay_days"] or 0)
        rec["effective_on_order"] = max(0, rec["on_order_qty"] - qty)
    elif signal["disruption_type"] == "partial_shipment":
        rec["effective_on_order"] = max(0, rec["on_order_qty"] - qty)
    elif signal["disruption_type"] == "shipment_cancellation":
        rec["effective_on_order"] = max(0, rec["on_order_qty"] - qty)
    return rec


def hourly_demand_params(record: Dict) -> Dict:
    return {
        "mean": record["demand_mean"] / 24.0,
        "std": max(0.01, record["demand_std"] / math.sqrt(24.0)),
    }


def compressed_base_arrival_hour(record: Dict, config: ExperimentConfig) -> int:
    scaled = record["lead_time_days"] * config.base_arrival_scale_hours
    return int(round(min(max(scaled, config.base_arrival_min_hours), config.base_arrival_max_hours)))


def compressed_delay_hours(signal: Dict, config: ExperimentConfig) -> int:
    delay_days = float(signal.get("delay_days") or 0.0)
    if delay_days <= 0:
        return int(round(config.delay_min_hours))
    return int(round(max(config.delay_min_hours, delay_days * config.delay_scale_hours)))


def build_inbound_schedule(record: Dict, signal: Dict, config: ExperimentConfig) -> List[tuple[int, float]]:
    base_arrival = compressed_base_arrival_hour(record, config)
    total_on_order = float(record["on_order_qty"])
    if not signal.get("actionable"):
        return [(base_arrival, total_on_order)]
    if signal.get("focal_sku") != record["sku"] or signal.get("affected_location") != record["location"]:
        return [(base_arrival, total_on_order)]

    affected = min(float(signal.get("quantity_affected") or 0.0), total_on_order)
    unaffected = max(0.0, total_on_order - affected)
    disruption_type = signal.get("disruption_type")
    delay_hours = compressed_delay_hours(signal, config)
    delayed_arrival = base_arrival + delay_hours
    events: List[tuple[int, float]] = []

    if unaffected > 0:
        events.append((base_arrival, unaffected))

    if disruption_type in {"lead_time_delay", "corrected_update", "partial_shipment"}:
        if affected > 0:
            events.append((delayed_arrival, affected))
    elif disruption_type == "shipment_cancellation":
        pass
    else:
        events.append((base_arrival, affected))

    return events


def human_miss_prob_for_packet(packet: Dict, config: ExperimentConfig) -> float:
    if packet["pattern"] in {"corrected_update", "ambiguous_buried_delay"}:
        return config.human_miss_prob * config.human_ambiguity_miss_multiplier
    return config.human_miss_prob


def demand_path_for_trial(rng: random.Random, record: Dict, config: ExperimentConfig) -> List[float]:
    params = hourly_demand_params(record)
    return [max(0.0, rng.gauss(params["mean"], params["std"])) for _ in range(config.horizon_hours)]


def initial_on_hand_for_trial(rng: random.Random, record: Dict, config: ExperimentConfig) -> float:
    cover_hours = rng.uniform(config.cover_min_hours, config.cover_max_hours)
    return max(1.0, cover_hours * hourly_demand_params(record)["mean"])


def on_order_for_trial(rng: random.Random, record: Dict, config: ExperimentConfig) -> float:
    cover_hours = rng.uniform(config.on_order_min_hours, config.on_order_max_hours)
    return max(1.0, cover_hours * hourly_demand_params(record)["mean"])


def operational_record_for_trial(record: Dict, initial_inventory: float, on_order_qty: float) -> Dict:
    operational = deepcopy(record)
    operational["current_inventory"] = initial_inventory
    operational["on_order_qty"] = on_order_qty
    operational["holding_cost"] = operational["holding_cost"] / 24.0
    return operational


def scale_signal_for_operational_record(base_record: Dict, operational_record: Dict, signal: Dict) -> Dict:
    if not signal.get("actionable"):
        return empty_signal()
    scaled = deepcopy(signal)
    original_on_order = max(float(base_record["on_order_qty"]), 1.0)
    operational_on_order = float(operational_record["on_order_qty"])
    original_qty = float(signal.get("quantity_affected") or 0.0)
    scaled_qty = min(operational_on_order, operational_on_order * original_qty / original_on_order)
    scaled["quantity_affected"] = int(round(scaled_qty))
    return scaled


def response_step(response_hours: float, config: ExperimentConfig) -> int:
    return max(0, min(config.horizon_hours, int(math.ceil(response_hours))))


def event_map(events: List[tuple[int, float]], config: ExperimentConfig) -> Dict[int, float]:
    mapped: Dict[int, float] = defaultdict(float)
    for hour, qty in events:
        if 0 <= hour < config.horizon_hours and qty > 0:
            mapped[int(hour)] += float(qty)
    return dict(mapped)


def future_inbound_qty(events: List[tuple[int, float]], start_hour: int, config: ExperimentConfig) -> float:
    return sum(qty for hour, qty in events if start_hour <= hour < config.horizon_hours)


def action_plan(action: str, needed_qty: int, current_hour: int, packet: Dict, config: ExperimentConfig) -> Dict:
    if action == "reallocate":
        deliver_qty = float(min(needed_qty, packet["surplus_pool_qty"]))
        return {"events": [(current_hour, deliver_qty)], "action_cost": 0.25 * deliver_qty}
    if action == "expedite":
        deliver_qty = float(needed_qty)
        arrival_hour = current_hour + int(math.ceil(config.expedite_arrival_hours))
        return {"events": [(arrival_hour, deliver_qty)], "action_cost": 0.60 * deliver_qty}
    if action == "standard_reorder":
        deliver_qty = float(config.reorder_fill_rate * needed_qty)
        arrival_hour = current_hour + int(math.ceil(config.reorder_arrival_hours))
        return {"events": [(arrival_hour, deliver_qty)], "action_cost": 0.10 * needed_qty}
    return {"events": [], "action_cost": 0.0}


def deterministic_tail_cost(
    current_inventory: float,
    future_events: List[tuple[int, float]],
    candidate_events: List[tuple[int, float]],
    record: Dict,
    start_hour: int,
    config: ExperimentConfig,
) -> float:
    params = hourly_demand_params(record)
    inventory = current_inventory
    inbound = event_map(future_events + candidate_events, config)
    cost = 0.0
    for hour in range(start_hour, config.horizon_hours):
        inventory += inbound.get(hour, 0.0)
        demand = params["mean"]
        shortage = max(0.0, demand - inventory)
        inventory = max(0.0, inventory - demand)
        cost += shortage * record["shortage_cost"] + inventory * record["holding_cost"]
    return cost


def choose_action_timeline(
    packet: Dict,
    record: Dict,
    current_inventory: float,
    future_events: List[tuple[int, float]],
    current_hour: int,
    response_hours: float,
    config: ExperimentConfig,
) -> Dict:
    remaining_hours = max(0, config.horizon_hours - current_hour)
    params = hourly_demand_params(record)
    target = params["mean"] * remaining_hours + SERVICE_Z * params["std"] * math.sqrt(max(remaining_hours, 1))
    future_qty = future_inbound_qty(future_events, current_hour, config)
    needed_qty = max(0, int(math.ceil(target - (current_inventory + future_qty))))

    candidates = ["no_action", "standard_reorder"]
    if response_hours <= config.reallocate_cutoff_hours and packet["surplus_pool_qty"] > 0:
        candidates.append("reallocate")
    if response_hours <= config.expedite_cutoff_hours:
        candidates.append("expedite")

    best_choice = None
    for action in candidates:
        plan = action_plan(action, needed_qty, current_hour, packet, config)
        score = deterministic_tail_cost(current_inventory, future_events, plan["events"], record, current_hour, config)
        score += plan["action_cost"]
        if best_choice is None or score < best_choice["score"]:
            best_choice = {
                "action": action,
                "reorder_qty": needed_qty,
                "target_base_stock": int(math.ceil(target)),
                "inventory_position": int(round(current_inventory + future_qty)),
                "action_events": plan["events"],
                "action_cost": plan["action_cost"],
                "score": score,
            }

    assert best_choice is not None
    return best_choice


def choose_action(packet: Dict, record: Dict) -> Dict:
    target = base_stock_level(record["demand_mean"], record["demand_std"], record["effective_lead_time"])
    inventory_position = record["current_inventory"] + record["effective_on_order"]
    reorder_qty = max(0, target - inventory_position)
    p_over_h = record["shortage_cost"] / max(record["holding_cost"], 1e-6)
    delay_days = max(0, record["effective_lead_time"] - record["lead_time_days"])

    if reorder_qty == 0:
        action = "no_action"
    elif packet["surplus_pool_qty"] >= max(40, int(0.7 * reorder_qty)):
        action = "reallocate"
    elif delay_days <= 3 and p_over_h >= 3.0:
        action = "expedite"
    else:
        action = "reorder"

    return {
        "action": action,
        "reorder_qty": reorder_qty,
        "target_base_stock": target,
        "inventory_position": inventory_position,
    }


def omnipotent_gold_outcome() -> PolicyOutcome:
    return PolicyOutcome(
        action="perfect_schedule",
        reorder_qty=0,
        target_base_stock=0,
        effective_on_order=0,
        effective_lead_time=0,
        mean_cost=0.0,
        std_cost=0.0,
        ci95_low=0.0,
        ci95_high=0.0,
        mean_service_level=1.0,
        mean_stockout_cost=0.0,
        mean_holding_cost=0.0,
        mean_action_cost=0.0,
        mean_pre_response_shortage_cost=0.0,
        mean_total_shortage_units=0.0,
        mean_total_holding_units=0.0,
        mean_response_delay_hours=0.0,
        realized_miss_rate=0.0,
    )


def simulate_single_arm_run(
    packet: Dict,
    record: Dict,
    demand_path: List[float],
    initial_inventory: float,
    true_events: List[tuple[int, float]],
    perceived_signal: Dict,
    response_hours: float,
    miss_prob: float,
    rng: random.Random,
    config: ExperimentConfig,
) -> Dict:
    inventory = initial_inventory
    response_hour = response_step(response_hours, config)
    missed = rng.random() < miss_prob
    effective_signal = empty_signal() if missed else perceived_signal
    perceived_events = build_inbound_schedule(record, effective_signal, config)
    actual_inbound = event_map(true_events, config)
    chosen_action = {
        "action": "no_action",
        "reorder_qty": 0,
        "target_base_stock": 0,
        "inventory_position": int(round(initial_inventory)),
        "action_events": [],
        "action_cost": 0.0,
    }
    action_selected = response_hour == 0
    if action_selected:
        chosen_action = choose_action_timeline(
            packet, record, inventory, perceived_events, 0, response_hours, config
        )
    action_inbound = event_map(chosen_action["action_events"], config)

    total_cost = 0.0
    stockout_cost = 0.0
    holding_cost = 0.0
    pre_response_shortage_cost = 0.0
    total_shortage_units = 0.0
    total_holding_units = 0.0
    total_demand = 0.0

    for hour in range(config.horizon_hours):
        inventory += actual_inbound.get(hour, 0.0) + action_inbound.get(hour, 0.0)

        if not action_selected and hour == response_hour:
            chosen_action = choose_action_timeline(
                packet, record, inventory, perceived_events, hour, response_hours, config
            )
            action_inbound = event_map(chosen_action["action_events"], config)
            inventory += action_inbound.get(hour, 0.0)
            action_selected = True

        demand = demand_path[hour]
        total_demand += demand
        shortage = max(0.0, demand - inventory)
        inventory = max(0.0, inventory - demand)
        total_shortage_units += shortage
        total_holding_units += inventory
        shortage_cost = shortage * record["shortage_cost"]
        stockout_cost += shortage_cost
        if hour < response_hour:
            pre_response_shortage_cost += shortage_cost
        hold_cost = inventory * record["holding_cost"]
        holding_cost += hold_cost
        total_cost += shortage_cost + hold_cost

    total_cost += chosen_action["action_cost"]
    fill_rate = 1.0 if total_demand <= 0 else max(0.0, 1.0 - total_shortage_units / total_demand)

    return {
        "action": chosen_action["action"],
        "reorder_qty": chosen_action["reorder_qty"],
        "target_base_stock": chosen_action["target_base_stock"],
        "effective_on_order": int(round(future_inbound_qty(true_events, 0, config))),
        "effective_lead_time": compressed_base_arrival_hour(record, config),
        "mean_cost": total_cost,
        "mean_service_level": fill_rate,
        "mean_stockout_cost": stockout_cost,
        "mean_holding_cost": holding_cost,
        "mean_action_cost": chosen_action["action_cost"],
        "mean_pre_response_shortage_cost": pre_response_shortage_cost,
        "mean_total_shortage_units": total_shortage_units,
        "mean_total_holding_units": total_holding_units,
        "mean_response_delay_hours": response_hours,
        "realized_miss_rate": 1.0 if missed else 0.0,
    }


def summarize_arm_runs(runs: List[Dict]) -> PolicyOutcome:
    costs = [run["mean_cost"] for run in runs]
    std_cost = statistics.pstdev(costs)
    ci_delta = 1.96 * (std_cost / math.sqrt(len(costs)))
    action_mode = Counter(run["action"] for run in runs).most_common(1)[0][0]
    return PolicyOutcome(
        action=action_mode,
        reorder_qty=int(round(statistics.mean(run["reorder_qty"] for run in runs))),
        target_base_stock=int(round(statistics.mean(run["target_base_stock"] for run in runs))),
        effective_on_order=int(round(statistics.mean(run["effective_on_order"] for run in runs))),
        effective_lead_time=int(round(statistics.mean(run["effective_lead_time"] for run in runs))),
        mean_cost=statistics.mean(costs),
        std_cost=std_cost,
        ci95_low=statistics.mean(costs) - ci_delta,
        ci95_high=statistics.mean(costs) + ci_delta,
        mean_service_level=statistics.mean(run["mean_service_level"] for run in runs),
        mean_stockout_cost=statistics.mean(run["mean_stockout_cost"] for run in runs),
        mean_holding_cost=statistics.mean(run["mean_holding_cost"] for run in runs),
        mean_action_cost=statistics.mean(run["mean_action_cost"] for run in runs),
        mean_pre_response_shortage_cost=statistics.mean(run["mean_pre_response_shortage_cost"] for run in runs),
        mean_total_shortage_units=statistics.mean(run["mean_total_shortage_units"] for run in runs),
        mean_total_holding_units=statistics.mean(run["mean_total_holding_units"] for run in runs),
        mean_response_delay_hours=statistics.mean(run["mean_response_delay_hours"] for run in runs),
        realized_miss_rate=statistics.mean(run["realized_miss_rate"] for run in runs),
    )


def packet_exact_match(gold: Dict, pred: Dict) -> bool:
    keys = [
        "actionable",
        "decisive_email_id",
        "focal_sku",
        "affected_location",
        "disruption_type",
        "delay_days",
        "quantity_affected",
    ]
    return all(gold.get(k) == pred.get(k) for k in keys)


def evaluate_extraction(scored_packets: List[Dict], predictions: Dict[str, Dict]) -> Dict:
    totals = len(scored_packets)
    exact = 0
    correct_actionable = 0
    correct_sku = 0
    correct_location = 0
    correct_type = 0
    delay_errors = []
    quantity_errors = []
    failure_modes = Counter()
    failure_reorder_gap = defaultdict(list)

    for packet in scored_packets:
        gold = packet["gold"]
        pred = predictions[packet["packet_id"]]
        if packet_exact_match(gold, pred):
            exact += 1
        if gold["actionable"] == pred["actionable"]:
            correct_actionable += 1
        if gold["focal_sku"] == pred["focal_sku"]:
            correct_sku += 1
        else:
            failure_modes["wrong_sku_or_location"] += 1
        if gold["affected_location"] == pred["affected_location"]:
            correct_location += 1
        if gold["disruption_type"] == pred["disruption_type"]:
            correct_type += 1
        else:
            failure_modes["wrong_disruption_type"] += 1

        if gold["delay_days"] is not None and pred["delay_days"] is not None:
            delay_error = abs(gold["delay_days"] - pred["delay_days"])
            delay_errors.append(delay_error)
            if delay_error > 0:
                failure_modes["wrong_delay_value"] += 1
        if gold["quantity_affected"] is not None and pred["quantity_affected"] is not None:
            quantity_error = abs(gold["quantity_affected"] - pred["quantity_affected"])
            quantity_errors.append(quantity_error)
            if quantity_error > 0:
                failure_modes["wrong_quantity_value"] += 1
        if gold["decisive_email_id"] != pred["decisive_email_id"]:
            failure_modes["wrong_decisive_email"] += 1

    return {
        "actionable_email_identification_accuracy": correct_actionable / totals,
        "focal_sku_exact_match_accuracy": correct_sku / totals,
        "location_exact_match_accuracy": correct_location / totals,
        "disruption_type_exact_match_accuracy": correct_type / totals,
        "mean_absolute_delay_error_days": statistics.mean(delay_errors) if delay_errors else 0.0,
        "mean_absolute_quantity_error": statistics.mean(quantity_errors) if quantity_errors else 0.0,
        "packet_level_exact_match_accuracy": exact / totals,
        "failure_modes": dict(failure_modes.most_common()),
    }


def evaluate_decisions(scored_packets: List[Dict], predictions: Dict[str, Dict], config: ExperimentConfig) -> Dict:
    arm_names = ["gold", "llm_instant", "system_based_operation", "human_planner_only"]
    arm_rollups = {arm: [] for arm in arm_names}
    per_packet = []
    noise_rollups = defaultdict(
        lambda: {
            "count": 0,
            "llm_exact_matches": 0,
            "llm_cost_sum": 0.0,
            "system_cost_sum": 0.0,
            "human_cost_sum": 0.0,
        }
    )

    for idx, packet in enumerate(scored_packets):
        focal_record = deepcopy(packet["inventory_records"][0])
        true_signal = extract_signal_for_arm(packet, "gold", None)
        llm_signal = extract_signal_for_arm(packet, "llm_instant", predictions[packet["packet_id"]])
        trial_runs = {arm: [] for arm in arm_names if arm != "gold"}
        for run_idx in range(SIM_RUNS):
            rng = random.Random(SEED + 1000 * idx + run_idx)
            initial_inventory = initial_on_hand_for_trial(rng, focal_record, config)
            on_order_qty = on_order_for_trial(rng, focal_record, config)
            operational_record = operational_record_for_trial(focal_record, initial_inventory, on_order_qty)
            demand_path = demand_path_for_trial(rng, operational_record, config)
            scaled_true_signal = scale_signal_for_operational_record(focal_record, operational_record, true_signal)
            scaled_llm_signal = scale_signal_for_operational_record(focal_record, operational_record, llm_signal)
            true_events = build_inbound_schedule(operational_record, scaled_true_signal, config)

            trial_runs["llm_instant"].append(
                simulate_single_arm_run(
                    packet,
                    operational_record,
                    demand_path,
                    initial_inventory,
                    true_events,
                    scaled_llm_signal,
                    response_hours=0.0,
                    miss_prob=0.0,
                    rng=rng,
                    config=config,
                )
            )
            trial_runs["system_based_operation"].append(
                simulate_single_arm_run(
                    packet,
                    operational_record,
                    demand_path,
                    initial_inventory,
                    true_events,
                    scaled_true_signal,
                    response_hours=config.system_response_hours,
                    miss_prob=0.0,
                    rng=rng,
                    config=config,
                )
            )
            trial_runs["human_planner_only"].append(
                simulate_single_arm_run(
                    packet,
                    operational_record,
                    demand_path,
                    initial_inventory,
                    true_events,
                    scaled_true_signal,
                    response_hours=config.human_response_hours,
                    miss_prob=human_miss_prob_for_packet(packet, config),
                    rng=rng,
                    config=config,
                )
            )

        outcomes = {
            "gold": omnipotent_gold_outcome(),
            "llm_instant": summarize_arm_runs(trial_runs["llm_instant"]),
            "system_based_operation": summarize_arm_runs(trial_runs["system_based_operation"]),
            "human_planner_only": summarize_arm_runs(trial_runs["human_planner_only"]),
        }

        for arm_name in arm_names:
            arm_rollups[arm_name].append(
                {
                    "cost_increment": outcomes[arm_name].mean_cost,
                    "service_level": outcomes[arm_name].mean_service_level,
                    "stockout_cost": outcomes[arm_name].mean_stockout_cost,
                    "holding_cost": outcomes[arm_name].mean_holding_cost,
                    "action_cost": outcomes[arm_name].mean_action_cost,
                    "pre_response_shortage_cost": outcomes[arm_name].mean_pre_response_shortage_cost,
                    "miss_rate": outcomes[arm_name].realized_miss_rate,
                }
            )

        exact = packet_exact_match(packet["gold"], predictions[packet["packet_id"]])
        noise_bucket = noise_rollups[packet["noise_tier"]]
        noise_bucket["count"] += 1
        noise_bucket["llm_exact_matches"] += int(exact)
        noise_bucket["llm_cost_sum"] += outcomes["llm_instant"].mean_cost
        noise_bucket["system_cost_sum"] += outcomes["system_based_operation"].mean_cost
        noise_bucket["human_cost_sum"] += outcomes["human_planner_only"].mean_cost

        per_packet.append(
            {
                "packet_id": packet["packet_id"],
                "pattern": packet["pattern"],
                "noise_tier": packet["noise_tier"],
                "gold_cost": round(outcomes["gold"].mean_cost, 3),
                "llm_action": outcomes["llm_instant"].action,
                "llm_cost_increment": round(outcomes["llm_instant"].mean_cost, 3),
                "system_action": outcomes["system_based_operation"].action,
                "system_cost_increment": round(outcomes["system_based_operation"].mean_cost, 3),
                "human_action": outcomes["human_planner_only"].action,
                "human_cost_increment": round(outcomes["human_planner_only"].mean_cost, 3),
                "human_realized_miss_rate": round(outcomes["human_planner_only"].realized_miss_rate, 3),
            }
        )

    summary = {}
    for arm_name in arm_names:
        rows = arm_rollups[arm_name]
        summary[arm_name] = {
            "mean_cost_increment_vs_gold": statistics.mean(r["cost_increment"] for r in rows),
            "mean_service_level": statistics.mean(r["service_level"] for r in rows),
            "mean_stockout_cost": statistics.mean(r["stockout_cost"] for r in rows),
            "mean_holding_cost": statistics.mean(r["holding_cost"] for r in rows),
            "mean_action_cost": statistics.mean(r["action_cost"] for r in rows),
            "mean_pre_response_shortage_cost": statistics.mean(r["pre_response_shortage_cost"] for r in rows),
            "mean_realized_miss_rate": statistics.mean(r["miss_rate"] for r in rows),
        }

    robustness = []
    for tier in ["low", "medium", "high"]:
        bucket = noise_rollups[tier]
        robustness.append(
            {
                "noise_tier": tier,
                "llm_packet_exact_match_rate": bucket["llm_exact_matches"] / bucket["count"],
                "mean_llm_cost_increment_vs_gold": bucket["llm_cost_sum"] / bucket["count"],
                "mean_system_cost_increment_vs_gold": bucket["system_cost_sum"] / bucket["count"],
                "mean_human_cost_increment_vs_gold": bucket["human_cost_sum"] / bucket["count"],
            }
        )

    return {"arm_summary": summary, "per_packet": per_packet, "robustness_by_noise": robustness}


def create_error_analysis(scored_packets: List[Dict], predictions: Dict[str, Dict]) -> str:
    config = load_experiment_config()
    mode_counts = Counter()
    cost_impacts = defaultdict(list)
    for idx, packet in enumerate(scored_packets):
        gold = packet["gold"]
        pred = predictions[packet["packet_id"]]
        focal_record = deepcopy(packet["inventory_records"][0])
        true_signal = deepcopy(gold)
        llm_signal = normalize_signal(pred)
        runs = []
        for run_idx in range(SIM_RUNS):
            rng = random.Random(SEED + 50000 + 1000 * idx + run_idx)
            initial_inventory = initial_on_hand_for_trial(rng, focal_record, config)
            on_order_qty = on_order_for_trial(rng, focal_record, config)
            operational_record = operational_record_for_trial(focal_record, initial_inventory, on_order_qty)
            demand_path = demand_path_for_trial(rng, operational_record, config)
            scaled_true_signal = scale_signal_for_operational_record(focal_record, operational_record, true_signal)
            scaled_llm_signal = scale_signal_for_operational_record(focal_record, operational_record, llm_signal)
            true_events = build_inbound_schedule(operational_record, scaled_true_signal, config)
            runs.append(
                simulate_single_arm_run(
                    packet,
                    operational_record,
                    demand_path,
                    initial_inventory,
                    true_events,
                    scaled_llm_signal,
                    response_hours=0.0,
                    miss_prob=0.0,
                    rng=rng,
                    config=config,
                )
            )
        llm_outcome = summarize_arm_runs(runs)

        if gold["decisive_email_id"] != pred["decisive_email_id"]:
            mode_counts["Missed corrective or decisive email"] += 1
            cost_impacts["Missed corrective or decisive email"].append(llm_outcome.mean_cost)
        elif gold["focal_sku"] != pred["focal_sku"] or gold["affected_location"] != pred["affected_location"]:
            mode_counts["Selected the wrong SKU/location"] += 1
            cost_impacts["Selected the wrong SKU/location"].append(llm_outcome.mean_cost)
        elif gold["delay_days"] != pred["delay_days"] or gold["quantity_affected"] != pred["quantity_affected"]:
            mode_counts["Misread delay or affected quantity"] += 1
            cost_impacts["Misread delay or affected quantity"].append(llm_outcome.mean_cost)

    lines = []
    for label, count in mode_counts.most_common(3):
        avg_gap = statistics.mean(cost_impacts[label]) if cost_impacts[label] else 0.0
        lines.append(
            f"- {label}: observed in {count} scored packets; average LLM cost increment vs gold = {avg_gap:.1f}."
        )
    return "\n".join(lines)


def build_trial_design_summary(scored_packets: List[Dict]) -> Dict:
    pattern_counts = Counter(packet["pattern"] for packet in scored_packets)
    noise_counts = Counter(packet["noise_tier"] for packet in scored_packets)
    email_counts = Counter(packet["packet_metadata"]["num_emails"] for packet in scored_packets)
    sku_counts = Counter(packet["packet_metadata"]["num_sku_locations"] for packet in scored_packets)
    return {
        "num_scored_packets": len(scored_packets),
        "emails_per_packet_distribution": dict(sorted(email_counts.items())),
        "sku_locations_per_packet_distribution": dict(sorted(sku_counts.items())),
        "actionable_pattern_counts": dict(pattern_counts),
        "noise_tier_counts": dict(noise_counts),
        "distractor_types": DISTRACTOR_TYPES,
    }


def svg_bar_chart(data: List[Dict], path: Path) -> None:
    width = 640
    height = 360
    margin = 50
    chart_w = width - 2 * margin
    chart_h = height - 2 * margin
    max_y = max(item["mean_llm_cost_increment_vs_gold"] for item in data) or 1.0
    bar_w = chart_w / (len(data) * 1.5)

    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>",
        "<style>text{font-family:Arial,sans-serif;font-size:13px;} .axis{stroke:#333;stroke-width:1.5;} "
        ".bar{fill:#3B7EA1;} .label{fill:#111;} .grid{stroke:#ddd;stroke-width:1;}</style>",
        f"<text x='{width/2}' y='28' text-anchor='middle' class='label'>LLM Cost Increment by Noise Tier</text>",
        f"<line x1='{margin}' y1='{height-margin}' x2='{width-margin}' y2='{height-margin}' class='axis'/>",
        f"<line x1='{margin}' y1='{margin}' x2='{margin}' y2='{height-margin}' class='axis'/>",
    ]

    for i in range(5):
        y_val = i / 4 * max_y
        y = height - margin - (y_val / max_y) * chart_h if max_y else height - margin
        parts.append(f"<line x1='{margin}' y1='{y:.1f}' x2='{width-margin}' y2='{y:.1f}' class='grid'/>")
        parts.append(f"<text x='{margin-8}' y='{y+4:.1f}' text-anchor='end'>{y_val:.2f}</text>")

    for idx, item in enumerate(data):
        x = margin + idx * (bar_w * 1.5) + bar_w * 0.25
        bar_h = (item["mean_llm_cost_increment_vs_gold"] / max_y) * chart_h if max_y else 0
        y = height - margin - bar_h
        parts.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_w:.1f}' height='{bar_h:.1f}' class='bar'/>")
        parts.append(
            f"<text x='{x + bar_w/2:.1f}' y='{height-margin+18}' text-anchor='middle'>{item['noise_tier']}</text>"
        )
        parts.append(
            f"<text x='{x + bar_w/2:.1f}' y='{y-6:.1f}' text-anchor='middle'>{item['mean_llm_cost_increment_vs_gold']:.0f}</text>"
        )

    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def build_summary_markdown(
    trial_design: Dict,
    extraction_metrics: Dict,
    decision_metrics: Dict,
    error_analysis: str,
    config: ExperimentConfig,
) -> str:
    lines = [
        "# Experiment Summary",
        "",
        "## Trial-Set Design",
        "",
        f"- Scored packets: {trial_design['num_scored_packets']}",
        f"- Emails per packet: {trial_design['emails_per_packet_distribution']}",
        f"- SKU/location records per packet: {trial_design['sku_locations_per_packet_distribution']}",
        f"- Actionable pattern counts: {trial_design['actionable_pattern_counts']}",
        f"- Noise tiers: {trial_design['noise_tier_counts']}",
        f"- Distractor types: {', '.join(trial_design['distractor_types'])}",
        f"- System response time (hours): {config.system_response_hours:.1f}",
        f"- Human response time (hours): {config.human_response_hours:.1f}",
        f"- Human missed-email risk: {config.human_miss_prob:.3f}",
        "",
        "## Extraction Accuracy",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Actionable-email identification accuracy | {extraction_metrics['actionable_email_identification_accuracy']:.3f} |",
        f"| Focal SKU exact-match accuracy | {extraction_metrics['focal_sku_exact_match_accuracy']:.3f} |",
        f"| Location exact-match accuracy | {extraction_metrics['location_exact_match_accuracy']:.3f} |",
        f"| Disruption-type exact-match accuracy | {extraction_metrics['disruption_type_exact_match_accuracy']:.3f} |",
        f"| Mean absolute delay error (days) | {extraction_metrics['mean_absolute_delay_error_days']:.3f} |",
        f"| Mean absolute quantity error | {extraction_metrics['mean_absolute_quantity_error']:.3f} |",
        f"| Packet-level exact match | {extraction_metrics['packet_level_exact_match_accuracy']:.3f} |",
        "",
        "## End-to-End Decision Performance",
        "",
        "| Arm | Mean cost increment vs gold | Mean service level | Mean stockout cost | Mean holding cost | Mean pre-response shortage cost |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm_key, label in [
        ("gold", "Gold omnipotent"),
        ("llm_instant", "LLM instant"),
        ("system_based_operation", "System-based operation"),
        ("human_planner_only", "Human planner only"),
    ]:
        row = decision_metrics["arm_summary"][arm_key]
        lines.append(
            f"| {label} | {row['mean_cost_increment_vs_gold']:.2f} | "
            f"{row['mean_service_level']:.3f} | "
            f"{row['mean_stockout_cost']:.2f} | "
            f"{row['mean_holding_cost']:.2f} | "
            f"{row['mean_pre_response_shortage_cost']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Robustness by Noise Tier",
            "",
            "| Noise tier | LLM exact match | Mean LLM cost increment | Mean system cost increment | Mean human cost increment |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in decision_metrics["robustness_by_noise"]:
        lines.append(
            f"| {row['noise_tier']} | {row['llm_packet_exact_match_rate']:.3f} | "
            f"{row['mean_llm_cost_increment_vs_gold']:.2f} | "
            f"{row['mean_system_cost_increment_vs_gold']:.2f} | "
            f"{row['mean_human_cost_increment_vs_gold']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Top Failure Modes",
            "",
            error_analysis,
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    dirs = ensure_dirs(root)
    config = load_experiment_config()
    prompt_text = load_text(root / "extraction_prompt.md")
    schema = json.loads((root / "extraction_schema.json").read_text(encoding="utf-8"))

    dataset = load_existing_packets(dirs["data"])

    requests = packet_prompt_requests(dataset["scored"], prompt_text, schema)
    write_jsonl(dirs["outputs"] / "llm_requests.jsonl", requests)

    demo_predictions_path = dirs["outputs"] / "demo_llm_predictions.jsonl"
    actual_predictions_path = dirs["outputs"] / "actual_llm_predictions.jsonl"
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()

    if provider == "gemini":
        predictions = run_gemini_predictions(requests, actual_predictions_path)
        prediction_source = f"gemini:{os.environ.get('GEMINI_MODEL', DEFAULT_GEMINI_MODEL)}"
    elif actual_predictions_path.exists():
        predictions = read_jsonl(actual_predictions_path)
        prediction_source = actual_predictions_path.name
    else:
        rng = random.Random(SEED + 99)
        demo_predictions = [demo_llm_prediction(packet, rng) for packet in dataset["scored"]]
        write_jsonl(demo_predictions_path, demo_predictions)
        predictions = demo_predictions
        prediction_source = demo_predictions_path.name
    prediction_map = {row["packet_id"]: row for row in predictions}
    missing_packets = [packet["packet_id"] for packet in dataset["scored"] if packet["packet_id"] not in prediction_map]
    if missing_packets:
        raise ValueError(
            f"Predictions are missing {len(missing_packets)} scored packets, including {missing_packets[:5]}."
        )

    extraction_metrics = evaluate_extraction(dataset["scored"], prediction_map)
    decision_metrics = evaluate_decisions(dataset["scored"], prediction_map, config)
    trial_design = build_trial_design_summary(dataset["scored"])
    error_analysis = create_error_analysis(dataset["scored"], prediction_map)

    results = {
        "seed": SEED,
        "simulation_runs_per_packet": SIM_RUNS,
        "prediction_source": prediction_source,
        "experiment_parameters": {
            "system_response_hours": config.system_response_hours,
            "human_response_hours": config.human_response_hours,
            "human_miss_prob": config.human_miss_prob,
        },
        "trial_design": trial_design,
        "extraction_metrics": extraction_metrics,
        "decision_metrics": decision_metrics,
        "error_analysis": error_analysis.splitlines(),
    }
    (dirs["outputs"] / "experiment_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary_md = build_summary_markdown(trial_design, extraction_metrics, decision_metrics, error_analysis, config)
    (dirs["outputs"] / "experiment_summary.md").write_text(summary_md, encoding="utf-8")
    svg_bar_chart(decision_metrics["robustness_by_noise"], dirs["outputs"] / "performance_by_noise.svg")

    print("Experiment artifacts written to:")
    print(f"- {dirs['outputs']}")


if __name__ == "__main__":
    main()
