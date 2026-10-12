"""Refresh vendored Lucide assets explicitly; never runs at app startup."""
import ast
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import urllib.request
import fitz
import re


def raster_svg(svg, name=None):
    """MuPDF drops the near-zero paths Lucide uses for round-cap dots."""
    text = svg.decode("utf-8").replace("currentColor", "#DCE4EE")
    # The Help dot needs two visible pixels even at the smallest button size.
    radius = 1.5 if name == "circle-help" else 1
    return re.sub(r'<path d="M([\d.]+) ([\d.]+)[hlv]\.01(?: 0)?"\s*/>',
                  lambda m: f'<circle cx="{m[1]}" cy="{m[2]}" r="{radius}" stroke="none" fill="#DCE4EE" />',
                  text).encode("utf-8")


def render_icon(folder, name):
    with fitz.open(stream=raster_svg((folder / (name + ".svg")).read_bytes(), name), filetype="svg") as document:
        document[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=True).save(str(folder / (name + ".png")))


def main():
    folder = Path(__file__).resolve().parents[1] / "note_organizer" / "assets" / "icons"
    module = ast.parse((folder.parents[1] / "icons.py").read_text(encoding="utf-8"))
    assignment = next(n for n in module.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "BUTTON_ICONS" for t in n.targets))
    names = sorted(set(ast.literal_eval(assignment.value).values()) | {"search"})
    def request(url):
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read()
    revision = json.loads(request("https://api.github.com/repos/lucide-icons/lucide/commits/0.468.0"))["sha"]
    base = f"https://raw.githubusercontent.com/lucide-icons/lucide/{revision}/"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "LICENSE.txt").write_bytes(request(base + "LICENSE"))
    def fetch(name):
        svg = request(base + "icons/" + name + ".svg")
        (folder / (name + ".svg")).write_bytes(svg)
        render_icon(folder, name)
    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(fetch, names))
    (folder / "SOURCE.txt").write_text("Lucide Icons\nhttps://github.com/lucide-icons/lucide\nRevision: "
                                     + revision + "\nSVG originals and 72px PNG renders; round-cap dots rendered as circles, with a larger Help dot for small-size legibility. See LICENSE.txt.\n", encoding="utf-8")
    print("Bundled", len(names), "icons from", revision)


if __name__ == "__main__":
    main()
