"""Prepare synthetic inputs and a disposable Zotero profile; never open a real library."""
from pathlib import Path
import json
import tempfile
import zipfile

import fitz

HERE = Path(__file__).resolve().parent
scratch = HERE.parents[2] / ".test-tmp"
scratch.mkdir(exist_ok=True)
run = Path(tempfile.mkdtemp(prefix="zotero-route-", dir=scratch))
profile = run / "profile"
data = run / "data"
inputs = run / "inputs"
plugin = run / "probe-plugin"
for path in [profile / "extensions", data, inputs, plugin]:
    path.mkdir(parents=True, exist_ok=True)

def pdf(name, pages):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 80), text)
    doc.save(inputs / name)
    doc.close()

pdf("cross-page.pdf", ["nanoparticle\nalpha phrase", "zirconium\nbeta phrase"])
pdf("same-page.pdf", ["nanoparticle zirconium\nalpha phrase"])
pdf("supporting-information.pdf", ["Supplementary spectra and experimental data."])
pdf("thesis.pdf", ["Synthetic doctoral dissertation\nPh.D.\nExample University", "dissertationendmarker"])
doc = fitz.open()
page = doc.new_page()
source = fitz.open(inputs / "same-page.pdf")
pix = source[0].get_pixmap()
page.insert_image(page.rect, stream=pix.tobytes("png"))
doc.save(inputs / "scan.pdf")
doc.close()
source.close()
pdf("long-thesis.pdf", [f"Synthetic thesis page {i+1}" for i in range(550)] + ["longthesisendmarker"])

config = {"run": str(run), "profile": str(profile), "data": str(data), "inputs": str(inputs),
          "report": str(run / "results.json"), "plugin": str(plugin)}
(HERE / "run-location.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
(plugin / "config.json").write_text(json.dumps(config), encoding="utf-8")
manifest = {
    "manifest_version": 2, "name": "Disposable Notable route preflight", "version": "0.0.1",
    "applications": {"zotero": {"id": "notable-route-preflight@example.invalid", "strict_min_version": "9.0", "strict_max_version": "10.*", "update_url": "https://example.invalid/updates.json"}},
}
(plugin / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
script = (HERE / "bootstrap.js").read_text(encoding="utf-8")
(plugin / "bootstrap.js").write_text(script, encoding="utf-8")
(profile / "extensions" / "notable-route-preflight@example.invalid").write_text(str(plugin), encoding="utf-8")
prefs = {
    "extensions.zotero.firstRun2": False,
    "extensions.zotero.firstRunGuidance": False,
    "extensions.zotero.useDataDir": True,
    "extensions.zotero.dataDir": str(data),
    "extensions.zotero.sync.autoSync": False,
    "extensions.zotero.automaticScraperUpdates": False,
    "extensions.zotero.httpServer.enabled": False,
    "extensions.zotero.warnOnUnsafeDataDir": False,
    "extensions.zoteroWinWordIntegration.skipInstallation": True,
    "extensions.zoteroOpenOfficeIntegration.skipInstallation": True,
    "extensions.update.enabled": False,
    "extensions.autoDisableScopes": 0,
    "extensions.enabledScopes": 15,
    "extensions.startupScanScopes": 15,
    "app.update.enabled": False,
    "app.update.auto": False,
    "browser.shell.checkDefaultBrowser": False,
}
(profile / "user.js").write_text("\n".join(f"user_pref({json.dumps(k)}, {json.dumps(v)});" for k, v in prefs.items()), encoding="utf-8")
print(json.dumps(config, indent=2))
