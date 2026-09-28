#!/usr/bin/env python3
"""Package real MVAD excerpts, oracle-stitch RTTMs, and reference positions.

Requires numpy, scipy, and soundfile. No inference or model checkpoints needed.
"""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.io import loadmat


SITE = Path(__file__).resolve().parents[1]
COLORS = ["#1565c0", "#d55e00", "#27804a"]
# Verified against the original Kinect videos for the image-only examples.
IMAGE_GEOMETRY = dict(width=640, height=480)
PREDICTION_DIRS = {
    "baseline": (
        "src/baselines/exp_papercheck_3ds_4mic_maxspacing_20260627/"
        "id8_diarizen_spatial_diarization_joint_3ds.slurm/"
        "oracle_stitch/metric_Loss_best/avg_ckpt5/test/MVAD"
    ),
    "sra": (
        "exp09_SARR/exp/id8_sarr_lam005_3ds.slurm/"
        "oracle_stitch/metric_Loss_best/avg_ckpt5/test/MVAD"
    ),
}
PROBE_TARGETS = {
    "Azimuth": ("azimuth_2d_deg", "deg", 2, 1,
                "Mean camera-projected horizontal angle of the active speaker."),
    "Elevation": ("elevation_deg", "deg", 2, 1,
                  "Mean world-coordinate elevation of the active speaker relative to the array."),
    "Distance": ("distance_m", "m", 3, 1,
                 "Mean distance of the active speaker from the microphone-array center."),
    "Separation-2": ("separation_2d_deg", "deg", 2, 2,
                     "Mean camera-projected angular separation, not world-coordinate azimuth separation."),
}


