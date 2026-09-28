#!/usr/bin/env python3
"""Select probe-linked examples, or reproduce the earlier scene-median selection.

Run before build_audio_examples.py. No inference is performed.
"""

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

from build_audio_examples import PREDICTION_DIRS, clip_errors, read_rttm, read_tsv, reference_activity


SITE = Path(__file__).resolve().parents[1]
DURATION = 16
SHIFT = 4
SIMILAR_PP = 1.0
PROBE_CASES = [
    dict(sample_id="mvad_Two5__036.000", context_start=24, category="probe-miss",
         title="Overlap recovered", tasks=["Separation-2"], minimum_improved_seeds=3),
    dict(sample_id="mvad_Three3__024.500", context_start=16, category="probe-continuity",
         title="Overlap continuity", tasks=["Separation-2"], minimum_improved_seeds=3),
    dict(sample_id="mvad_Three2__019.500", context_start=12, category="probe-confusion",
         title="Speaker assignment", tasks=["Separation-2"], minimum_improved_seeds=3),
    dict(sample_id="mvad_Two1__009.500", context_start=3.5, category="probe-single-fa",
         title="Fewer false alarms", tasks=["Azimuth", "Elevation", "Distance"],
         minimum_improved_seeds=2),
    dict(sample_id="mvad_Two12__027.500", context_start=21.5, category="probe-azimuth",
         title="Azimuth estimation", tasks=["Azimuth"], minimum_improved_seeds=3,
         expected_focus_activity=[0, 1.989342, .010658, 0]),
    dict(sample_id="mvad_One6__016.500", context_start=10.5, category="probe-single-miss",
         title="Single-speaker speech recovered", tasks=["Azimuth"], minimum_improved_seeds=3),
    dict(sample_id="mvad_Two4__023.500", context_start=16, category="probe-counterexample",
         title="Probe gain without DER gain", tasks=["Separation-2"], minimum_improved_seeds=3),
]


