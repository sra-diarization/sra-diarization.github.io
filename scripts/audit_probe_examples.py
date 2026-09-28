#!/usr/bin/env python3
"""Audit co-occurring probe and diarization improvements without changing the demo.

Use existing recording-disjoint out-of-fold predictions, retain all three
probe seeds, and re-score the identical 2-s interval from original RTTMs.
The output is exploratory: choosing examples by outcome cannot establish a
population association or a causal effect of spatial decodability on DER.
"""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from build_audio_examples import PREDICTION_DIRS, SITE, clip_errors, read_rttm, read_tsv


ROOT = SITE.parent
RESULTS = ROOT / "exp17_final_prob/results"
MANIFEST = ROOT / "exp03_prob_MVAD/data/windows.tsv"
TASKS = {
    "Azimuth": ("Azimuth-2D", "azimuth_2d_deg", -30, 30, 36),
    "Elevation": ("Elevation-3D", "elevation_deg", 0, 30, 12),
    "Distance": ("Distance-3D", "distance_m", .5, 2.5, 20),
    "Separation-2": ("Separation-2", "separation_2d_deg", 0, 60, 20),
}
MODELS = {"baseline": "ID8", "sra": "ID8-SARR"}
EPSILON = 1e-8


def main():
    manifest = pd.read_csv(MANIFEST, sep="\t").set_index("sample_id", drop=False)
    predictions_path = RESULTS / "confidence_probe_oof_predictions.csv"
    predictions = pd.read_csv(predictions_path)
    predictions = predictions[predictions.model_id.isin(MODELS.values())].copy()
    summary = pd.read_csv(RESULTS / "probe_summary.csv")
    recordings = {row["recording_id"]: row for row in
                  read_tsv(ROOT / "data/processed/MVAD/official_all/recordings.tsv")}

    # Check that the OOF predictions recover the paper's fold-weighted MAEs.
    for (model, site, task), group in predictions.groupby(["model_id", "site", "task"]):
        mean = group.groupby(["fold", "seed"]).absolute_error.mean().groupby("fold").mean().mean()
        paper = summary[(summary.model_id == model) & (summary.site == site)
                        & (summary.task == TASKS[task][0])].iloc[0]
        if not np.isclose(mean, paper["mean"], atol=1e-9, rtol=0):
            raise ValueError(f"Probe predictions differ from paper results: {model}/{site}/{task}")

    sources = {predictions_path, MANIFEST, RESULTS / "probe_summary.csv"}

    @lru_cache(None)
    def recording_tracks(recording):
        meta = recordings[recording]
        speakers = [f"speaker_{index}" for index in range(int(meta["num_speakers"]))]
        paths = {"reference": ROOT / "data/processed/MVAD/official_all/rttm",
                 **{model: ROOT / directory / f"{recording}.rttm"
                    for model, directory in PREDICTION_DIRS.items()}}
        sources.update(paths.values())
        return {model: read_rttm(path, recording, 0, float(meta["audio_duration_sec"]),
                                speakers, unmatched_prefix=None if model == "reference" else model)
                for model, path in paths.items()}

    @lru_cache(None)
    def window_errors(sample_id):
        row = manifest.loc[sample_id]
        start, duration = float(row.start_sec), float(row.duration_sec)
        tracks = {
            model: [dict(speaker=segment["speaker"],
                         start=round(max(start, segment["start"])-start, 6),
                         end=round(min(start+duration, segment["end"])-start, 6))
                    for segment in segments
                    if segment["start"] < start+duration and segment["end"] > start]
            for model, segments in recording_tracks(row.recording_id).items()
        }
        return {model: clip_errors(tracks["reference"], tracks[model], duration)
                for model in MODELS}

    random_mae = {}
    for task, (_, label, low, high, bins) in TASKS.items():
        centers = np.linspace(low, high, bins+1)
        centers = (centers[1:]+centers[:-1])/2
        labels = manifest[label].dropna().to_numpy()
        random_mae[task] = float(np.abs(labels[:, None]-centers).mean())

    rows = []
    for (sample_id, task), group in predictions.groupby(["sample_id", "task"]):
        meta = manifest.loc[sample_id]
        if set(group.seed) != {17, 3407, 2026} or len(group) != 18:
            raise ValueError(f"Incomplete probe predictions: {sample_id}/{task}")
        if not group.fold.eq(meta.fold).all() or not group.recording_id.eq(meta.recording_id).all():
            raise ValueError(f"Misaligned probe metadata: {sample_id}/{task}")
        errors = window_errors(sample_id)
        row = dict(sample_id=sample_id, recording=meta.recording_id,
                   start=float(meta.start_sec), end=float(meta.start_sec+meta.duration_sec),
                   task=task, label=float(group.label.iloc[0]), fold=int(meta.fold),
                   world_positions=int(meta.world_position_present))
        for short, model in MODELS.items():
            for site in ("S", "A", "F"):
                part = group[(group.model_id == model) & (group.site == site)]
                mae = float(part.absolute_error.mean())
                row[f"{short}_{site}_mae"] = mae
                row[f"{short}_{site}_score"] = 1-mae/random_mae[task]
            metrics = errors[short]
            row[f"{short}_der"] = metrics["der_percent"]
            for component in ("miss", "false_alarm", "confusion"):
                row[f"{short}_{component}"] = 100*metrics[component]/metrics["reference"]
        paired = group[group.site == "F"].pivot(index="seed", columns="model_id", values="absolute_error")
        gains = paired[MODELS["baseline"]]-paired[MODELS["sra"]]
        row["probe_gain"] = row["baseline_F_mae"]-row["sra_F_mae"]
        row["der_gain"] = row["baseline_der"]-row["sra_der"]
        row["improved_probe_seeds"] = int((gains > EPSILON).sum())
        row["minimum_seed_probe_gain"] = float(gains.min())
        rows.append(row)

    data = pd.DataFrame(rows)
    destination = SITE / "scripts/probe_example_audit"
    destination.mkdir(exist_ok=True)
    data.to_csv(destination / "all_candidates.csv", index=False)
    overlap = data[data.task.eq("Separation-2")]
    illustrative = overlap[(overlap.probe_gain > 1) & (overlap.der_gain > 1)
                           & (overlap.improved_probe_seeds == 3)]
    illustrative.sort_values(["der_gain", "probe_gain"], ascending=False).to_csv(
        destination / "seed_consistent_ov2_candidates.csv", index=False)
    associations = pd.read_csv(RESULTS / "probe_der_associations.csv")
    association = associations[associations.predictor.eq("SARR probe-error improvement")].iloc[0]
    report = dict(
        protocol="No new inference or probe fitting. Recording-disjoint OOF probe predictions; same 2-s intervals re-scored against original oracle-stitch RTTMs; no per-clip relabeling; all three probe seeds retained.",
        paper_mae_check="OOF predictions recover every S/A/F MAE for both models and all four paper attributes, using the paper's equal-fold weighting.",
        probe_score="For optional per-window scores, 1 - three-seed mean absolute error / expected uniform-bin error on the complete attribute manifest. Physical MAE is primary; this is not a calibrated sample reliability score.",
        exploratory_selection="OV2 candidates with >1 degree mean F-probe error reduction and >1 percentage point DER reduction, with strictly lower error in all three paired probe seeds. These are selected success cases, not representative frequencies or independent significance tests.",
        ov2_windows=len(overlap), ov2_recordings=int(overlap.recording.nunique()),
        ov2_both_improve=int(((overlap.probe_gain > EPSILON) & (overlap.der_gain > EPSILON)).sum()),
        ov2_probe_improves_der_worsens=int(((overlap.probe_gain > EPSILON) & (overlap.der_gain < -EPSILON)).sum()),
        ov2_der_improves_probe_does_not=int(((overlap.der_gain > EPSILON) & (overlap.probe_gain <= EPSILON)).sum()),
        seed_consistent_candidates=len(illustrative),
        previous_within_recording_correlation={
            "rho": float(association.within_recording_rho),
            "ci95_low": float(association.within_ci95_low),
            "ci95_high": float(association.within_ci95_high),
            "source": "exp17_final_prob/results/probe_der_associations.csv",
            "note": "Previously computed recording-cluster bootstrap, not recomputed by this script.",
        },
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(sources)},
    )
    (destination / "audit.json").write_text(json.dumps(report, indent=2)+"\n")
    chosen = ["mvad_Two5__036.000", "mvad_Three3__024.500", "mvad_Three2__019.500"]
    explanation = {
        chosen[0]: "Miss decreases 88.00% -> 0.00%; both reference speakers are recovered.",
        chosen[1]: "Miss decreases 9.50% -> 0.00%; a 0.38-s gap in the second speaker is recovered.",
        chosen[2]: "Confusion decreases 25.00% -> 2.50%, while Miss increases 25.00% -> 33.00%; this is a net improvement with a tradeoff.",
    }
    lines = ["# Probe-linked qualitative examples", "",
             "These are deliberately selected joint improvements, not evidence of a general or causal sample-level relation. The demo displays the three OV2 cases and the Two1 Single case below. Two12, One6 and the counterexample are retained in the data and audit but excluded from the page.", "",
             "Existing 2-s out-of-fold probe predictions reproduce the paper's aggregate MAEs. All values below average the three probe seeds; no best seed is selected. Every OV2 case in this table improves Separation-2 at F in all three seeds.", "",
             "| Recording | Interval (s) | Label (deg) | F-probe MAE, baseline -> SRA (deg) | Local DER, baseline -> SRA (%) |",
             "|---|---:|---:|---:|---:|"]
    for sample_id in chosen:
        row = overlap[overlap.sample_id.eq(sample_id)].iloc[0]
        lines.append(f"| {row.recording} | {row.start:g}-{row.end:g} | {row.label:.2f} | {row.baseline_F_mae:.2f} -> {row.sra_F_mae:.2f} | {row.baseline_der:.2f} -> {row.sra_der:.2f} |")
    lines += ["", *[f"- {key}: {value}" for key, value in explanation.items()], "",
              "The label is the existing Separation-2 target (camera-projected angular separation). It should not be replaced by the world-coordinate azimuth separation displayed by the top-view map; those definitions can differ.", "",
              "## Additional Single cases", "",
              "Two1 (9.5-11.5 s) has one active reference speaker. Azimuth F MAE changes 15.04 -> 4.06 degrees, Elevation 6.75 -> 3.92 degrees, and Distance 0.710 -> 0.410 m. DER changes 30.00 -> 0.00%, removing 0.600 speaker-seconds of false alarm. Each probe improves in two seeds; the third is worse for Azimuth/Distance and tied for Elevation. In the fixed 3.5-19.5 s context, DER is 20.29 -> 15.20%.", "",
              "Two12 (27.5-29.5 s) improves Azimuth F MAE from 31.66 to 6.66 degrees in all three seeds, and DER from 14.79 to 11.75%. Its frame-sampled probe cohort is Single, but exact RTTM scoring includes 0.010658 s of overlap; all frames are retained. Its fixed 21.5-37.5 s context improves DER from 6.83 to 5.89%; reference positions are image-only. It was removed from the page because the diarization improvement is visually modest, and remains in the packaged data and audit.", "",
              "One6 (16.5-18.5 s) has one active reference speaker. Azimuth F MAE changes 8.76 -> 2.09 degrees, improving in all three seeds. DER changes 13.95 -> 0.00%, removing 0.279 speaker-seconds of miss. The fixed 10.5-26.5 s context instead worsens from 14.74 to 17.57%; only the highlighted window is a joint improvement. It was removed from the page because full-context DER worsens; both scores remain in the packaged data and audit.", "",
              "Probe extraction uses isolated 2-s inputs, whereas the existing diarization predictions use longer inference windows and reconstruction. Matching timestamps does not make these the same forward pass.", "",
              "## Population context", "",
              f"Across all {len(overlap)} overlapping 2-s OV2 windows, {report['ov2_both_improve']} improve on both axes and {report['ov2_probe_improves_der_worsens']} improve probe error while DER worsens. These windows overlap in time, so their counts are not independent trial counts.",
              f"The prior within-recording association is rho={association.within_recording_rho:.3f}, 95% recording-cluster CI [{association.within_ci95_low:.3f}, {association.within_ci95_high:.3f}]. It does not establish a general positive association.", "",
              "For a demo, retain a longer audio context with the 2-s evaluation interval explicitly marked. Show its reference label, all three seed predictions or their MAE, and time-aligned diarization errors. Do not label the longer-context DER as the 2-s probe-window DER. Retain counterexamples in the audit.", "",
              "Reproduce: `.conda/spatialrole/bin/python sra-diarization.github.io/scripts/audit_probe_examples.py`", ""]
    (destination / "RECOMMENDATIONS.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
