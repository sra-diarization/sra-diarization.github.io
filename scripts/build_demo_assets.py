#!/usr/bin/env python3
"""Export Exp17 scores and the paper's four-attribute statistics for the demo.

Run from anywhere: python scripts/build_demo_assets.py [--project-root PATH]
PDF conversion requires PyMuPDF. --data-only reuses the existing SVG artwork.
"""

import argparse
import base64
import csv
import hashlib
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

from build_header_asset import build_assets, read_assets


SITE = Path(__file__).resolve().parents[1]
TASKS = [
    ("Azimuth-2D", "Azimuth", "Horizontal source angle", "Single speaker"),
    ("Elevation-3D", "Elevation", "Vertical source angle", "Single speaker"),
    ("Distance-3D", "Distance", "Source-to-array distance", "Single speaker"),
    ("Separation-2", "Separation-2", "Angular separation of two speakers", "Two-speaker overlap"),
]
TASK_IDS = {task[0] for task in TASKS}
MODELS = {"ID8", "ID8-SARR"}
STATISTICS = Path("_final_submission/probing_four_attribute_stats")


def read_csv(path):
    with path.open(newline="") as source:
        return list(csv.DictReader(source))


def paper_statistics(root):
    transfer_path = root / STATISTICS / "probe_transfer_four.csv"
    comparison_path = root / STATISTICS / "sra_paired_contrasts_four.csv"
    strings = {"kind", "model_id", "source", "site", "task", "metric", "unit", "evidence"}

    def convert(row, q_column):
        return {
            key: value if key in strings else float(value)
            for key, value in row.items()
            if not key.startswith("q_") or key == q_column
        }

    transfers = [
        convert(row, "q_family") for row in read_csv(transfer_path)
        if row["model_id"] in MODELS | {"SARR-minus-ID8"} and row["task"] in TASK_IDS
    ]
    comparisons = [
        convert(row, "q_site") for row in read_csv(comparison_path)
        if row["task"] in TASK_IDS
    ]
    for rows, keys, q_column, expected_families in (
        (transfers, ("kind", "model_id", "source"), "q_family", 6),
        (comparisons, ("site",), "q_site", 3),
    ):
        families = defaultdict(list)
        for row in rows:
            assert math.isfinite(row[q_column]) and 0 <= row[q_column] <= 1
            assert row["n_folds"] == 5 and row["df"] == 4
            families[tuple(row[key] for key in keys)].append(row["task"])
        assert len(families) == expected_families, "Unexpected paper contrast families"
        assert all(len(tasks) == 4 and set(tasks) == TASK_IDS for tasks in families.values())
    metadata = dict(
        test="Two-sided paired t-test on five fold means after averaging three probe seeds per fold",
        correction="Benjamini-Hochberg",
        family_size=4,
        targets=[task[0] for task in TASKS],
        correction_label="BH correction across four reported attributes",
        transfer_family=["kind", "model_id", "source"],
        comparison_family=["site"],
        source_files={str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (transfer_path, comparison_path)},
    )
    return transfers, comparisons, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=SITE.parent)
    parser.add_argument("--data-only", action="store_true",
                        help="Refresh scores, statistics and reference PNG without reconverting the PDF")
    args = parser.parse_args()
    results = args.project_root / "exp17_final_prob/results"
    rows = [r for r in read_csv(results / "probe_summary.csv")
            if r["model_id"] in MODELS and r["task"] in TASK_IDS]
    assert len(rows) == 24, "Expected four tasks at three sites for two models"
    keys = [(r["model_id"], r["site"], r["task"]) for r in rows]
    assert len(set(keys)) == len(rows), "Duplicate probe results"
    transfers, comparisons, statistics = paper_statistics(args.project_root)
    reference_plot = "_final_submission/figures/id8_spatial_dilution.png"
    if not (args.project_root / reference_plot).is_file():
        raise FileNotFoundError(f"Missing paper reference figure: {reference_plot}")

    protocol = json.loads((results / "protocol.json").read_text())
    with (args.project_root / "exp03_prob_MVAD/data/windows.tsv").open(newline="") as source:
        windows = list(csv.DictReader(source, delimiter="\t"))
    labels = {t["name"]: t["label"] for t in protocol["tasks"]}
    tasks = []
    for task_id, title, description, cohort in TASKS:
        count = sum(w[labels[task_id]] not in ("", "nan", "NaN") for w in windows)
        tasks.append(dict(id=task_id, title=title, description=description, cohort=cohort, windows=count))

    scores = []
    strings = {"model_id", "site", "task", "metric", "unit"}
    for row in rows:
        scores.append({k: v if k in strings else float(v) for k, v in row.items()})
    if not args.data_only:
        build_assets(SITE / "assets")
    svg, baseline_svg, diagram = read_assets(SITE / "assets")
    data = dict(
        source="exp17_final_prob/results/probe_summary.csv",
        source_sha256=hashlib.sha256((results / "probe_summary.csv").read_bytes()).hexdigest(),
        reference_plot="_final_submission/audit_scripts/recompute_four_attribute_q.py",
        tasks=tasks, scores=scores, transfers=transfers, comparisons=comparisons,
        protocol={**{k: protocol[k] for k in ("sites", "probe")}, "statistics": statistics},
        diagram=diagram,
    )
    with (SITE / "assets/probe-scores.csv").open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    shutil.copyfile(args.project_root / reference_plot, SITE / "assets/id8_spatial_dilution.png")
    (SITE / "assets/probe-data.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    # Classic script + embedded vectors also work when index.html is opened via file://.
    data["diagram"]["image"] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    data["diagram"]["baseline_image"] = "data:image/svg+xml;base64," + base64.b64encode(baseline_svg.encode()).decode()
    (SITE / "assets/probe-data.js").write_text("window.PROBE_DATA = " + json.dumps(data, separators=(",", ":"), allow_nan=False) + ";\n")
    print(f"Exported {len(scores)} scores, {len(tasks)} tasks, and PDF vectors to {SITE / 'assets'}")


if __name__ == "__main__":
    main()
