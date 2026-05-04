from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_experiment import load_existing_packets, packet_prompt_requests, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare LLM request JSONL files from the current extraction prompt.")
    parser.add_argument(
        "--split",
        choices=["pilot", "scored", "all"],
        default="all",
        help="Which packet split to prepare.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    outputs_dir = root / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    prompt_text = (root / "extraction_prompt.md").read_text(encoding="utf-8")
    schema = json.loads((root / "extraction_schema.json").read_text(encoding="utf-8"))
    dataset = load_existing_packets(data_dir)

    outputs = []
    if args.split in {"pilot", "all"}:
        pilot_requests = packet_prompt_requests(dataset["pilot"], prompt_text, schema)
        pilot_path = outputs_dir / "pilot_llm_requests.jsonl"
        write_jsonl(pilot_path, pilot_requests)
        outputs.append((pilot_path, len(pilot_requests)))

    if args.split in {"scored", "all"}:
        scored_requests = packet_prompt_requests(dataset["scored"], prompt_text, schema)
        scored_path = outputs_dir / "llm_requests.jsonl"
        write_jsonl(scored_path, scored_requests)
        outputs.append((scored_path, len(scored_requests)))

    for path, count in outputs:
        print(f"Wrote {count} requests to {path}")


if __name__ == "__main__":
    main()
