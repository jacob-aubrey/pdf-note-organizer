"""Diagnose the real WebView2/PDF.js bootstrap before the full Windows suite."""
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from note_organizer.reader_server import ReaderServer
from tests.reader_app_regression import require_private_desktop


class ProbeServer(ReaderServer):
    def _serve_file(self, handler, path, *, head, document=None):
        if document is None and path.name == "index.html":
            # Capture failed module imports even when the app bridge never starts.
            page = path.read_text(encoding="utf-8").replace(
                '<script type="module" src="reader.mjs"></script>',
                '<script type="module">import("./reader.mjs").catch(error => '
                '{ window.readerBootstrapError = String(error.stack || error); });</script>')
            content = page.encode("utf-8")
            self._headers(handler, 200, len(content), "text/html; charset=utf-8")
            if not head:
                handler.wfile.write(content)
            return
        super()._serve_file(handler, path, head=head, document=document)


def main():
    require_private_desktop()
    import webview
    ready = threading.Event()
    result = {}

    class API:
        def event(self, payload):
            if payload.get("kind") == "ready":
                ready.set()

    server = ProbeServer()
    window = webview.create_window("Notable runtime check", server.url, js_api=API(),
                                   hidden=True, frameless=True, focus=False, width=700, height=600)

    def check():
        try:
            if not window.events.loaded.wait(25):
                raise RuntimeError("WebView2 did not load the local HTML page")
            ready.wait(8)
            result.update(window.evaluate_js("""({
                userAgent: navigator.userAgent, documentState: document.readyState,
                mapInsertion: typeof Map.prototype.getOrInsertComputed,
                promiseResolvers: typeof Promise.withResolvers, promiseTry: typeof Promise.try,
                regexpEscape: typeof RegExp.escape,
                bootstrapError: window.readerBootstrapError || null
            })"""))
            result["ready"] = ready.is_set()
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            print(json.dumps(result, indent=2), flush=True)
            window.destroy()

    try:
        webview.start(check, gui="edgechromium", private_mode=True)
    finally:
        server.close()
    if not result.get("ready"):
        raise SystemExit("PDF reader bootstrap failed; see runtime details above")


if __name__ == "__main__":
    main()
