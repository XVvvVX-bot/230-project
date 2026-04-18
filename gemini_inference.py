from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def read_jsonl(path: Path) -> List[Dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_json_text(raw_text: str) -> Dict:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def normalize_prediction(packet_id: str, payload: Dict) -> Dict:
    normalized = {
        "packet_id": packet_id,
        "actionable": payload.get("actionable", False),
        "decisive_email_id": payload.get("decisive_email_id"),
        "focal_sku": payload.get("focal_sku"),
        "affected_location": payload.get("affected_location"),
        "disruption_type": payload.get("disruption_type"),
        "original_eta": payload.get("original_eta"),
        "revised_eta": payload.get("revised_eta"),
        "delay_days": payload.get("delay_days"),
        "quantity_affected": payload.get("quantity_affected"),
        "confidence": payload.get("confidence", 0.0),
    }
    if normalized["packet_id"] != packet_id:
        normalized["packet_id"] = packet_id
    return normalized


def gemini_request_body(request_row: Dict) -> Dict:
    temperature = float(os.environ.get("GEMINI_TEMPERATURE", "0"))
    contents = []
    for message in request_row["messages"]:
        role = "model" if message["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": message["content"]}]})
    return {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseJsonSchema": request_row["schema"],
        },
    }


def call_gemini(request_row: Dict) -> Dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")

    packet_id = request_row["packet_id"]
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    api_base = os.environ.get("GEMINI_API_BASE", DEFAULT_GEMINI_API_BASE).rstrip("/")
    timeout = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "90"))
    retries = int(os.environ.get("GEMINI_MAX_RETRIES", "4"))
    url = f"{api_base}/models/{model}:generateContent"
    payload = gemini_request_body(request_row)
    body = json.dumps(payload).encode("utf-8")

    for attempt in range(retries + 1):
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_json = json.loads(response.read().decode("utf-8"))
            candidates = response_json.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"Gemini returned no candidates for {packet_id}: {response_json}")
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts if "text" in part).strip()
            if not text:
                raise RuntimeError(f"Gemini returned no text for {packet_id}: {response_json}")
            return normalize_prediction(packet_id, parse_json_text(text))
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
            if attempt >= retries:
                raise RuntimeError(f"Gemini request failed for {packet_id}: {exc}") from exc
            time.sleep(min(2**attempt, 8))


def run_gemini_predictions(request_rows: List[Dict], output_path: Path) -> List[Dict]:
    existing = {}
    if output_path.exists():
        existing = {row["packet_id"]: row for row in read_jsonl(output_path)}

    predictions = []
    total = len(request_rows)
    for idx, request_row in enumerate(request_rows, 1):
        packet_id = request_row["packet_id"]
        if packet_id in existing:
            prediction = existing[packet_id]
        else:
            print(f"[Gemini] {idx}/{total} {packet_id}")
            prediction = call_gemini(request_row)
            existing[packet_id] = prediction
            ordered_rows = [existing[row["packet_id"]] for row in request_rows if row["packet_id"] in existing]
            write_jsonl(output_path, ordered_rows)
            delay = float(os.environ.get("GEMINI_DELAY_SECONDS", "0"))
            if delay > 0:
                time.sleep(delay)
        predictions.append(prediction)
    return predictions
