from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
VIZ = ROOT / "visualizations"

ARM_ORDER = ["hybrid_llm_human", "llm_agent", "rule_system", "human_planner"]
ARM_LABELS = {
    "hybrid_llm_human": "Hybrid LLM + Human",
    "llm_agent": "LLM Agent",
    "rule_system": "Rule System",
    "human_planner": "Human Planner",
}
COLORS = {
    "hybrid_llm_human": "#2D6A4F",
    "llm_agent": "#1D4E89",
    "rule_system": "#9A7B16",
    "human_planner": "#B24C3A",
    "oracle": "#666666",
}
INK = "#1F2528"
MUTED = "#697177"
GRID = "#D4D8DC"
BORDER = "#AEB6BD"


def read_csv(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def f(row: Dict, key: str) -> float:
    return float(row[key])


def fmt(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}"


def svg_open(width: int, height: int) -> List[str]:
    return [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<style>",
        "text{font-family:Georgia,'Times New Roman',serif;fill:#1F2528}.sans{font-family:Arial,sans-serif}.title{font-size:24px;font-weight:700}.subtitle{font-size:13px;fill:#697177}.small{font-size:12px;fill:#697177}.label{font-size:14px}.value{font-size:20px;font-weight:700}.grid{stroke:#D4D8DC;stroke-width:1}.axis{stroke:#1F2528;stroke-width:1.3}.card{fill:#FFFFFF;stroke:#AEB6BD;stroke-width:1.2}",
        "</style>",
    ]


def finish(parts: List[str], path: Path) -> None:
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def cost_cards(path: Path, arm_rows: List[Dict]) -> None:
    rows = [row for row in arm_rows if row["arm"] in ARM_ORDER]
    rows = sorted(rows, key=lambda row: f(row, "mean_total_cost"))
    width, height = 1100, 620
    parts = svg_open(width, height)
    parts += [
        "<text class='title' x='60' y='58'>Total Exception Cost by Workflow</text>",
        "<text class='subtitle sans' x='60' y='84'>Lower is better. Costs include stockout, holding, action, and evidence-anchored processing costs.</text>",
    ]
    max_cost = max(f(row, "mean_total_cost") for row in rows)
    min_cost = min(f(row, "mean_total_cost") for row in rows)
    card_w, card_h = 235, 340
    start_x, y = 58, 145
    for idx, row in enumerate(rows):
        arm = row["arm"]
        x = start_x + idx * (card_w + 25)
        cost = f(row, "mean_total_cost")
        delta = cost - min_cost
        service = f(row, "mean_service_level")
        loss = f(row, "mean_service_loss_vs_baseline")
        fill = COLORS[arm]
        parts += [
            f"<rect class='card' x='{x}' y='{y}' width='{card_w}' height='{card_h}' rx='8'/>",
            f"<line x1='{x+18}' y1='{y+18}' x2='{x+card_w-18}' y2='{y+18}' stroke='{fill}' stroke-width='5' stroke-linecap='round'/>",
            f"<text class='small sans' x='{x+22}' y='{y+46}'>Rank {idx+1}</text>",
            f"<text class='label' x='{x+22}' y='{y+78}'>{ARM_LABELS[arm]}</text>",
            f"<text class='value sans' x='{x+22}' y='{y+126}'>${fmt(cost, 0)}</text>",
            f"<text class='small sans' x='{x+22}' y='{y+150}'>mean total cost</text>",
            f"<text class='small sans' x='{x+22}' y='{y+193}'>Gap vs best</text>",
            f"<text class='label sans' x='{x+22}' y='{y+220}'>+${fmt(delta, 0)}</text>",
            f"<text class='small sans' x='{x+22}' y='{y+262}'>Service level</text>",
            f"<text class='label sans' x='{x+22}' y='{y+289}'>{service:.3f}</text>",
            f"<text class='small sans' x='{x+22}' y='{y+322}'>Service loss vs baseline: {loss:.3f}</text>",
        ]
        bar_h = 88 * (cost - min_cost) / max(max_cost - min_cost, 1)
        parts.append(f"<rect x='{x+178}' y='{y+218-bar_h:.1f}' width='28' height='{bar_h+14:.1f}' rx='5' fill='{fill}' opacity='0.78'/>")
    parts += [
        "<text class='subtitle sans' x='60' y='555'>Interpretation: the hybrid workflow has the lowest total cost because fast LLM triage reduces delay while human approval corrects high-impact extraction errors.</text>"
    ]
    finish(parts, path)


def service_loss_lollipop(path: Path, arm_rows: List[Dict]) -> None:
    rows = [row for row in arm_rows if row["arm"] in ARM_ORDER]
    rows = sorted(rows, key=lambda row: f(row, "mean_service_loss_vs_baseline"))
    width, height = 980, 520
    parts = svg_open(width, height)
    parts += [
        "<text class='title' x='62' y='58'>Service Loss Relative to No-Disruption Baseline</text>",
        "<text class='subtitle sans' x='62' y='84'>This avoids over-interpreting raw service levels and isolates disruption-response impact.</text>",
    ]
    x0, x1 = 310, 880
    y0, step = 160, 74
    max_loss = max(f(row, "mean_service_loss_vs_baseline") for row in rows) * 1.15
    for i in range(6):
        value = max_loss * i / 5
        x = x0 + value / max_loss * (x1 - x0)
        parts += [
            f"<line x1='{x:.1f}' y1='128' x2='{x:.1f}' y2='430' class='grid'/>",
            f"<text class='small sans' x='{x:.1f}' y='455' text-anchor='middle'>{value:.2f}</text>",
        ]
    for idx, row in enumerate(rows):
        arm = row["arm"]
        loss = f(row, "mean_service_loss_vs_baseline")
        x = x0 + loss / max_loss * (x1 - x0)
        y = y0 + idx * step
        parts += [
            f"<text class='label' x='62' y='{y+5}'>{ARM_LABELS[arm]}</text>",
            f"<line x1='{x0}' y1='{y}' x2='{x:.1f}' y2='{y}' stroke='{COLORS[arm]}' stroke-width='8' stroke-linecap='round' opacity='0.45'/>",
            f"<circle cx='{x:.1f}' cy='{y}' r='15' fill='{COLORS[arm]}'/>",
            f"<text class='label sans' x='{x+24:.1f}' y='{y+5}'>{loss:.3f}</text>",
        ]
    parts.append("<text class='small sans' x='595' y='485' text-anchor='middle'>service loss</text>")
    finish(parts, path)


def cutoff_timing_panel(path: Path, cutoff_rows: List[Dict]) -> None:
    rows = [row for row in cutoff_rows if row["arm"] in ARM_ORDER]
    tiers = ["easy", "moderate", "tight", "near_impossible"]
    width, height = 1080, 610
    parts = svg_open(width, height)
    parts += [
        "<text class='title' x='62' y='58'>Who Acts Before the Operational Cutoff?</text>",
        "<text class='subtitle sans' x='62' y='84'>Panels show before-cutoff detection rate; darker and longer means more timely response.</text>",
    ]
    panel_w, panel_h = 230, 360
    start_x, start_y = 58, 140
    lookup = {(row["cutoff_tier"], row["arm"]): f(row, "before_cutoff_rate") for row in rows}
    for t_idx, tier in enumerate(tiers):
        x = start_x + t_idx * (panel_w + 22)
        parts += [
            f"<rect class='card' x='{x}' y='{start_y}' width='{panel_w}' height='{panel_h}' rx='8'/>",
            f"<text class='label' x='{x+20}' y='{start_y+38}'>{tier.replace('_', ' ').title()}</text>",
        ]
        for a_idx, arm in enumerate(ARM_ORDER):
            rate = lookup.get((tier, arm), 0.0)
            y = start_y + 82 + a_idx * 62
            bar_w = 150 * rate
            parts += [
                f"<text class='small sans' x='{x+20}' y='{y+5}'>{ARM_LABELS[arm]}</text>",
                f"<rect x='{x+20}' y='{y+18}' width='150' height='15' rx='3' fill='#FFFFFF' stroke='{GRID}'/>",
                f"<rect x='{x+20}' y='{y+18}' width='{bar_w:.1f}' height='15' rx='8' fill='{COLORS[arm]}'/>",
                f"<text class='small sans' x='{x+182}' y='{y+31}'>{rate:.2f}</text>",
            ]
    parts.append("<text class='subtitle sans' x='62' y='555'>Human-only loses access to fast corrective actions in tight windows; LLM and rule automation see emails immediately, but extraction quality still determines whether the action is useful.</text>")
    finish(parts, path)


def extraction_radar(path: Path, results: Dict) -> None:
    metrics = [
        ("packet_exact_match", "Packet exact"),
        ("decisive_email_id", "Email ID"),
        ("original_eta", "Original ETA"),
        ("revised_eta", "Revised ETA"),
        ("delay_days", "Delay"),
        ("quantity_affected", "Quantity"),
    ]
    width, height = 820, 680
    cx, cy, radius = 410, 360, 210
    parts = svg_open(width, height)
    parts += [
        "<text class='title' x='60' y='58'>Extraction Accuracy Profile</text>",
        "<text class='subtitle sans' x='60' y='84'>LLM is stronger on flexible interpretation; rules are cheap but brittle on relative dates.</text>",
    ]
    for level in [0.25, 0.5, 0.75, 1.0]:
        pts = []
        for idx, _ in enumerate(metrics):
            angle = -math.pi / 2 + idx * 2 * math.pi / len(metrics)
            pts.append(f"{cx + radius*level*math.cos(angle):.1f},{cy + radius*level*math.sin(angle):.1f}")
        parts.append(f"<polygon points='{' '.join(pts)}' fill='none' stroke='{GRID}' stroke-width='1'/>")
    for idx, (_, name) in enumerate(metrics):
        angle = -math.pi / 2 + idx * 2 * math.pi / len(metrics)
        x = cx + (radius + 54) * math.cos(angle)
        y = cy + (radius + 54) * math.sin(angle)
        parts += [
            f"<line x1='{cx}' y1='{cy}' x2='{cx+radius*math.cos(angle):.1f}' y2='{cy+radius*math.sin(angle):.1f}' class='grid'/>",
            f"<text class='small sans' x='{x:.1f}' y='{y:.1f}' text-anchor='middle'>{name}</text>",
        ]
    for arm in ["llm_agent", "rule_system"]:
        metric_obj = results["extraction_accuracy"][arm]
        pts = []
        for idx, (key, _) in enumerate(metrics):
            value = metric_obj["packet_exact_match"] if key == "packet_exact_match" else metric_obj["field_accuracy"][key]
            angle = -math.pi / 2 + idx * 2 * math.pi / len(metrics)
            pts.append((cx + radius*value*math.cos(angle), cy + radius*value*math.sin(angle)))
        point_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f"<polygon points='{point_str}' fill='{COLORS[arm]}' fill-opacity='0.18' stroke='{COLORS[arm]}' stroke-width='3'/>")
        for x, y in pts:
            parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='4' fill='{COLORS[arm]}'/>")
    parts += [
        f"<rect x='585' y='135' width='14' height='14' fill='{COLORS['llm_agent']}'/><text class='small sans' x='608' y='147'>LLM Agent</text>",
        f"<rect x='585' y='162' width='14' height='14' fill='{COLORS['rule_system']}'/><text class='small sans' x='608' y='174'>Rule System</text>",
    ]
    finish(parts, path)


