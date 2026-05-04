from __future__ import annotations

import argparse
from pathlib import Path

from gemini_inference import read_jsonl, run_gemini_predictions
from run_experiment import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Gemini on a prepared LLM request JSONL file.")
    parser.add_argument("--requests", type=Path, default=Path("outputs/pilot_llm_requests.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("outputs/pilot_actual_llm_predictions.jsonl"))
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete the output file first so Gemini is called again with the current prompt.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")

    request_path = args.requests if args.requests.is_absolute() else root / args.requests
    output_path = args.output if args.output.is_absolute() else root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.overwrite and output_path.exists():
        output_path.unlink()

    request_rows = read_jsonl(request_path)
    predictions = run_gemini_predictions(request_rows, output_path)
    print(f"Wrote {len(predictions)} predictions to {output_path}")


if __name__ == "__main__":
    main()
