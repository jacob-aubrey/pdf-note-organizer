"""Opt-in packaged-app check; only uses the caller's disposable data directory."""
import json
import os
from . import __version__
from .workflow_ui import background


def start(app):
    def check():
        import pymupdf
        from PIL import Image
        from io import BytesIO
        path = app.data_dir / "smoke-paper.pdf"
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((50, 60), "Notable packaged application verification")
            page.add_text_annot((70, 100), "Synthetic note")
            document.save(path)
        data = app.pdf_worker.full_page(path, 1)
        with Image.open(BytesIO(data)) as image:
            image.verify()
        pages = app.pdf_worker.text_pages(path)
        if "packaged application verification" not in pages[0]["text"]:
            raise ValueError("Packaged PDF search returned unexpected text.")
        from .icons import ASSETS, BUTTON_ICONS
        missing = [name for name in set(BUTTON_ICONS.values()) if not (ASSETS / (name + ".png")).is_file()]
        if missing or not (ASSETS.parent / "cursors" / "closed-hand.cur").is_file():
            raise ValueError("Packaged UI assets are incomplete.")
        return {"ok": True, "version": __version__, "pdf_engine": pymupdf.VersionBind, "pid": os.getpid(),
                "native_pdf_worker": True, "icons": len(set(BUTTON_ICONS.values())), "pages": len(pages)}
    def finished(result):
        (app.data_dir / "smoke-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        app.close()
    background(app, check, finished, lambda error: finished({"ok": False, "error": str(error)}))
