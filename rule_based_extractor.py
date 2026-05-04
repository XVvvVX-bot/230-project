from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASE_DATE = date(2026, 4, 20)
WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

CRITICAL_KEYS = [
    "actionable",
    "decisive_email_id",
    "focal_sku",
    "affected_location",
    "disruption_type",
    "original_eta",
    "revised_eta",
    "delay_days",
    "quantity_affected",
]

EXCLUSION_PHRASES = [
    "no changes to confirmed inbound orders",
    "no further action is needed",
    "administrative note only",
    "does not affect the focal",
    "not the focal planning line",
    "other po",
    "backlog on",
    "has been cleared",
    "hold on",
    "is cleared",
    "still on track",
]


def read_jsonl(path: Path) -> List[Dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def empty_prediction(packet_id: str) -> Dict:
    return {
        "packet_id": packet_id,
        "actionable": False,
        "decisive_email_id": None,
        "focal_sku": None,
        "affected_location": None,
        "disruption_type": None,
        "original_eta": None,
        "revised_eta": None,
        "delay_days": None,
        "quantity_affected": None,
        "confidence": 0.0,
    }


def combined_text(email: Dict) -> str:
    return f"{email.get('subject', '')}\n{email.get('body', '')}"


def parse_timestamp(value: str) -> date:
    return datetime.fromisoformat(value).date()


def parse_explicit_dates(text: str) -> List[str]:
    return re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)


def next_weekday_after(anchor: date, weekday_name: str, strictly_after: bool = False) -> date:
    target = WEEKDAY_INDEX[weekday_name.lower()]
    delta = (target - anchor.weekday()) % 7
    if strictly_after and delta == 0:
        delta = 7
    return anchor + timedelta(days=delta)


def next_named_weekday(text: str, email_day: date, after: Optional[date] = None) -> Optional[date]:
    lowered = text.lower()
    matches = list(
        re.finditer(
            r"\b(?:this|next|the)?\s*"
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
            r"(?:'s)?(?:\s+(?:slot|truck|unload window|receipt|window))?",
            lowered,
        )
    )
    if not matches:
        return None

    anchor = after if after else email_day
    for match in matches:
        phrase = match.group(0)
        weekday = match.group(1)
        if "next" in phrase:
            candidate = next_weekday_after(email_day + timedelta(days=7), weekday)
        else:
            candidate = next_weekday_after(anchor, weekday, strictly_after=after is not None)
        if after is None or candidate > after:
            return candidate
    return None


def extract_date_after_markers(text: str, markers: List[str]) -> Optional[str]:
    lowered = text.lower()
    for marker in markers:
        idx = lowered.find(marker)
        if idx >= 0:
            snippet = text[idx : idx + 180]
            dates = parse_explicit_dates(snippet)
            if dates:
                return dates[0]
    return None


def extract_original_eta(text: str, email_day: date) -> Optional[str]:
    explicit = extract_date_after_markers(
        text,
        [
            "original eta",
            "expected on",
            "was expected on",
            "lined up for",
            "not arrive on",
            "misses",
            "miss the original eta",
            "do not plan against",
            "not going to make",
        ],
    )
    if explicit:
        return explicit

    lowered = text.lower()
    original_markers = [
        "lined up for",
        "tied to",
        "misses",
        "do not plan against",
        "current departure tied to",
    ]
    for marker in original_markers:
        idx = lowered.find(marker)
        if idx >= 0:
            candidate = next_named_weekday(text[idx : idx + 170], email_day)
            if candidate:
                return candidate.isoformat()
    return None


def extract_revised_eta(text: str, email_day: date, original_eta: Optional[str]) -> Optional[str]:
    explicit = extract_date_after_markers(
        text,
        [
            "revised eta",
            "will arrive on",
            "should follow",
            "latest dock booking points to",
            "earliest replacement space",
            "not going to make",
            "use next",
            "use the",
            "remainder will arrive",
        ],
    )
    if explicit:
        return explicit

    lowered = text.lower()
    after_date = date.fromisoformat(original_eta) if original_eta else None
    revised_markers = [
        "earliest replacement space",
        "should follow",
        "use next",
        "use the",
        "latest dock booking points to",
        "points to",
        "remainder will arrive",
    ]
    for marker in revised_markers:
        idx = lowered.find(marker)
        if idx >= 0:
            candidate = next_named_weekday(text[idx : idx + 170], email_day, after=after_date)
            if candidate:
                return candidate.isoformat()
    return None


