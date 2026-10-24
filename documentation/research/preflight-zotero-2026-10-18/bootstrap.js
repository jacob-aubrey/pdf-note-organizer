/* Test harness for a disposable, unsigned, account-free Zotero profile only. */
var config;
var report;
async function startup({ rootURI }) {
  config = JSON.parse(await (await fetch(rootURI + "config.json")).text());
  report = { started: new Date().toISOString(), version: Zotero.version, checks: [] };
  // Do not block Zotero initialization on a plugin's startup method.
  Zotero.initializationPromise.then(run).catch(async error => {
    report.fatal = String(error) + "\n" + error.stack;
    await flush();
  });
}
async function flush() {
  await IOUtils.writeUTF8(config.report, JSON.stringify(report, null, 2));
}
async function check(name, fn) {
  try { report.checks.push({ name, ...(await fn()) }); }
  catch (error) { report.checks.push({ name, status: "ERROR", error: String(error), stack: error.stack }); }
  await flush();
}
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
async function run() {
  await Zotero.uiReadyPromise;
  report.dataDirectory = Zotero.DataDirectory.dir;
  report.profileDirectory = Zotero.Profile.dir;
  assert(PathUtils.normalize(report.dataDirectory) === PathUtils.normalize(config.data), "Refuse to test outside disposable data directory");
  await flush();
  if (config.restart) {
    await runRestart();
    return;
  }
  await check("isolated_profile", async () => ({ status: "PASS", signedIn: !!Zotero.Prefs.get("sync.server.username"), data: Zotero.DataDirectory.dir }));
  let thesis, parent, main, si, same, cross, scan, long;
  await check("dissertation_metadata", async () => {
    thesis = new Zotero.Item("thesis");
    thesis.setField("title", "Synthetic doctoral dissertation");
    thesis.setField("university", "Example University");
    thesis.setField("thesisType", "Ph.D.");
    thesis.setField("date", "2026");
    thesis.setCreators([{ firstName: "Test", lastName: "Researcher", creatorType: "author" }]);
    await thesis.saveTx({ skipNotifier: true });
    let value = thesis.toJSON();
    assert(value.itemType === "thesis" && value.university === "Example University" && value.thesisType === "Ph.D.", "Thesis metadata lost");
    return { status: "PASS", metadata: value };
  });
  await check("main_and_SI_association", async () => {
    parent = new Zotero.Item("journalArticle");
    parent.setField("title", "Synthetic main article");
    await parent.saveTx({ skipNotifier: true });
    main = await Zotero.Attachments.importFromFile({ file: PathUtils.join(config.inputs, "same-page.pdf"), saveOptions: { skipNotifier: true }, parentItemID: parent.id, title: "Main article" });
    si = await Zotero.Attachments.importFromFile({ file: PathUtils.join(config.inputs, "supporting-information.pdf"), saveOptions: { skipNotifier: true }, parentItemID: parent.id, title: "Supporting information" });
    assert(parent.getAttachments().includes(main.id) && parent.getAttachments().includes(si.id), "Sibling attachment association failed");
    return { status: "PASS", parentTitle: parent.getField("title"), attachments: [main, si].map(x => ({ title: x.getField("title"), parentID: x.parentID, path: x.getFilePath() })) };
  });
  await check("nested_collections_and_tags", async () => {
    let root = new Zotero.Collection(); root.name = "Research"; await root.saveTx({ skipNotifier: true });
    let child = new Zotero.Collection(); child.name = "Nanoparticles"; child.parentID = root.id; await child.saveTx({ skipNotifier: true });
    parent.setCollections([root.id, child.id]);
    parent.setTags([{ tag: "nanoparticle" }, { tag: "read-on-tablet" }]);
    await parent.saveTx({ skipNotifier: true });
    assert(parent.getCollections().length === 2 && parent.hasTag("read-on-tablet"), "Collections/tags failed");
    return { status: "PASS", collections: parent.getCollections(), tags: parent.getTags() };
  });
  await check("linked_PDF_preserves_external_path", async () => {
    let path = PathUtils.join(config.inputs, "thesis.pdf");
    let linked = await Zotero.Attachments.linkFromFile({ file: path, parentItemID: thesis.id, saveOptions: { skipNotifier: true } });
    assert(PathUtils.normalize(await linked.getFilePathAsync()) === PathUtils.normalize(path), "Linked path changed");
    return { status: "PASS", path: await linked.getFilePathAsync(), mode: linked.attachmentLinkMode };
  });
  await check("search_inputs_indexed", async () => {
    let add = name => Zotero.Attachments.importFromFile({ file: PathUtils.join(config.inputs, name), contentType: "application/pdf", saveOptions: { skipNotifier: true } });
    same = await add("same-page.pdf"); cross = await add("cross-page.pdf"); scan = await add("scan.pdf"); long = await add("long-thesis.pdf");
    await Zotero.Fulltext.indexItems([same.id, cross.id, scan.id, long.id]);
    return { status: "PASS", ids: { same: same.id, cross: cross.id, scan: scan.id, long: long.id }, defaults: { pdfMaxPages: Zotero.Prefs.get("fulltext.pdfMaxPages"), textMaxLength: Zotero.Prefs.get("fulltext.textMaxLength") } };
  });
  async function query(conditions, mode = "all") {
    let search = new Zotero.Search(); search.libraryID = Zotero.Libraries.userLibraryID;
    search.addCondition("joinMode", mode);
    for (let [operator, text] of conditions) search.addCondition("fulltextContent", operator, text);
    return await search.search();
  }
  await check("Boolean_AND_across_PDF_pages", async () => {
    let hits = await query([["contains", "nanoparticle"], ["contains", "zirconium"]]);
    assert(hits.includes(same.id) && hits.includes(cross.id), "Cross-page whole-PDF AND not satisfied");
    return { status: "PASS", ids: hits, samePageHit: hits.includes(same.id), crossPageHit: hits.includes(cross.id) };
  });
  await check("Boolean_NOT_across_PDF_pages", async () => {
    let hits = await query([["contains", "nanoparticle"], ["doesNotContain", "zirconium"]]);
    assert(!hits.includes(same.id) && !hits.includes(cross.id), "Cross-page NOT exclusion failed");
    return { status: "PASS", ids: hits, samePageExcluded: !hits.includes(same.id), crossPageExcluded: !hits.includes(cross.id) };
  });
  await check("Boolean_OR_and_phrase", async () => {
    let hits = await query([["contains", "nanoparticle"], ["contains", "unfindableuniquemarker"]], "any");
    let phrase = await query([["contains", "alpha phrase"]]);
    assert(hits.includes(same.id) && hits.includes(cross.id) && phrase.includes(cross.id), "OR/phrase failed");
    return { status: "PASS", orHits: hits, phraseHits: phrase };
  });
  await check("image_only_PDF_requires_OCR", async () => {
    let hits = await query([["contains", "nanoparticle"]]);
    assert(!hits.includes(scan.id), "Unexpected searchable text in scan fixture");
    let text = await Zotero.PDFWorker.getFullText(scan.id, null);
    return { status: "GAP_CONFIRMED", searchable: false, extractedCharacters: text.text.length };
  });
  await check("long_thesis_default_and_complete_index", async () => {
    let before = await query([["contains", "longthesisendmarker"]]);
    await Zotero.Fulltext.indexItems([long.id], { complete: true });
    let after = await query([["contains", "longthesisendmarker"]]);
    assert(after.includes(long.id), "End marker not found after complete reindex");
    return { status: before.includes(long.id) ? "PASS" : "DEFAULT_LIMIT_CONFIRMED", pages: 551, tailFoundDefault: before.includes(long.id), tailFoundComplete: after.includes(long.id) };
  });
  await check("native_annotation_and_durable_export", async () => {
    let original = await main.getFilePathAsync();
    let before = await IOUtils.read(original);
    let annotation = await Zotero.Annotations.saveFromJSON(main, {
      key: Zotero.DataObjectUtilities.generateKey(), type: "highlight", text: "nanoparticle", comment: "Synthetic tablet-note stand-in; not a device sync test",
      color: "#ffd400", pageLabel: "1", sortIndex: "00000|000000|00000",
      position: { pageIndex: 0, rects: [[50, 740, 140, 755]] }, tags: [{ name: "test-tag" }]
    }, { skipNotifier: true });
    let after = await IOUtils.read(original);
    let changed = before.length !== after.length || before.some((x, i) => x !== after[i]);
    assert(!changed && main.getAnnotations().some(x => x.id === annotation.id), "Annotation/source behavior unexpected");
    let exported = PathUtils.join(config.run, "annotated-export.pdf");
    let count = await Zotero.PDFWorker.export(main.id, exported);
    assert(count === 1 && await IOUtils.exists(exported), "Annotated export failed");
    return { status: "PASS_WITH_WORKFLOW_LIMIT", originalUnchanged: !changed, exportedAnnotations: count, path: exported };
  });
  report.completed = new Date().toISOString();
  await flush();
  Services.startup.quit(Ci.nsIAppStartup.eAttemptQuit);
}
function install() {}
function uninstall() {}
function shutdown() {}