def read_tsv(path):
    with path.open(newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def read_rttm(path, recording, start, end, speakers, unmatched_prefix=None):
    segments = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if not fields or fields[0] != "SPEAKER" or fields[1] != recording:
            continue
        left = max(start, float(fields[3]))
        right = min(end, float(fields[3]) + float(fields[4]))
        if right <= left:
            continue
        speaker = fields[7]
        if speaker not in speakers:
            if unmatched_prefix is None:
                raise ValueError(f"Unexpected speaker {speaker} in {path}")
            speaker = f"unmatched_{unmatched_prefix}_{speaker}"
        segments.append(dict(speaker=speaker, start=round(left-start, 6),
                             end=round(right-start, 6)))
    return sorted(segments, key=lambda segment: (segment["start"], segment["speaker"]))


def speaker_set_errors(reference, hypothesis):
    return dict(
        miss=max(0, len(reference)-len(hypothesis)),
        false_alarm=max(0, len(hypothesis)-len(reference)),
        confusion=min(len(reference), len(hypothesis))-len(reference & hypothesis),
    )


def clip_errors(reference, hypothesis, duration):
    """Exact interval integration with existing oracle-aligned speaker labels."""
    bounds = sorted({0, duration} | {s[key] for s in reference + hypothesis
                                   for key in ("start", "end")})
    result = dict(reference=0.0, miss=0.0, false_alarm=0.0, confusion=0.0)
    for left, right in zip(bounds, bounds[1:]):
        middle = (left + right) / 2
        refs = {s["speaker"] for s in reference if s["start"] <= middle < s["end"]}
        hyps = {s["speaker"] for s in hypothesis if s["start"] <= middle < s["end"]}
        dt = right-left
        result["reference"] += len(refs)*dt
        for key, value in speaker_set_errors(refs, hyps).items():
            result[key] += value*dt
    if result["reference"] <= 0:
        raise ValueError("Clip DER requires positive reference speaker time")
    result["der_percent"] = 100 * sum(result[k] for k in ("miss", "false_alarm", "confusion")) / result["reference"]
    return {key: round(value, 6) for key, value in result.items()}


def paired_error_intervals(tracks, duration):
    bounds = sorted({0, duration} | {segment[key] for segments in tracks.values()
                    for segment in segments for key in ("start", "end")})
    intervals = []
    for left, right in zip(bounds, bounds[1:]):
        middle = (left+right)/2
        active = {key: {segment["speaker"] for segment in segments
                       if segment["start"] <= middle < segment["end"]}
                  for key, segments in tracks.items()}
        errors = {key: speaker_set_errors(active["reference"], active[key])
                  for key in PREDICTION_DIRS}
        gain = sum(errors["baseline"].values())-sum(errors["sra"].values())
        intervals.append(dict(start=left, end=right, referenceCount=len(active["reference"]),
                              baseline=errors["baseline"], sra=errors["sra"], gain=gain))
    return intervals


def reference_activity(reference, duration):
    """Seconds with exactly 0, 1, 2, or 3 active reference speakers."""
    bounds = sorted({0, duration} | {s[key] for s in reference for key in ("start", "end")})
    seconds = [0.0] * 4
    for left, right in zip(bounds, bounds[1:]):
        middle = (left + right) / 2
        count = len({s["speaker"] for s in reference if s["start"] <= middle < s["end"]})
        seconds[count] += right-left
    return [round(value, 6) for value in seconds]


def probe_focus(root, chosen, sources, speakers):
    sample_id = chosen.get("probe_sample_id")
    if sample_id is None:
        return None, set()
    prediction_path = root / "exp17_final_prob/results/confidence_probe_oof_predictions.csv"
    manifest_path = root / "exp03_prob_MVAD/data/windows.tsv"
    meta = next(row for row in read_tsv(manifest_path) if row["sample_id"] == sample_id)
    start, end = chosen["focus_start"], chosen["focus_end"]
    if (meta["recording_id"] != chosen["recording"] or float(meta["start_sec"]) != start
            or float(meta["duration_sec"]) != end-start or end-start != 2):
        raise ValueError(f"Misaligned probe window: {sample_id}")
    with prediction_path.open(newline="") as source:
        rows = [row for row in csv.DictReader(source)
                if row["sample_id"] == sample_id]
    seeds = [17, 3407, 2026]
    probes = []
    counts = set()
    for task in chosen["probe_tasks"]:
        label_key, unit, decimals, count, definition = PROBE_TARGETS[task]
        counts.add(count)
        label = float(meta[label_key])
        if not np.isfinite(label):
            raise ValueError(f"Missing target: {sample_id}/{task}")
        predictions, errors = {}, {}
        for key, model in (("baseline", "ID8"), ("sra", "ID8-SARR")):
            predictions[key], errors[key] = {}, {}
            for site in ("S", "A", "F"):
                selected = [row for row in rows if row["model_id"] == model
                            and row["site"] == site and row["task"] == task]
                if len(selected) != 3 or {int(row["seed"]) for row in selected} != set(seeds):
                    raise ValueError(f"Incomplete seed predictions: {sample_id}/{task}/{model}/{site}")
                if any(abs(float(row["label"])-label) > 1e-8 or int(row["fold"]) != int(meta["fold"])
                       for row in selected):
                    raise ValueError(f"Label/fold mismatch: {sample_id}/{task}/{model}/{site}")
                selected.sort(key=lambda row: seeds.index(int(row["seed"])))
                predictions[key][site] = [dict(seed=int(row["seed"]), prediction=float(row["prediction"]),
                                              error=float(row["absolute_error"])) for row in selected]
                errors[key][site] = float(np.mean([row["error"] for row in predictions[key][site]]))
        improved = sum(sra["error"] < base["error"] - 1e-8
                       for base, sra in zip(predictions["baseline"]["F"], predictions["sra"]["F"]))
        if (improved < chosen["minimum_improved_seeds"]
                or errors["sra"]["F"] >= errors["baseline"]["F"]):
            raise ValueError(f"Probe outcome changed after selection: {sample_id}/{task}")
        probes.append(dict(task=task, target=label, unit=unit, decimals=decimals,
                           targetDefinition=definition, predictions=predictions,
                           errors=errors, improvedSeeds=improved))
    if len(counts) != 1:
        raise ValueError(f"Incompatible probe cohorts: {sample_id}")
    count = counts.pop()
    if float(meta["count_label"]) != count:
        raise ValueError(f"Manifest cohort differs from probe target: {sample_id}")
    tracks = {key: read_rttm(path, chosen["recording"], start, end, speakers,
                             unmatched_prefix=None if key == "reference" else key)
              for key, path in sources.items()}
    stable_activity = [0] * 4
    stable_activity[count] = end-start
    activity = reference_activity(tracks["reference"], end-start)
    expected_activity = chosen.get("expected_focus_activity") or stable_activity
    if not np.allclose(activity, expected_activity, atol=1e-6, rtol=0):
        raise ValueError(f"Unexpected reference activity: {sample_id}: {activity}")
    diarization = {key: clip_errors(tracks["reference"], tracks[key], end-start)
                   for key in PREDICTION_DIRS}
    return dict(sampleId=sample_id, sourceStart=start, sourceEnd=end,
                start=start-chosen["start"], end=end-chosen["start"],
                referenceCount=count if activity == stable_activity else None,
                probeReferenceCount=count, referenceActivitySeconds=activity,
                seeds=seeds, probes=probes,
                diarizationErrors=diarization), {prediction_path, manifest_path}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=SITE.parent)
    args = parser.parse_args()
    root = args.project_root.resolve()
    selection_path = SITE / "scripts/example_selection.json"
    selection = json.loads(selection_path.read_text())
    processed = root / "data/processed/MVAD/official_all"
    recordings = {r["recording_id"]: r for r in read_tsv(processed / "recordings.tsv")}
    all_frames = defaultdict(list)
    for row in read_tsv(processed / "spatial_frames.tsv"):
        all_frames[row["recording_id"]].append(row)
    output = SITE / "assets/audio"
    output.mkdir(parents=True, exist_ok=True)
    examples = []
    inputs = {processed / name for name in ("recordings.tsv", "spatial_frames.tsv", "rttm")}

    for chosen in selection["examples"]:
        recording = chosen["recording"]
        name = recording.removeprefix("mvad_")
        start, end, category = chosen["start"], chosen["end"], chosen["category"]
        meta = recordings[recording]
        source_audio = root / "data/raw/MVAD/official/audio" / (name + ".wav")
        setup_path = root / "data/raw/MVAD/official/setup" / (name + ".mat")
        inputs.update((source_audio, setup_path))
        position_space = "world" if meta["world_position_present"] == "1" else "image"
        if position_space == "image" and meta["image_position_present"] != "1":
            raise ValueError(f"No position annotations for {recording}")
        duration = end-start
        speakers = [dict(id=f"speaker_{i}", label=f"Speaker {i+1}",
                         short=f"P{i+1}", color=COLORS[i])
                    for i in range(int(meta["num_speakers"]))]
        ids = [s["id"] for s in speakers]
        sources = {"reference": processed / "rttm", **{
            model: root / directory / (recording + ".rttm")
            for model, directory in PREDICTION_DIRS.items()
        }}
        inputs.update(sources.values())
        rate = int(meta["sample_rate"])
        source_start_sample = round(start * rate)
        if start < 0 or end > float(meta["audio_duration_sec"]) or duration <= 0:
            raise ValueError(f"Invalid excerpt interval: {recording}")
        tracks = {model: read_rttm(path, recording, start, end, ids,
                                 unmatched_prefix=None if model == "reference" else model)
                  for model, path in sources.items()}
        focus, focus_inputs = probe_focus(root, chosen, sources, ids)
        inputs.update(focus_inputs)
        errors = {model: clip_errors(tracks["reference"], tracks[model], duration)
                  for model in PREDICTION_DIRS}
        for model in PREDICTION_DIRS:
            if abs(errors[model]["der_percent"]-chosen[f"{model}_der"]) > 1e-5:
                raise ValueError(f"Predictions changed after selection: {recording}/{model}")
        unmatched_ids = sorted({segment["speaker"] for segments in tracks.values()
                                for segment in segments if segment["speaker"] not in ids})
        unmatched = [dict(id=speaker, short=f"U{i+1}", label=f"Unmatched stream {i+1}", color="#757575")
                     for i, speaker in enumerate(unmatched_ids)]

        activity_seconds = reference_activity(tracks["reference"], duration)
        if category == "single" and sum(activity_seconds[2:]) > 1e-6:
            raise ValueError(f"Overlapping reference speech in single excerpt: {recording}")

        # Listen to the actual reference microphone, using one fixed gain per clip.
        # Sample rate and crop boundaries preserve the original annotation clock.
        with sf.SoundFile(source_audio) as source:
            if source.samplerate != rate:
                raise ValueError(f"Sample rate mismatch: {recording}")
            source.seek(source_start_sample)
            audio = source.read(round(duration*rate), dtype="float64", always_2d=True)[:, 0]
        if len(audio) != duration*rate or not np.isfinite(audio).all():
            raise ValueError(f"Invalid audio crop: {recording}")
        peak = float(np.max(np.abs(audio)))
        gain = 0.9/peak if peak > 0 else 1.0
        audio_name = f"{name.lower()}-{start}-{end}.wav"
        sf.write(output / audio_name, audio*gain, rate, subtype="PCM_16")

        setup = loadmat(setup_path, simplify_cells=True)
        intrinsic = np.asarray(setup["cameraIntrinsicParameters"], dtype=float)
        microphones = np.asarray(setup["micsPositions"], dtype=float).T
        if microphones.shape != (8, 3):
            raise ValueError(f"Unexpected array geometry: {recording}")
        center = microphones.mean(axis=0)
        mic_points = [dict(channel=i, x=round(float(v[0]), 6),
                           y=round(float(v[1]), 6), z=round(float(v[2]), 6),
                           selected=i in (0, 2, 4, 6))
                      for i, v in enumerate(microphones-center)]
        by_frame = defaultdict(list)
        for row in all_frames[recording]:
            time = float(row["start_sec"])
            stop = time + float(row["duration_sec"])
            if time < end and stop > start:
                by_frame[int(row["frame_index"])].append(row)
        frames = []
        missing = 0
        for frame_id in sorted(by_frame):
            rows = by_frame[frame_id]
            time = float(rows[0]["start_sec"])
            stop = time + float(rows[0]["duration_sec"])
            by_speaker = {r["speaker_id"]: r for r in rows}
            points = []
            for speaker in ids:
                r = by_speaker[speaker]
                if position_space == "world":
                    xyz = np.array([float(r[k]) for k in ("world_x", "world_y", "world_z")]) - center
                    distance = float(np.linalg.norm(xyz))
                    azimuth = float(np.degrees(np.arctan2(xyz[0], xyz[1])))
                    elevation = float(np.degrees(np.arctan2(xyz[2], np.linalg.norm(xyz[:2]))))
                    valid = (int(r["world_gt_status"]) > 0 and np.isfinite(xyz).all()
                             and .5 <= distance <= 2.5 and abs(azimuth) <= 60 and abs(elevation) <= 60)
                    point = dict(x=round(float(xyz[0]), 5), y=round(float(xyz[1]), 5),
                                 z=round(float(xyz[2]), 5)) if valid else None
                else:
                    x, y = float(r["image_x"]), float(r["image_y"])
                    valid = (int(r["image_gt_status"]) > 0 and np.isfinite([x, y]).all()
                             and 0 <= x < IMAGE_GEOMETRY["width"]
                             and 0 <= y < IMAGE_GEOMETRY["height"])
                    # Camera-projected horizontal angle; no depth or acoustic DoA inferred.
                    azimuth = float(np.degrees(np.arctan2(x-intrinsic[0, 2], intrinsic[0, 0])))
                    point = dict(x=x, y=y, azimuth=round(azimuth, 6)) if valid else None
                points.append(point)
                missing += point is None
            frames.append(dict(start=round(max(0, time-start), 6),
                               end=round(min(duration, stop-start), 6), points=points))
        if not frames or frames[0]["start"] != 0 or frames[-1]["end"] != duration:
            raise ValueError(f"Position timing does not cover {recording}")
        clip_id = f"{name.lower()}-{start:g}-{end:g}".replace(".", "p")
        examples.append(dict(id=clip_id, recording=recording,
                             category=category, title=chosen["title"], outcome=chosen["outcome"],
                             gainPp=chosen["gain_pp"], positionSpace=position_space,
                             start=round(start, 9), sourceStartSample=source_start_sample, duration=duration,
                             audio=f"assets/audio/{audio_name}", sampleRate=rate,
                             playbackGain=round(gain, 6), speakers=speakers, tracks=tracks,
                             unmatchedSpeakers=unmatched, errorIntervals=paired_error_intervals(tracks, duration),
                             frameHopSamples=int(meta["frame_hop_samples"]),
                             microphones=mic_points, frames=frames,
                             missingPositions=missing, clipErrors=errors, focus=focus,
                             activitySeconds=activity_seconds,
                             sources={k: str(v.relative_to(root)) for k, v in sources.items()}))
        print(f"{name} {start:.6f}–{end:.6f}s: {position_space}, {len(frames)} frames, {missing} missing positions; "
              f"clip DER S-DiariZen / + SRA: {errors['baseline']['der_percent']:.2f} / "
              f"{errors['sra']['der_percent']:.2f}%")

    if selection["protocol"].get("mode") == "scene-median" and not any(example["activitySeconds"][3] >= 5 for example in examples):
        raise ValueError("Include at least five seconds of true three-speaker overlap")

    data = dict(
        examples=examples,
        geometry=dict(xMin=-.8, xMax=.8, yMin=-.15, yMax=2.1),
        imageGeometry=IMAGE_GEOMETRY,
        protocol=dict(
            audio="Original channel 0; original sample rate; fixed peak normalization to 0.9; PCM16 WAV.",
            timing="Original annotation timestamps and per-recording frameHopSamples; no video-FPS approximation.",
            predictions="Existing oracle-stitch RTTM predictions; labels already aligned to the reference. No per-clip relabeling.",
            modelInputs=dict(baseline=[0, 2, 4, 6], sra=[0, 2, 4, 6]),
            positions="Reference world coordinates relative to the mean of all eight microphones, or original image pixels when world labels are absent. Image azimuths use the camera intrinsics and do not supply acoustic DoA or depth. Positions are held per annotated frame, not predicted or interpolated.",
            missing="Invalid or absent coordinates in the selected space are null; never replaced with invented positions.",
            selection=selection["protocol"],
            scoring="Exact interval integration, zero collar, includes silence and overlap; oracle-aligned speaker labels. Unmatched predicted streams are retained. Component percentages use reference speaker-seconds as denominator.",
            errorChange="Per-interval baseline error count minus SRA error count; positive means fewer errors with SRA. Equal counts may have different error types. Not a per-frame DER.",
        ),
        selectionSha256=hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        sourceHashes={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(inputs)},
    )
    encoded = json.dumps(data, separators=(",", ":"), allow_nan=False)
    (SITE / "assets/audio-examples.json").write_text(encoded + "\n")
    (SITE / "assets/audio-examples.js").write_text("window.AUDIO_EXAMPLES = " + encoded + ";\n")


if __name__ == "__main__":
    main()
