"""Reproduce Notable's app icon from the locally vendored Lucide SVG."""
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render(size):
    resolution = size * 4
    tile = Image.new("RGBA", (resolution, resolution))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, resolution - 1, resolution - 1),
                                          radius=resolution * .19, fill="#1B629B")
    svg = (ROOT / "note_organizer/assets/icons/notebook-pen.svg").read_bytes().replace(b"currentColor", b"#ffffff")
    inset = round(resolution * .10)
    glyph_size = resolution - inset * 2
    with fitz.open(stream=svg, filetype="svg") as document:
        pixels = document[0].get_pixmap(matrix=fitz.Matrix(glyph_size / 24, glyph_size / 24), alpha=True)
        with Image.open(BytesIO(pixels.tobytes("png"))) as glyph:
            tile.alpha_composite(glyph, (inset, inset))
    return tile.resize((size, size), Image.Resampling.LANCZOS)


def main():
    folder = ROOT / "note_organizer/assets/branding"
    folder.mkdir(parents=True, exist_ok=True)
    images = [render(size) for size in SIZES]
    images[-1].save(folder / "notable.png")
    images[SIZES.index(64)].save(folder / "notable-64.png")
    images[-1].save(ROOT / "Note icon.ico", format="ICO", sizes=[(size, size) for size in SIZES],
                    append_images=images[:-1])
    print("Generated Notable PNG and nine Windows icon sizes from bundled Lucide notebook-pen.")


if __name__ == "__main__":
    main()
