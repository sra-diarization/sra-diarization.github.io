"""Regression checks for the paper-version probe statistics and static assets."""

import base64
import csv
import hashlib
import json
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
PROJECT = SITE.parent
TASKS = ("Azimuth-2D", "Elevation-3D", "Distance-3D", "Separation-2")


class DemoStatisticsTests(unittest.TestCase):
    def test_header_asset_matches_source_pdf(self):
        pdf = SITE / "assets/SRA_FINAL3.pdf"
        svg = (SITE / "assets/SRA_FINAL3.svg").read_text()
        self.assertIn(hashlib.sha256(pdf.read_bytes()).hexdigest(), svg)
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertTrue(list(root.iter("{http://www.w3.org/2000/svg}path")))
        self.assertIn('src="assets/SRA_FINAL3.svg"', (SITE / "index.html").read_text())

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((SITE / "assets/probe-data.json").read_text())

    def test_four_reported_attributes(self):
        self.assertEqual(tuple(task["id"] for task in self.data["tasks"]), TASKS)
        self.assertEqual(len(self.data["scores"]), 24)
        self.assertEqual(len(self.data["transfers"]), 24)
        self.assertEqual(len(self.data["comparisons"]), 12)
        self.assertEqual(self.data["protocol"]["statistics"]["family_size"], 4)

    def test_classic_script_matches_json(self):
        script = (SITE / "assets/probe-data.js").read_text()
        prefix = "window.PROBE_DATA = "
        self.assertTrue(script.startswith(prefix))
        payload = json.loads(script[len(prefix):].rstrip().removesuffix(";"))
        for key in self.data:
            if key != "diagram":
                self.assertEqual(payload[key], self.data[key])
        for key, value in self.data["diagram"].items():
            self.assertEqual(payload["diagram"][key], value)
        self.assertTrue(payload["diagram"]["image"].startswith("data:image/svg+xml;base64,"))

    def test_chart_artwork_and_anchor_locations(self):
        script = (SITE / "assets/probe-data.js").read_text()
        diagram = json.loads(script[len("window.PROBE_DATA = "):].rstrip().removesuffix(";"))["diagram"]
        self.assertEqual(diagram["source"], "assets/SRA_FINAL3.pdf")
        self.assertEqual(diagram["anchors"], {
            "S": [161.03824, 29.69497], "A": [161.03824, 74.94447],
            "F": [290.42352, 74.23745],
        })
        for key, filename in (("image", "SRA_FINAL3.svg"),
                              ("baseline_image", "SRA_FINAL3-baseline.svg")):
            svg = base64.b64decode(diagram[key].split(",", 1)[1]).decode()
            self.assertEqual(svg, (SITE / "assets" / filename).read_text())
            root = ET.fromstring(svg)
            self.assertEqual(list(map(float, root.attrib["viewBox"].split())),
                             [0, 0, diagram["width"], diagram["height"]])
            red = [element for element in root.iter()
                   if any(element.get(attr, "").lower() == "#ff3333"
                          for attr in ("fill", "stroke"))]
            self.assertEqual(bool(red), key == "image")
        for x, y in diagram["anchors"].values():
            self.assertTrue(0 < x < diagram["width"])
            self.assertTrue(0 < y < diagram["height"])

    def test_paper_q_values(self):
        expected_transfer = (0.0481, 0.0232, 0.0481, 0.0311)
        expected_comparison = (0.0719, 0.4063, 0.0222, 0.0591)
        for task, transfer_q, comparison_q in zip(TASKS, expected_transfer, expected_comparison):
            transfer = next(row for row in self.data["transfers"]
                            if row["task"] == task and row["kind"] == "within-model"
                            and row["model_id"] == "ID8" and row["source"] == "S")
            comparison = next(row for row in self.data["comparisons"]
                              if row["task"] == task and row["site"] == "F")
            self.assertEqual(f"{transfer['q_family']:.4f}", f"{transfer_q:.4f}")
            self.assertEqual(f"{comparison['q_site']:.4f}", f"{comparison_q:.4f}")

    def test_all_q_values_use_four_test_families(self):
        for name, keys, q_key in (("transfers", ("kind", "model_id", "source"), "q_family"),
                                  ("comparisons", ("site",), "q_site")):
            families = defaultdict(list)
            for row in self.data[name]:
                self.assertEqual([key for key in row if key.startswith("q_")], [q_key])
                families[tuple(row[key] for key in keys)].append(row)
            for family in families.values():
                self.assertEqual(len(family), 4)
                self.assertEqual({row["task"] for row in family}, set(TASKS))
                ranked = sorted(family, key=lambda row: row["p_two_sided"])
                running_minimum = 1.0
                for rank in range(4, 0, -1):
                    row = ranked[rank - 1]
                    running_minimum = min(running_minimum, row["p_two_sided"] * 4 / rank)
                    self.assertAlmostEqual(row[q_key], running_minimum, places=12)

    def test_statistics_match_paper_audit(self):
        directory = PROJECT / "_final_submission/probing_four_attribute_stats"
        if not directory.is_dir():
            self.skipTest("Full experimental checkout is not available")
        for name, filename, keys, q_key in (
            ("transfers", "probe_transfer_four.csv", ("kind", "model_id", "source", "task"), "q_family"),
            ("comparisons", "sra_paired_contrasts_four.csv", ("site", "task"), "q_site"),
        ):
            with (directory / filename).open(newline="") as source:
                audit = {tuple(row[key] for key in keys): row for row in csv.DictReader(source)}
            for row in self.data[name]:
                expected = audit[tuple(row[key] for key in keys)]
                self.assertEqual(row[q_key], float(expected[q_key]))
                self.assertEqual(row["p_two_sided"], float(expected["p_two_sided"]))

    def test_probe_scores_unchanged(self):
        source_path = PROJECT / "exp17_final_prob/results/probe_summary.csv"
        if not source_path.is_file():
            self.skipTest("Full experimental checkout is not available")
        keys = ("model_id", "site", "task")
        with source_path.open(newline="") as source:
            scores = {tuple(row[key] for key in keys): row for row in csv.DictReader(source)}
        for row in self.data["scores"]:
            original = scores[tuple(row[key] for key in keys)]
            for column in ("mean", "sem", "normalized_mean", "normalized_sem"):
                self.assertEqual(row[column], float(original[column]))

    def test_reference_figure_matches_paper(self):
        paper = PROJECT / "_final_submission/figures/id8_spatial_dilution.png"
        if not paper.is_file():
            self.skipTest("Full experimental checkout is not available")
        self.assertEqual((SITE / "assets/id8_spatial_dilution.png").read_bytes(), paper.read_bytes())


if __name__ == "__main__":
    unittest.main()
