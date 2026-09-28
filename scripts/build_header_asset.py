"""Export header and probe-chart artwork from SRA_FINAL3.pdf using PyMuPDF."""

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path


# Centers of the S circle, A diamond and F square in SRA_FINAL3.pdf coordinates.
ANCHORS = {
    "S": [161.03824, 29.69497],
    "A": [161.03824, 74.94447],
    "F": [290.42352, 74.23745],
}


def build_assets(assets):
    import pymupdf

    source = assets / "SRA_FINAL3.pdf"
    destination = source.with_suffix(".svg")
    with pymupdf.open(source) as document:
        if len(document) != 1:
            raise ValueError("The header PDF must contain exactly one page")
        # Outlined text preserves the original fonts in browsers without font dependencies.
        svg = document[0].get_svg_image(text_as_path=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = f"<!-- Source: {source.name}; SHA-256: {digest}; PyMuPDF {pymupdf.VersionBind} -->\n"
    destination.write_text(metadata + svg, encoding="utf-8")
    # The unregularized model shares the architecture without the red SRA annotation.
    root = ET.fromstring(svg)
    removed = 0
    for parent in list(root.iter()):
        for child in list(parent):
            if any(child.get(attr, "").lower() == "#ff3333" for attr in ("fill", "stroke")):
                parent.remove(child)
                removed += 1
    if not removed:
        raise ValueError("No SRA annotation found in the source artwork")
    baseline = metadata + ET.tostring(root, encoding="unicode")
    (assets / "SRA_FINAL3-baseline.svg").write_text(baseline, encoding="utf-8")


def read_assets(assets):
    svg = (assets / "SRA_FINAL3.svg").read_text()
    baseline_svg = (assets / "SRA_FINAL3-baseline.svg").read_text()
    _, _, width, height = map(float, ET.fromstring(svg).attrib["viewBox"].split())
    return svg, baseline_svg, dict(
        source="assets/SRA_FINAL3.pdf", width=width, height=height, anchors=ANCHORS,
    )


def main():
    assets = Path(__file__).resolve().parents[1] / "assets"
    build_assets(assets)
    print(f"Exported header and baseline vectors to {assets}")


if __name__ == "__main__":
    main()