def pattern_heatmap(path: Path, pattern_rows: List[Dict]) -> None:
    rows = [row for row in pattern_rows if row["arm"] in ARM_ORDER]
    patterns = sorted({row["pattern"] for row in rows})
    lookup = {(row["pattern"], row["arm"]): f(row, "mean_total_cost") for row in rows}
    values = list(lookup.values())
    min_v, max_v = min(values), max(values)
    width, height = 1120, 560
    parts = svg_open(width, height)
    parts += [
        "<text class='title' x='60' y='58'>Cost Heatmap by Disruption Pattern</text>",
        "<text class='subtitle sans' x='60' y='84'>Darker cells indicate higher total cost. The pattern view shows where rule templates or LLM flexibility matter most.</text>",
    ]
    x0, y0 = 255, 130
    cell_w, cell_h = 165, 58
    for a_idx, arm in enumerate(ARM_ORDER):
        x = x0 + a_idx * cell_w
        parts.append(f"<text class='small sans' x='{x+cell_w/2}' y='116' text-anchor='middle'>{ARM_LABELS[arm]}</text>")
    for p_idx, pattern in enumerate(patterns):
        y = y0 + p_idx * cell_h
        parts.append(f"<text class='small sans' x='60' y='{y+35}'>{pattern.replace('_', ' ')}</text>")
        row_values = [lookup[(pattern, arm)] for arm in ARM_ORDER]
        best = min(row_values)
        for a_idx, arm in enumerate(ARM_ORDER):
            value = lookup[(pattern, arm)]
            intensity = (value - min_v) / max(max_v - min_v, 1)
            # White-to-blue scale keeps the heatmap readable in an academic report.
            r = int(248 - 145 * intensity)
            g = int(250 - 130 * intensity)
            b = int(252 - 80 * intensity)
            x = x0 + a_idx * cell_w
            stroke = "#1F2528" if value == best else "#FFFFFF"
            sw = 2.5 if value == best else 1
            parts += [
                f"<rect x='{x}' y='{y}' width='{cell_w-8}' height='{cell_h-8}' rx='4' fill='rgb({r},{g},{b})' stroke='{stroke}' stroke-width='{sw}'/>",
                f"<text class='label sans' x='{x+(cell_w-8)/2}' y='{y+31}' text-anchor='middle'>${fmt(value, 0)}</text>",
            ]
    parts.append("<text class='small sans' x='60' y='510'>Outlined cell marks the lowest-cost workflow for each disruption pattern.</text>")
    finish(parts, path)