def extract_quantity(text: str) -> Optional[int]:
    lowered = text.lower()
    unit_patterns = [
        r"\b(?:impacted|affected|delayed|canceled|cancelled)\s+quantity\s*(?:is|:)\s*(\d+)\s+units\b",
        r"\b(\d+)\s+units\s+will\s+miss\b",
        r"\bcancel\s+(\d+)\s+units\b",
        r"\bdelayed\s+quantity\s+is\s+(\d+)\s+units\b",
    ]
    for pattern in unit_patterns:
        match = re.search(pattern, lowered)
        if match:
            return int(match.group(1))

    cases_match = re.search(r"\b(\d+)\s+cases?\b", lowered)
    loose_match = re.search(r"\bplus\s+(\d+)\s+loose\s+units?\b", lowered)
    pack_match = re.search(r"\b(?:case pack|case pack still at|usual|unchanged)\D{0,20}(\d+)[-\s]*unit\b", lowered)
    if not pack_match:
        pack_match = re.search(r"\bcase pack still at\s+(\d+)\b", lowered)
    if cases_match and pack_match:
        loose = int(loose_match.group(1)) if loose_match else 0
        return int(cases_match.group(1)) * int(pack_match.group(1)) + loose
    return None


def infer_disruption_type(text: str) -> Optional[str]:
    lowered = text.lower()
    if any(term in lowered for term in ["cancel", "cancellation", "off the board", "not shipping on this cycle"]):
        return "shipment_cancellation"
    if any(term in lowered for term in ["correction", "corrected", "do not plan against"]):
        return "corrected_update"
    if any(term in lowered for term in ["partial shipment", "first wave", "only a partial shipment"]):
        return "partial_shipment"
    if any(
        term in lowered
        for term in [
            "delayed",
            "revised eta",
            "not going to make",
            "latest dock booking",
            "replacement space",
        ]
    ):
        return "lead_time_delay"
    return None


def candidate_score(email: Dict, focal_sku: str, focal_location: str) -> int:
    text = combined_text(email)
    lowered = text.lower()
    if focal_sku.lower() not in lowered:
        return -100
    if focal_location.lower() not in lowered:
        return -20
    if any(phrase in lowered for phrase in EXCLUSION_PHRASES):
        return -50

    score = 0
    if "correction" in lowered or "do not plan against" in lowered:
        score += 40
    if any(term in lowered for term in ["cancel", "cancellation", "off the board", "not shipping"]):
        score += 35
    if any(term in lowered for term in ["partial shipment", "first wave"]):
        score += 30
    if any(term in lowered for term in ["delayed", "not going to make", "revised eta", "latest dock booking", "replacement space"]):
        score += 25
    if "held portion" in lowered or "impacted portion" in lowered:
        score += 10
    if parse_explicit_dates(text):
        score += 5
    if extract_quantity(text) is not None:
        score += 5
    return score


def extract_packet(packet: Dict) -> Dict:
    packet_id = packet["packet_id"]
    focal_record = packet["inventory_records"][0]
    focal_sku = focal_record["sku"]
    focal_location = focal_record["location"]

    scored = []
    for email in packet["emails"]:
        score = candidate_score(email, focal_sku, focal_location)
        if score > 0:
            scored.append((score, parse_timestamp(email["timestamp"]), email))

    if not scored:
        return empty_prediction(packet_id)

    scored.sort(key=lambda row: (row[0], row[1], row[2]["email_id"]))
    _, _, email = scored[-1]
    text = combined_text(email)
    email_day = parse_timestamp(email["timestamp"])
    disruption_type = infer_disruption_type(text)
    original_eta = extract_original_eta(text, email_day)
    revised_eta = None if disruption_type == "shipment_cancellation" else extract_revised_eta(text, email_day, original_eta)
    quantity = extract_quantity(text)

    delay_days = None
    if original_eta and revised_eta:
        delay_days = (date.fromisoformat(revised_eta) - date.fromisoformat(original_eta)).days

    if not disruption_type or not original_eta or quantity is None:
        return empty_prediction(packet_id)

    confidence = 0.82
    if revised_eta or disruption_type == "shipment_cancellation":
        confidence += 0.06
    if parse_explicit_dates(text):
        confidence += 0.04
    if "correction" in text.lower():
        confidence += 0.03

    return {
        "packet_id": packet_id,
        "actionable": True,
        "decisive_email_id": email["email_id"],
        "focal_sku": focal_sku,
        "affected_location": focal_location,
        "disruption_type": disruption_type,
        "original_eta": original_eta,
        "revised_eta": revised_eta,
        "delay_days": delay_days,
        "quantity_affected": quantity,
        "confidence": round(min(confidence, 0.97), 2),
    }