def outcome(gain):
    if gain > SIMILAR_PP:
        return "lower"
    if gain < -SIMILAR_PP:
        return "higher"
    return "similar"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=SITE.parent)
    parser.add_argument("--mode", choices=("probe-linked", "scene-median"), default="probe-linked")
    args = parser.parse_args()
    root = args.project_root.resolve()
    processed = root / "data/processed/MVAD/official_all"
    spatial = defaultdict(list)
    for row in read_tsv(processed / "spatial_frames.tsv"):
        spatial[row["recording_id"]].append(row)
    candidates = []
    for meta in read_tsv(processed / "recordings.tsv"):
        recording = meta["recording_id"]
        ids = [f"speaker_{i}" for i in range(int(meta["num_speakers"]))]
        sources = {"reference": processed / "rttm", **{
            model: root / directory / (recording + ".rttm")
            for model, directory in PREDICTION_DIRS.items()
        }}
        world = meta["world_position_present"] == "1"
        starts = set(range(0, math.floor(float(meta["audio_duration_sec"])) - DURATION + 1, SHIFT))
        if args.mode == "probe-linked":
            starts.update(case["context_start"] for case in PROBE_CASES
                          if case["sample_id"].split("__")[0] == recording)
        for start in sorted(starts):
            end = start + DURATION
            if start < 0 or end > float(meta["audio_duration_sec"]):
                raise ValueError(f"Context outside recording: {recording}/{start}")
            tracks = {key: read_rttm(path, recording, start, end, ids,
                                   unmatched_prefix=None if key == "reference" else key)
                      for key, path in sources.items()}
            seconds = reference_activity(tracks["reference"], DURATION)
            if sum(seconds[1:]) < 4:
                continue
            metrics = {key: clip_errors(tracks["reference"], tracks[key], DURATION)
                       for key in PREDICTION_DIRS}
            frames = [row for row in spatial[recording]
                      if float(row["start_sec"]) < end
                      and float(row["start_sec"]) + float(row["duration_sec"]) > start]
            angles = defaultdict(list)
            valid = 0
            for row in frames:
                if world:
                    okay = (int(row["world_gt_status"]) > 0
                            and .5 <= float(row["distance_m"]) <= 2.5
                            and abs(float(row["azimuth_deg"])) <= 60
                            and abs(float(row["elevation_deg"])) <= 60)
                else:
                    okay = (int(row["image_gt_status"]) > 0
                            and 0 <= float(row["image_x"]) < 640
                            and 0 <= float(row["image_y"]) < 480)
                valid += okay
                if okay and int(row["speech_status"]) > 0:
                    angles[row["speaker_id"]].append(float(row["azimuth_deg"]))
            coverage = valid / len(frames) if frames else 0
            if coverage < .95:
                continue
            gain = metrics["baseline"]["der_percent"] - metrics["sra"]["der_percent"]
            candidates.append(dict(
                recording=recording, start=start, end=end, category="",
                position_space="world" if world else "image",
                position_coverage=coverage,
                motion_degrees=max((max(a) - min(a) for a in angles.values()), default=0),
                active_speakers=len({segment["speaker"] for segment in tracks["reference"]}),
                silence_seconds=seconds[0], single_seconds=seconds[1],
                ov2_seconds=seconds[2], ov3_seconds=seconds[3],
                baseline_der=metrics["baseline"]["der_percent"],
                sra_der=metrics["sra"]["der_percent"], gain_pp=gain, outcome=outcome(gain),
            ))

    ov2 = lambda row: row["ov2_seconds"] >= 4 and row["ov3_seconds"] < 1e-5
    specifications = [
        ("overlap-lower", "Two-speaker overlap", lambda row: ov2(row) and row["outcome"] == "lower"),
        ("overlap-similar", "Two-speaker overlap", lambda row: ov2(row) and row["outcome"] == "similar"),
        ("overlap-higher", "Two-speaker overlap", lambda row: ov2(row) and row["outcome"] == "higher"),
        ("single", "Single speech", lambda row: row["single_seconds"] >= 4 and row["silence_seconds"] >= .5 and row["ov2_seconds"] + row["ov3_seconds"] < 1e-5),
        ("motion", "Speaker motion", lambda row: row["motion_degrees"] >= 12 and row["ov3_seconds"] < 1e-5),
        ("overlap-three", "Three-speaker overlap", lambda row: row["ov3_seconds"] >= 5),
    ]
    selected, used = [], set()
    for category, title, predicate in specifications:
        pool = [row for row in candidates if predicate(row) and row["recording"] not in used]
        if not pool:
            raise RuntimeError(f"No eligible unused recording for {category}")
        world_pool = [row for row in pool if row["position_space"] == "world"]
        if world_pool:
            pool = world_pool
        center = median(row["gain_pp"] for row in pool)
        chosen = min(pool, key=lambda row: (abs(row["gain_pp"] - center), row["recording"], row["start"]))
        chosen = dict(chosen, category=category, title=title, eligible_pool_size=len(pool))
        selected.append(chosen)
        used.add(chosen["recording"])

    if args.mode == "probe-linked":
        with (SITE / "scripts/probe_example_audit/all_candidates.csv").open() as source:
            audited = {(row["sample_id"], row["task"]): row for row in csv.DictReader(source)}
        selected = []
        for case in PROBE_CASES:
            sample_id, context_start = case["sample_id"], case["context_start"]
            category, title = case["category"], case["title"]
            for task in case["tasks"]:
                probe = audited[sample_id, task]
                if (int(probe["improved_probe_seeds"]) < case["minimum_improved_seeds"]
                        or float(probe["probe_gain"]) <= 0):
                    raise ValueError(f"Unexpected probe outcome: {sample_id}/{task}")
            expected_sign = -1 if category == "probe-counterexample" else 1
            if expected_sign * float(probe["der_gain"]) <= 1:
                raise ValueError(f"Unexpected DER outcome: {sample_id}")
            context = next(row for row in candidates if row["recording"] == probe["recording"]
                           and row["start"] == context_start)
            focus_start, focus_end = float(probe["start"]), float(probe["end"])
            if not context["start"] <= focus_start < focus_end <= context["end"]:
                raise ValueError(f"Probe window outside context: {sample_id}")
            selected.append(dict(context, category=category, title=title,
                                 probe_sample_id=sample_id, focus_start=focus_start,
                                 focus_end=focus_end, probe_tasks=case["tasks"],
                                 minimum_improved_seeds=case["minimum_improved_seeds"],
                                 expected_focus_activity=case.get("expected_focus_activity")))

    with (SITE / "scripts/example_candidates.csv").open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=candidates[0].keys())
        writer.writeheader()
        writer.writerows(candidates)
    report = dict(
        protocol=dict(
            window_seconds=DURATION, shift_seconds=SHIFT, similar_der_threshold_pp=SIMILAR_PP,
            minimum_speech_seconds=4, minimum_position_coverage=.95,
            rule="Scene/outcome strata; prefer world coordinates when available; choose the eligible window nearest the stratum's median DER gain, with recording/start tie breaks and distinct recordings. Not a maximum-gain selection.",
            limitation="Outcome-stratified qualitative examples, not an estimate of improvement frequency or overall performance; similar denotes a descriptive +/-1 pp band, not statistical equivalence.",
            comparison="Exact interval DER from existing oracle-stitch predictions, zero collar, including reference silence and overlap. No per-clip relabeling.",
        ),
        candidate_count=len(candidates), examples=selected,
    )
    report["protocol"]["mode"] = args.mode
    if args.mode == "probe-linked":
        report["protocol"]["rule"] = "Four displayed joint-improvement examples: three OV2 Separation-2 windows and the Two1 Single window with Azimuth/Elevation/Distance. Two12, One6 and a counterexample are retained in the data but hidden by the renderer. Two12 retains all frames, including 0.010658 s of overlap under exact RTTM scoring despite its frame-sampled Single cohort. Two1 improves each probe on average and in two seeds; the other examples improve their probe in all three seeds. Each has a fixed 16-s context. The focus intervals, expected reference activity and required seed counts are explicitly specified in PROBE_CASES."
        report["protocol"]["limitation"] = "Outcome-selected qualitative illustrations, not representative performance or evidence of causal coupling. Probe and diarization metrics refer to the identical highlighted 2-s window; full-context DER is reported separately."
    (SITE / "scripts/example_selection.json").write_text(json.dumps(report, indent=2) + "\n")
    for row in selected:
        print(f"{row['category']:16s} {row['recording']:14s} {row['start']:g}-{row['end']:g}s "
              f"{row['baseline_der']:.2f} -> {row['sra_der']:.2f} ({row['gain_pp']:+.2f} pp); "
              f"OV2={row['ov2_seconds']:.2f}s OV3={row['ov3_seconds']:.2f}s")


if __name__ == "__main__":
    main()
