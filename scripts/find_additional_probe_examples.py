#!/usr/bin/env python3
"""Recheck Azimuth/Distance examples with a fixed 16-s context; no inference."""

import hashlib
import json
import math
from collections import defaultdict
from functools import lru_cache

import numpy as np
import pandas as pd

from build_audio_examples import (
    PREDICTION_DIRS, SITE, clip_errors, read_rttm, read_tsv, reference_activity,
)


ROOT = SITE.parent
DESTINATION = SITE / "scripts/probe_example_audit"
EPSILON = 1e-8
MODELS = {"baseline": "ID8", "sra": "ID8-SARR"}


def main():
    audit_path = DESTINATION / "all_candidates.csv"
    prediction_path = ROOT / "exp17_final_prob/results/confidence_probe_oof_predictions.csv"
    processed = ROOT / "data/processed/MVAD/official_all"
    audit = pd.read_csv(audit_path)
    predictions = pd.read_csv(prediction_path)
    recordings = {r["recording_id"]: r for r in read_tsv(processed / "recordings.tsv")}
    positions = defaultdict(list)
    for row in read_tsv(processed / "spatial_frames.tsv"):
        positions[row["recording_id"]].append(row)
    packaged_path = SITE / "assets/audio-examples.json"
    displayed = {c["recording"] for c in json.loads(packaged_path.read_text())["examples"]
                 if c["category"] not in ("probe-counterexample", "probe-single-miss", "probe-azimuth")}
    sources = {audit_path, prediction_path, packaged_path,
               processed / "recordings.tsv", processed / "spatial_frames.tsv"}

    @lru_cache(None)
    def tracks(recording):
        meta = recordings[recording]
        ids = [f"speaker_{i}" for i in range(int(meta["num_speakers"]))]
        paths = {"reference": processed / "rttm", **{
            key: ROOT / directory / f"{recording}.rttm"
            for key, directory in PREDICTION_DIRS.items()}}
        sources.update(paths.values())
        return {key: read_rttm(path, recording, 0, float(meta["audio_duration_sec"]), ids,
                               unmatched_prefix=None if key == "reference" else key)
                for key, path in paths.items()}

    @lru_cache(None)
    def score(recording, start, end):
        cropped = {key: [dict(speaker=s["speaker"],
                              start=round(max(start, s["start"])-start, 6),
                              end=round(min(end, s["end"])-start, 6))
                         for s in segments if s["start"] < end and s["end"] > start]
                   for key, segments in tracks(recording).items()}
        return ({key: clip_errors(cropped["reference"], cropped[key], end-start)
                 for key in MODELS}, reference_activity(cropped["reference"], end-start))

    def coverage(recording, start, end):
        world = recordings[recording]["world_position_present"] == "1"
        valid, total = 0, 0
        for r in positions[recording]:
            t = float(r["start_sec"])
            if t >= end or t+float(r["duration_sec"]) <= start:
                continue
            total += 1
            if world:
                okay = (int(r["world_gt_status"]) > 0
                        and .5 <= float(r["distance_m"]) <= 2.5
                        and abs(float(r["azimuth_deg"])) <= 60
                        and abs(float(r["elevation_deg"])) <= 60)
            else:
                okay = (int(r["image_gt_status"]) > 0
                        and 0 <= float(r["image_x"]) < 640
                        and 0 <= float(r["image_y"]) < 480)
            valid += okay
        return valid/total if total else 0

    rows = []
    eligible = audit[audit.task.isin(["Azimuth", "Distance"])
                     & audit.probe_gain.gt(EPSILON) & audit.der_gain.gt(EPSILON)]
    for row in eligible.to_dict("records"):
        recording = row["recording"]
        # The same context rule is used for every candidate, without searching for a better crop.
        last_boundary = math.floor(float(recordings[recording]["audio_duration_sec"])*2)/2
        context_start = max(0, min(row["start"]-6, last_boundary-16))
        context_end = context_start+16
        if not 0 <= context_start <= row["start"] < row["end"] <= context_end <= last_boundary:
            raise ValueError(f"Invalid context: {row['sample_id']}")
        local, activity = score(recording, row["start"], row["end"])
        context, _ = score(recording, context_start, context_end)
        pred = predictions[predictions.sample_id.eq(row["sample_id"])
                           & predictions.task.eq(row["task"])
                           & predictions.site.eq("F")
                           & predictions.model_id.isin(MODELS.values())]
        seed_errors = {}
        for key, model in MODELS.items():
            group = pred[pred.model_id.eq(model)].sort_values("seed")
            if len(group) != 3 or set(group.seed) != {17, 3407, 2026}:
                raise ValueError(f"Incomplete seeds: {row['sample_id']}/{model}")
            computed = np.abs(group.prediction.to_numpy()-group.label.to_numpy())
            np.testing.assert_allclose(computed, group.absolute_error.to_numpy(), atol=1e-9, rtol=0)
            np.testing.assert_allclose(computed.mean(), row[f"{key}_F_mae"], atol=1e-9, rtol=0)
            np.testing.assert_allclose(local[key]["der_percent"], row[f"{key}_der"], atol=1e-5, rtol=0)
            seed_errors[key] = computed
        gains = seed_errors["baseline"]-seed_errors["sra"]
        row.update(
            improved_probe_seeds=int((gains > EPSILON).sum()),
            unchanged_probe_seeds=int((np.abs(gains) <= EPSILON).sum()),
            degraded_probe_seeds=int((gains < -EPSILON).sum()),
            strict_single=activity == [0, 2, 0, 0],
            reference_silence_seconds=activity[0], reference_ov_seconds=sum(activity[2:]),
            context_start=context_start, context_end=context_end,
            context_baseline_der=context["baseline"]["der_percent"],
            context_sra_der=context["sra"]["der_percent"],
            context_der_gain=context["baseline"]["der_percent"]-context["sra"]["der_percent"],
            position_coverage=coverage(recording, context_start, context_end),
            already_displayed_recording=recording in displayed,
            previously_removed_recording=recording in ("mvad_One6", "mvad_Two12"),
        )
        for key in MODELS:
            for component in ("miss", "false_alarm", "confusion"):
                row[f"{key}_{component}_seconds"] = local[key][component]
        rows.append(row)

    result = pd.DataFrame(rows).sort_values(["task", "der_gain", "probe_gain"], ascending=[True, False, False])
    result.to_csv(DESTINATION / "additional_spatial_candidates.csv", index=False)
    report = dict(
        protocol="Existing F-probe OOF predictions, all three seeds; same 2-s local RTTM score. Fixed 16-s context beginning 6 s before each probe window, clipped to recording boundaries on a 0.5-s grid. Context endpoints are not optimized by DER. Exact RTTM activity is checked separately from the frame-sampled probe manifest.",
        tasks={},
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(sources)},
    )
    for task in ("Azimuth", "Distance"):
        candidates = result[result.task.eq(task)]
        kept = candidates[candidates.context_der_gain.gt(EPSILON)
                          & candidates.position_coverage.ge(.95)]
        report["tasks"][task] = dict(
            total_probe_windows=int(audit.task.eq(task).sum()),
            local_joint_improvements=len(candidates),
            context_joint_improvements=len(kept),
            context_recordings=sorted(kept.recording.unique().tolist()),
            new_recordings=sorted(kept[~kept.already_displayed_recording].recording.unique().tolist()),
        )
    (DESTINATION / "additional_spatial_audit.json").write_text(json.dumps(report, indent=2)+"\n")
    lines = ["# Additional Azimuth and Distance examples", "", report["protocol"], "",
             "Values are S-DiariZen -> S-DiariZen-SRA. Probe values are three-seed F MAE, not a selected seed. These are outcome-selected qualitative candidates. No demo assets or model outputs are changed.", "",
             "| File | Probe window (s) | Task | F MAE | Local DER (%) | Context (s) | Context DER (%) | Improved/tied/worse seeds | Exact Single | Position coverage |",
             "|---|---:|---|---:|---:|---:|---:|---|---|---:|"]
    chosen = [("mvad_One3__053.500", "Azimuth"),
              ("mvad_Two12__027.500", "Azimuth"),
              ("mvad_One7__022.000", "Distance")]
    for sample_id, task in chosen:
        r = result[result.sample_id.eq(sample_id) & result.task.eq(task)].iloc[0]
        decimals = 3 if task == "Distance" else 2
        unit = "m" if task == "Distance" else "deg"
        lines.append(f"| {r.recording.removeprefix('mvad_')}.wav | {r.start:g}-{r.end:g} | {task} | {r.baseline_F_mae:.{decimals}f} -> {r.sra_F_mae:.{decimals}f} {unit} | {r.baseline_der:.2f} -> {r.sra_der:.2f} | {r.context_start:g}-{r.context_end:g} | {r.context_baseline_der:.2f} -> {r.context_sra_der:.2f} | {r.improved_probe_seeds}/{r.unchanged_probe_seeds}/{r.degraded_probe_seeds} | {bool(r.strict_single)} | {r.position_coverage:.1%} |")
    lines += ["",
              "- One3 removes 0.093 speaker-seconds of miss in the probe window. Its long context improves but still has high DER; only image positions are available.",
              "- Two12 removes 0.061 speaker-seconds of false alarm. Its probe manifest labels the window Single, but exact RTTM scoring finds 0.010658 s of overlap at the edge. The packaged data explicitly validates this activity distribution and retains all frames. It is excluded from the page because the diarization improvement is visually modest.",
              "- One7 removes only 0.020 speaker-seconds of miss. Distance improves in two seeds with one tie; Azimuth is unchanged and Elevation worsens. It is not a multi-attribute win.",
              "- Other Distance joint-improvement windows are adjacent to the existing Two1 example or have worse fixed-context DER (Two4 and Two5). One6 remains excluded because its fixed-context DER worsens.",
              "- Every candidate and its context result, including rejected candidates, is saved in additional_spatial_candidates.csv.", "",
              "Reproduce: `.conda/spatialrole/bin/python sra-diarization.github.io/scripts/find_additional_probe_examples.py`", ""]
    (DESTINATION / "ADDITIONAL_SPATIAL_EXAMPLES.md").write_text("\n".join(lines))
    print("\n".join(lines))
    print(json.dumps(report["tasks"], indent=2))


if __name__ == "__main__":
    main()
