from __future__ import annotations

import argparse
from pathlib import Path

from rule_based_extractor import read_jsonl, score_predictions


def build_summary(score: dict, packets_path: Path, predictions_path: Path) -> str:
    lines = [
        "# Extraction Prediction Evaluation",
        "",
        "## Design",
        "",
        f"- Packet file: `{packets_path}`",
        f"- Prediction file: `{predictions_path}`",
        f"- Packets scored: {score['packet_count']}",
        "- Exact match requires every required extraction field to match the gold label.",
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
                for key in [
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
                if miss["gold"].get(key) != miss["prediction"].get(key)
            ]
            lines.append(f"| {miss['packet_id']} | {miss['pattern']} | {miss['noise_tier']} | {', '.join(diffs)} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score extraction predictions against packet gold labels.")
    parser.add_argument("--packets", type=Path, default=Path("data/pilot_packets.jsonl"))
    parser.add_argument("--predictions", type=Path, default=Path("outputs/pilot_actual_llm_predictions.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("outputs/extraction_prediction_summary.md"))
    args = parser.parse_args()

    packets = read_jsonl(args.packets)
    predictions = read_jsonl(args.predictions)
    score = score_predictions(packets, predictions)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(build_summary(score, args.packets, args.predictions), encoding="utf-8")
    print(f"Packet exact match: {score['packet_exact_match']:.3f}")
    print(f"Summary written to: {args.summary}")


if __name__ == "__main__":
    main()