def main() -> None:
    VIZ.mkdir(exist_ok=True)
    arm_rows = read_csv(OUTPUTS / "cutoff_experiment_arm_summary.csv")
    pattern_rows = read_csv(OUTPUTS / "cutoff_experiment_by_pattern.csv")
    cutoff_rows = read_csv(OUTPUTS / "cutoff_experiment_by_cutoff.csv")
    results = json.loads((OUTPUTS / "cutoff_experiment_results.json").read_text(encoding="utf-8"))

    cost_cards(VIZ / "01_workflow_cost_cards.svg", arm_rows)
    service_loss_lollipop(VIZ / "02_service_loss_lollipop.svg", arm_rows)
    cutoff_timing_panel(VIZ / "03_cutoff_timing_panel.svg", cutoff_rows)
    extraction_radar(VIZ / "04_extraction_accuracy_radar.svg", results)
    pattern_heatmap(VIZ / "05_pattern_cost_heatmap.svg", pattern_rows)

    write_csv(VIZ / "arm_summary.csv", arm_rows)
    write_csv(VIZ / "pattern_summary.csv", pattern_rows)
    write_csv(VIZ / "cutoff_summary.csv", [row for row in cutoff_rows if row["arm"] != "oracle"])
    print(f"Visualizations written to {VIZ}")


if __name__ == "__main__":
    main()