def exact_match(gold: Dict, prediction: Dict) -> bool:
    return all(gold.get(key) == prediction.get(key) for key in CRITICAL_KEYS if key != "confidence")


def score_predictions(packets: List[Dict], predictions: List[Dict]) -> Dict:
    prediction_map = {row["packet_id"]: row for row in predictions}
    field_counts = {key: 0 for key in CRITICAL_KEYS if key != "confidence"}
    misses = []
    exact_count = 0
    for packet in packets:
        pred = prediction_map[packet["packet_id"]]
        gold = packet["gold"]
        is_exact = exact_match(gold, pred)
        exact_count += int(is_exact)
        if not is_exact:
            misses.append(
                {
                    "packet_id": packet["packet_id"],
                    "pattern": packet["pattern"],
                    "noise_tier": packet["noise_tier"],
                    "gold": deepcopy(gold),
                    "prediction": deepcopy(pred),
                }
            )
        for key in field_counts:
            field_counts[key] += int(gold.get(key) == pred.get(key))

    total = len(packets)
    return {
        "packet_count": total,
        "packet_exact_match": exact_count / total if total else 0.0,
        "field_accuracy": {key: value / total if total else 0.0 for key, value in field_counts.items()},
        "misses": misses,
    }


def build_summary(score: Dict, input_path: Path) -> str:
    lines = [
        "# Rule-Based Extractor Evaluation",
        "",
        "## Design",
        "",
        f"- Input file: `{input_path}`",
        f"- Packets: {score['packet_count']}",
        "- Calibration rule: this parser was designed against pilot packets only.",
        "- Realistic system interpretation: ERP scope supplies the focal SKU/location; deterministic text rules parse supplier emails into the same JSON schema used by the LLM.",
        "- The parser does not read `gold`, `thread_type`, or `is_actionable` during extraction.",
        "",
        "## Accuracy",
        "",
        "| Metric | Accuracy |",
        "|---|---:|",
        f"| Packet exact match | {score['packet_exact_match']:.3f} |",
    ]
    for key, value in score["field_accuracy"].items():
        lines.append(f"| {key} | {value:.3f} |")

    lines.extend(["", "## Misses", ""])
    if not score["misses"]:
        lines.append("No misses.")
    else:
        lines.extend(["| Packet | Pattern | Noise | Main difference |", "|---|---|---|---|"])
        for miss in score["misses"]:
            diffs = [
                key
                for key in CRITICAL_KEYS
                if key != "confidence" and miss["gold"].get(key) != miss["prediction"].get(key)
            ]
            lines.append(f"| {miss['packet_id']} | {miss['pattern']} | {miss['noise_tier']} | {', '.join(diffs)} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule-based supplier email extractor.")
    parser.add_argument("--input", type=Path, default=Path("data/pilot_packets.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("outputs/rule_based_pilot_predictions.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("outputs/rule_based_pilot_summary.md"))
    args = parser.parse_args()

    packets = read_jsonl(args.input)
    predictions = [extract_packet(packet) for packet in packets]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output, predictions)

    if all("gold" in packet for packet in packets):
        score = score_predictions(packets, predictions)
        args.summary.write_text(build_summary(score, args.input), encoding="utf-8")
        print(f"Packet exact match: {score['packet_exact_match']:.3f}")
        print(f"Summary written to: {args.summary}")
    print(f"Predictions written to: {args.output}")


if __name__ == "__main__":
    main()