async function runRestart() {
  const previous = JSON.parse(await IOUtils.readUTF8(config.previousReport));
  await check("restart_preserves_thesis_and_SI", async () => {
    const old = previous.checks.find(x => x.name === "dissertation_metadata").metadata;
    const thesis = Zotero.Items.getByLibraryAndKey(Zotero.Libraries.userLibraryID, old.key);
    assert(thesis && thesis.getField("university") === "Example University", "Thesis metadata not retained");
    let children = Zotero.Items.get(2).getAttachments();
    assert(children.length === 2, "SI relationship not retained");
    return { status: "PASS", university: thesis.getField("university"), attachments: children.length };
  });
  await check("restart_preserves_complete_long_PDF_index", async () => {
    let search = new Zotero.Search(); search.libraryID = Zotero.Libraries.userLibraryID;
    search.addCondition("fulltextContent", "contains", "longthesisendmarker");
    let hits = await search.search();
    let id = previous.checks.find(x => x.name === "search_inputs_indexed").ids.long;
    assert(hits.includes(id), "Complete index end marker missing after restart");
    return { status: "PASS", ids: hits };
  });
  await check("dissertation_CSL_bibliography", async () => {
    await Zotero.Styles.init();
    const key = previous.checks.find(x => x.name === "dissertation_metadata").metadata.key;
    const item = Zotero.Items.getByLibraryAndKey(Zotero.Libraries.userLibraryID, key);
    const bibliography = await Zotero.QuickCopy.getContentFromItems([item], "bibliography=http://www.zotero.org/styles/apa");
    assert(bibliography.text.includes("Example University"), "Institution missing from thesis bibliography");
    return { status: "PASS", text: bibliography.text };
  });
  if (config.ocrPDF) {
    await check("OCR_searchable_copy_indexes_in_Zotero", async () => {
      let item = await Zotero.Attachments.importFromFile({ file: config.ocrPDF, contentType: "application/pdf", saveOptions: { skipNotifier: true } });
      await Zotero.Fulltext.indexItems([item.id], { complete: true });
      let search = new Zotero.Search(); search.libraryID = Zotero.Libraries.userLibraryID;
      search.addCondition("fulltextContent", "contains", "nanoparticle");
      let hits = await search.search();
      assert(hits.includes(item.id), "OCR text not found in imported PDF");
      return { status: "PASS", itemID: item.id, keyword: "nanoparticle", found: true };
    });
  }
  // Test double for the authorization prompt, strictly inside the synthetic profile.
  // It does not grant access to or modify the user's normal Zotero instance.
  Zotero.Server.LocalAPI._promptForAuthorization = async appName => ({
    allow: appName === "Notable disposable preflight", remember: true
  });
  report.localAPITest = { port: 23129, authPrompt: "simulated in disposable profile", ready: true };
  await flush();
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline && !(await IOUtils.exists(PathUtils.join(config.run, "api-done.json")))) {
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  report.localAPITest.completed = await IOUtils.exists(PathUtils.join(config.run, "api-done.json"));
  report.completed = new Date().toISOString();
  await flush();
  Services.startup.quit(Ci.nsIAppStartup.eAttemptQuit);
}
