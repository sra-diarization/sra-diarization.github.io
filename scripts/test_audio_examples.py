"""Checks for qualitative selection, error integration, and packaged media."""

import hashlib
import json
import tempfile
import unittest
import wave
from pathlib import Path

from build_audio_examples import SITE, clip_errors, read_rttm, reference_activity, speaker_set_errors
from select_audio_examples import PROBE_CASES, outcome


class AudioExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((SITE / "assets/audio-examples.json").read_text())
        cls.examples = cls.data["examples"]

    def test_selection_and_script_payload(self):
        selection_path = SITE / "scripts/example_selection.json"
        self.assertEqual(self.data["selectionSha256"], hashlib.sha256(selection_path.read_bytes()).hexdigest())
        selection = json.loads(selection_path.read_text())
        count = len(PROBE_CASES) if selection["protocol"]["mode"] == "probe-linked" else 6
        self.assertEqual(len(self.examples), count)
        self.assertEqual(len({clip["recording"] for clip in self.examples}), count)
        self.assertTrue({"lower", "higher"} <= {clip["outcome"] for clip in self.examples})
        script = (SITE / "assets/audio-examples.js").read_text()
        payload = json.loads(script.removeprefix("window.AUDIO_EXAMPLES = ").strip().removesuffix(";"))
        self.assertEqual(payload, self.data)
        for clip, chosen in zip(self.examples, selection["examples"]):
            self.assertEqual(clip["recording"], chosen["recording"])
            self.assertEqual(clip["duration"], 16)
            self.assertEqual(clip["outcome"], outcome(clip["gainPp"]))
            self.assertAlmostEqual(clip["gainPp"], clip["clipErrors"]["baseline"]["der_percent"] - clip["clipErrors"]["sra"]["der_percent"])

    def test_audio_and_position_timing(self):
        for clip in self.examples:
            with self.subTest(clip=clip["id"]):
                with wave.open(str(SITE / clip["audio"]), "rb") as audio:
                    self.assertEqual(audio.getnchannels(), 1)
                    self.assertEqual(audio.getsampwidth(), 2)
                    self.assertEqual(audio.getframerate(), clip["sampleRate"])
                    self.assertEqual(audio.getnframes(), clip["duration"] * clip["sampleRate"])
                self.assertEqual(clip["frames"][0]["start"], 0)
                self.assertEqual(clip["frames"][-1]["end"], clip["duration"])
                for left, right in zip(clip["frames"], clip["frames"][1:]):
                    self.assertAlmostEqual(left["end"], right["start"], places=5)
                for frame in clip["frames"]:
                    self.assertEqual(len(frame["points"]), len(clip["speakers"]))
                self.assertAlmostEqual(sum(clip["activitySeconds"]), clip["duration"], places=5)

    def test_error_band_matches_clip_metrics(self):
        for clip in self.examples:
            intervals = clip["errorIntervals"]
            self.assertEqual(intervals[0]["start"], 0)
            self.assertEqual(intervals[-1]["end"], clip["duration"])
            for left, right in zip(intervals, intervals[1:]):
                self.assertEqual(left["end"], right["start"])
            for model in ("baseline", "sra"):
                expected = clip["clipErrors"][model]
                self.assertEqual(clip_errors(clip["tracks"]["reference"], clip["tracks"][model], clip["duration"]), expected)
                for component in ("miss", "false_alarm", "confusion"):
                    total = sum((part["end"]-part["start"]) * part[model][component] for part in intervals)
                    self.assertAlmostEqual(total, expected[component], places=5)
                reference = sum((part["end"]-part["start"]) * part["referenceCount"] for part in intervals)
                self.assertAlmostEqual(reference, expected["reference"], places=5)
            for part in intervals:
                self.assertGreater(part["end"], part["start"])
                self.assertEqual(part["gain"], sum(part["baseline"].values()) - sum(part["sra"].values()))

    def test_unmatched_tracks_and_silence_are_not_discarded(self):
        self.assertEqual(speaker_set_errors({"a"}, {"a", "extra"}), dict(miss=0, false_alarm=1, confusion=0))
        self.assertEqual(speaker_set_errors({"a"}, {"extra"}), dict(miss=0, false_alarm=0, confusion=1))
        self.assertEqual(speaker_set_errors(set(), {"extra"}), dict(miss=0, false_alarm=1, confusion=0))
        self.assertEqual(speaker_set_errors({"a", "b"}, {"a"}), dict(miss=1, false_alarm=0, confusion=0))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prediction.rttm"
            path.write_text("SPEAKER demo 1 0.0 1.0 <NA> <NA> extra <NA> <NA>\n")
            segment = read_rttm(path, "demo", 0, 2, ["a"], unmatched_prefix="baseline")[0]
            self.assertEqual(segment["speaker"], "unmatched_baseline_extra")
            with self.assertRaises(ValueError):
                read_rttm(path, "demo", 0, 2, ["a"])

    def test_silence_false_alarms_use_reference_speaker_time(self):
        reference = [dict(speaker="a", start=1, end=2)]
        hypothesis = [dict(speaker="a", start=0, end=2)]
        errors = clip_errors(reference, hypothesis, 2)
        self.assertEqual(errors["false_alarm"], 1)
        self.assertEqual(errors["reference"], 1)
        self.assertEqual(errors["der_percent"], 100)

    def test_scene_coverage(self):
        if self.examples[0].get("focus"):
            self.assertEqual([clip["recording"] for clip in self.examples],
                             ["mvad_Two5", "mvad_Three3", "mvad_Three2",
                              "mvad_Two1", "mvad_Two12", "mvad_One6", "mvad_Two4"])
            return
        scenes = {clip["category"]: clip for clip in self.examples}
        for category in ("overlap-lower", "overlap-similar", "overlap-higher"):
            self.assertGreaterEqual(scenes[category]["activitySeconds"][2], 4)
        self.assertGreaterEqual(scenes["overlap-three"]["activitySeconds"][3], 5)
        self.assertEqual(sum(scenes["single"]["activitySeconds"][2:]), 0)

    def test_focus_probe_and_der_use_the_same_window(self):
        for clip in self.examples:
            focus = clip.get("focus")
            if focus is None:
                continue
            self.assertEqual(focus["end"]-focus["start"], 2)
            self.assertEqual(clip["start"]+focus["start"], focus["sourceStart"])
            self.assertEqual(clip["start"]+focus["end"], focus["sourceEnd"])
            self.assertGreaterEqual(focus["start"], 0)
            self.assertLessEqual(focus["end"], clip["duration"])
            cropped = {key: [dict(speaker=segment["speaker"],
                                  start=max(focus["start"], segment["start"])-focus["start"],
                                  end=min(focus["end"], segment["end"])-focus["start"])
                            for segment in segments
                            if segment["start"] < focus["end"] and segment["end"] > focus["start"]]
                       for key, segments in clip["tracks"].items()}
            for model in ("baseline", "sra"):
                expected = clip_errors(cropped["reference"], cropped[model], 2)
                self.assertEqual(expected, focus["diarizationErrors"][model])
                self.assertAlmostEqual(expected["reference"], sum(
                    count * duration for count, duration in enumerate(focus["referenceActivitySeconds"])), places=6)
                for probe in focus["probes"]:
                    for site in ("S", "A", "F"):
                        predictions = probe["predictions"][model][site]
                        self.assertEqual([row["seed"] for row in predictions], [17, 3407, 2026])
                        errors = [abs(row["prediction"]-probe["target"]) for row in predictions]
                        self.assertAlmostEqual(sum(errors)/3, probe["errors"][model][site])
                        for row, error in zip(predictions, errors):
                            self.assertAlmostEqual(row["error"], error)
            activity = reference_activity(cropped["reference"], 2)
            self.assertEqual(activity, focus["referenceActivitySeconds"])
            if focus["referenceCount"] is not None:
                self.assertEqual(activity[focus["referenceCount"]], 2)
            else:
                self.assertEqual(clip["recording"], "mvad_Two12")
                self.assertGreater(activity[2], 0)
            for probe in focus["probes"]:
                improved = sum(sra["error"] < base["error"] - 1e-8
                               for base, sra in zip(probe["predictions"]["baseline"]["F"],
                                                    probe["predictions"]["sra"]["F"]))
                self.assertEqual(improved, probe["improvedSeeds"])
                self.assertEqual(improved, 2 if clip["recording"] == "mvad_Two1" else 3)
                self.assertLess(probe["errors"]["sra"]["F"], probe["errors"]["baseline"]["F"])
            gain = focus["diarizationErrors"]["baseline"]["der_percent"]-focus["diarizationErrors"]["sra"]["der_percent"]
            self.assertGreater(-gain if clip["category"] == "probe-counterexample" else gain, 1)

    def test_expected_focus_results(self):
        expected = [(24.37, 5.21, 88, 0), (20.02, 9.02, 9.5, 0),
                    (28.35, 13.05, 50, 35.5), (15.04, 4.06, 30, 0),
                    (31.66, 6.66, 14.79, 11.75),
                    (8.76, 2.09, 13.95, 0), (23.98, 8.02, 0, 8.65)]
        if not self.examples[0].get("focus"):
            self.skipTest("Legacy scene-median selection")
        for clip, values in zip(self.examples, expected):
            focus = clip["focus"]
            probe = focus["probes"][0]
            actual = [probe["errors"]["baseline"]["F"], probe["errors"]["sra"]["F"],
                      focus["diarizationErrors"]["baseline"]["der_percent"], focus["diarizationErrors"]["sra"]["der_percent"]]
            self.assertEqual(tuple(round(value, 2) for value in actual), values)

    def test_single_windows_keep_all_attributes_and_context_outcomes(self):
        if not self.examples[0].get("focus"):
            self.skipTest("Legacy scene-median selection")
        clips = {clip["recording"]: clip for clip in self.examples}
        two1 = clips["mvad_Two1"]
        one6 = clips["mvad_One6"]
        self.assertEqual((two1["start"], one6["start"]), (3.5, 10.5))
        self.assertEqual(two1["id"], "two1-3p5-19p5")
        self.assertEqual(one6["id"], "one6-10p5-26p5")
        probes = two1["focus"]["probes"]
        self.assertEqual([probe["task"] for probe in probes], ["Azimuth", "Elevation", "Distance"])
        self.assertEqual([round(probe["errors"]["baseline"]["F"], probe["decimals"])
                          for probe in probes], [15.04, 6.75, .710])
        self.assertEqual([round(probe["errors"]["sra"]["F"], probe["decimals"])
                          for probe in probes], [4.06, 3.92, .410])
        self.assertEqual(probes[-1]["unit"], "m")
        self.assertLess(two1["clipErrors"]["sra"]["der_percent"], two1["clipErrors"]["baseline"]["der_percent"])
        self.assertGreater(one6["clipErrors"]["sra"]["der_percent"], one6["clipErrors"]["baseline"]["der_percent"])
        self.assertEqual(two1["focus"]["diarizationErrors"]["baseline"]["false_alarm"], .6)
        self.assertEqual(one6["focus"]["diarizationErrors"]["baseline"]["miss"], .279)

    def test_two12_retains_exact_reference_activity_and_probe_window(self):
        if not self.examples[0].get("focus"):
            self.skipTest("Legacy scene-median selection")
        clip = next(c for c in self.examples if c["recording"] == "mvad_Two12")
        focus = clip["focus"]
        self.assertEqual(clip["id"], "two12-21p5-37p5")
        self.assertEqual((clip["start"], clip["duration"]), (21.5, 16))
        self.assertEqual((focus["sourceStart"], focus["sourceEnd"]), (27.5, 29.5))
        self.assertIsNone(focus["referenceCount"])
        self.assertEqual(focus["probeReferenceCount"], 1)
        self.assertEqual(focus["referenceActivitySeconds"], [0, 1.989342, .010658, 0])
        self.assertEqual(focus["diarizationErrors"]["baseline"]["reference"], 2.010658)
        self.assertEqual([probe["task"] for probe in focus["probes"]], ["Azimuth"])
        self.assertEqual(focus["probes"][0]["improvedSeeds"], 3)
        self.assertEqual(clip["positionSpace"], "image")
        self.assertEqual(clip["missingPositions"], 0)
        self.assertEqual([round(clip["clipErrors"][key]["der_percent"], 2)
                          for key in ("baseline", "sra")], [6.83, 5.89])


if __name__ == "__main__":
    unittest.main()
