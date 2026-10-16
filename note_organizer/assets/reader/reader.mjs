import * as pdfjsLib from "../pdfjs/build/pdf.mjs";
const { EventBus, PDFViewer, PDFLinkService, PDFFindController } =
  await import("../pdfjs/web/pdf_viewer.mjs");

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL("../pdfjs/build/pdf.worker.mjs", import.meta.url).href;

const $ = id => document.getElementById(id);
const eventBus = new EventBus();
const linkService = new PDFLinkService({ eventBus, ignoreDestinationZoom: true });
let inPdfFind = false;
let mainPageMatches = [];
let mainPageMatchesLength = [];
let mainSelected = { pageIdx: -1, matchIdx: -1 };
let mainScrollMatches = false;
let mainMapping = null;
let mainMappingBuilds = 0;
// Keep PDF-local Find's full candidate set separate from the main search's
// actual enabled-field occurrences. TextHighlighter reads this display facade,
// so a late PDF.js extraction cannot paint unrelated query words.
class ScopedFindController extends PDFFindController {
  get pageMatches() { return inPdfFind ? super.pageMatches : mainPageMatches; }
  get pageMatchesLength() { return inPdfFind ? super.pageMatchesLength : mainPageMatchesLength; }
  get selected() { return inPdfFind ? super.selected : mainSelected; }
  get highlightMatches() { return inPdfFind ? super.highlightMatches : true; }
  get state() { return inPdfFind ? super.state : { highlightAll: true }; }
  get candidateMatches() { return super.pageMatches; }
  get candidateLengths() { return super.pageMatchesLength; }
}
const findLinkService = {
  get page() { return linkService.page; },
  set page(value) {
    if (!inPdfFind) return;
    linkService.page = value;
    // Fit the destination page before its text layer paints the selected hit,
    // including documents with pages of different widths.
    viewer.currentScaleValue = defaultScale();
    // Scaling may restore PDF.js's cached location on the preceding page.
    linkService.page = value;
  },
  get pagesCount() { return linkService.pagesCount; },
};
const findController = new ScopedFindController({ eventBus, linkService: findLinkService, delay: 100 });
const viewer = new PDFViewer({
  container: $("viewerContainer"), viewer: $("viewer"), eventBus,
  linkService, findController,
  annotationMode: pdfjsLib.AnnotationMode.ENABLE,
  annotationEditorMode: pdfjsLib.AnnotationEditorType.DISABLE,
  enableHighlightFloatingButton: false,
  imageResourcesPath: new URL("../pdfjs/web/images/", import.meta.url).href,
  enablePermissions: true,
});
linkService.setViewer(viewer);

let active = null;
let pdfDocument = null;
let loadingTask = null;
let generation = 0;
let ready = false;
let findTimer = null;
let pendingMatch = null;
let matchCount = { current: 0, total: 0 };
let findStatus = 0;
let stateTimer = null;
let pendingOpen = null;
let expanded = false;
let requestedMatch = { index: 0 };
let rawPageText = new Map();
let missingMainMatchPage = null;
let lastWarning = "";
let pan = null;
let readingSnapshot = null;
let suppressLinkClickUntil = 0;
let suppressedPopups = new Set();

// PDF.js normally centers the selected word horizontally. Main-result arrows
// instead reveal the line vertically while keeping the fitted page centered.
// PDF-local Find also reveals the selected line while keeping the page centered.
findController.scrollMatchIntoView = function (request) {
  const { element, pageIndex, matchIndex } = request;
  if (inPdfFind) {
    if (!this._scrollMatches || !element || pageIndex !== this.selected.pageIdx ||
        matchIndex !== this.selected.matchIdx) return;
    // Wait until page fitting and highlight painting finish. A scale change
    // can replace this text layer; only a connected, still-selected hit may
    // consume the pending scroll, and it may do so only once.
    const document = pdfDocument;
    requestAnimationFrame(() => {
      if (!inPdfFind || pdfDocument !== document || !this._scrollMatches ||
          !element.isConnected || pageIndex !== this.selected.pageIdx ||
          matchIndex !== this.selected.matchIdx) return;
      this._scrollMatches = false;
      const container = $("viewerContainer");
      container.scrollTop += element.getBoundingClientRect().top - container.getBoundingClientRect().top - 65;
      container.scrollLeft = 0;
      reportState();
    });
    return;
  }
  if (!mainScrollMatches || !element || pageIndex !== this.selected.pageIdx ||
      matchIndex !== this.selected.matchIdx) return;
  const document = pdfDocument, selection = mainSelected;
  requestAnimationFrame(() => {
    if (inPdfFind || pdfDocument !== document || mainSelected !== selection ||
        !mainScrollMatches || !element.isConnected ||
        pageIndex !== this.selected.pageIdx || matchIndex !== this.selected.matchIdx) return;
    mainScrollMatches = false;
    const container = $("viewerContainer");
    container.scrollTop += element.getBoundingClientRect().top - container.getBoundingClientRect().top - 65;
    container.scrollLeft = 0;
    reportState();
  });
};

function report(kind, values = {}) {
  const event = { kind, id: active?.id ?? null, ...values };
  const bridge = window.pywebview?.api?.event;
  if (bridge) Promise.resolve(bridge(event)).catch(() => {});
}

function reportWarning(message) {
  lastWarning = String(message || "PDF reader warning.");
  report("warning", { message: lastWarning });
}

function diagnosticState() {
  return {
    id: active?.id ?? null, url: active?.url ?? null, title: active?.title ?? "",
    ready, loaded: ready, page: ready ? viewer.currentPageNumber : 0,
    pages: pdfDocument?.numPages ?? 0,
    scale: ready ? viewer.currentScale : 0,
    scaleValue: ready ? viewer.currentScaleValue : "page-width",
    selectedPage: active?.page ?? 0,
    hasSelection: !!active?.hasSelection,
    selectedMatch: { ...findController.selected },
    pageMatches: findController.pageMatches.map(matches => matches?.length ?? 0),
    matches: { ...matchCount }, findMode: inPdfFind ? "pdf" : "library",
    mainMappingBuilds,
    findQuery: $("findInput").value, expanded,
    panning: pan !== null,
    scroll: { left: $("viewerContainer").scrollLeft, top: $("viewerContainer").scrollTop },
    textLayers: document.querySelectorAll(".textLayer").length,
    renderedPages: document.querySelectorAll(".page canvas").length,
    selectionOutlined: !!document.querySelector(".notable-selection"),
    suppressedPopupCount: suppressedPopups.size,
    annotationEditorMode: viewer.annotationEditorMode,
    renderForms: viewer.renderForms, enableScripting: viewer.enableScripting,
    lastWarning,
    message: $("empty").hidden ? "" : $("empty").textContent,
  };
}

function reportState() {
  clearTimeout(stateTimer);
  stateTimer = setTimeout(() => report("state", diagnosticState()), 60);
}

function updateControls() {
  for (const id of ["pageNumber", "zoom", "zoomIn", "zoomOut", "findToggle"]) {
    $(id).disabled = !ready;
  }
  $("backToSelection").disabled = !ready || !active?.hasSelection;
  $("backToSelection").title = !ready ? "Open a PDF to return to its selected note or main search result." : !active?.hasSelection ?
    "Select a note or main search result to enable returning to its location." :
    "Return to the selected note or main search result and resume main search highlighting.";
  $("previousPage").disabled = !ready || viewer.currentPageNumber <= 1;
  $("nextPage").disabled = !ready || viewer.currentPageNumber >= (pdfDocument?.numPages ?? 0);
  $("previousPage").title = !ready ? "Open a PDF to browse pages." :
    viewer.currentPageNumber <= 1 ? "Already on the first PDF page." : "Go to the previous PDF page.";
  $("nextPage").title = !ready ? "Open a PDF to browse pages." :
    viewer.currentPageNumber >= pdfDocument.numPages ? "Already on the last PDF page." : "Go to the next PDF page.";
  $("findToggle").title = !ready ? "Open a PDF to find words or phrases within it." :
    $("findbar").hidden ? "Find a word or phrase in this PDF (Ctrl+F). Main search results stay unchanged." :
    "Close Find in PDF and resume main search highlighting (Escape).";
  $("pageNumber").value = ready ? viewer.currentPageNumber : 1;
  $("pageCount").textContent = `of ${pdfDocument?.numPages ?? 0}`;
  $("viewerContainer").style.visibility = ready ? "visible" : "hidden";
}

function updateScale() {
  const scaleValue = String(viewer.currentScaleValue);
  const exact = [...$("zoom").options].find(option => option.value === scaleValue && option.value !== "custom");
  $("customZoom").hidden = !!exact;
  if (exact) $("zoom").value = scaleValue;
  else {
    $("customZoom").textContent = `${Math.round(viewer.currentScale * 100)}%`;
    $("zoom").value = "custom";
  }
  reportState();
}

function validTerms(terms) {
  return [...new Set((Array.isArray(terms) ? terms : []).filter(term => typeof term === "string").map(term => term.trim()).filter(Boolean))];
}

function validMainHits(hits) {
  return (Array.isArray(hits) ? hits : []).filter(hit => hit && typeof hit === "object").map(hit => ({ ...hit }));
}

function matchRequest(value) {
  const request = value && typeof value === "object" ? value : { index: value };
  const result = { index: Math.max(0, Number.parseInt(request.index, 10) || 0), fitWidth: true };
  for (const field of ["term", "text", "normalized_text", "context", "before", "after", "field"]) {
    if (typeof request[field] === "string") result[field] = request[field];
  }
  return result;
}

function mainCandidateTerms() {
  // Search the actual enabled-field spellings rather than every query term.
  // Full union spans preserve overlapping Boolean terms; original spellings
  // also let PDF.js find case-folded backend hits such as Straße / strasse.
  return validTerms(active.mainHits.filter(hit => ["quote", "context", "pdf"].includes(hit.field))
    .flatMap(hit => [hit.normalized_text, hit.text]));
}

function resetMainHighlights() {
  mainPageMatches = [];
  mainPageMatchesLength = [];
  mainSelected = { pageIdx: -1, matchIdx: -1 };
  mainScrollMatches = false;
  mainMapping = null;
}

function updateSearchAuthority() {
  $("viewerContainer").dataset.searchMode = inPdfFind ? "pdf" : "main";
}

function defaultScale() { return expanded ? "1.25" : "page-width"; }

function applyMainDefault(page) {
  viewer.currentPageNumber = Math.min(Math.max(1, page), pdfDocument.numPages);
  viewer.currentScaleValue = defaultScale();
  // Fitting may restore PDF.js's previous cached location. Keep this target.
  viewer.currentPageNumber = Math.min(Math.max(1, page), pdfDocument.numPages);
  $("viewerContainer").scrollLeft = 0;
}

function normalizeImportedPopups(document, suppressedByPage) {
  // Subject/custom import fields are not exposed by PDF.js. The local PDF
  // worker identifies only verified quote-only reMarkable annotations; strip
  // their display popup data here, leaving appearance streams and source bytes
  // untouched. Genuine comments and ordinary PDF annotations remain intact.
  const getPage = document.getPage.bind(document);
  const wrapped = new WeakSet();
  const normalizedIds = suppressedPopups;
  document.getPage = async function (pageNumber) {
    const page = await getPage(pageNumber);
    const ids = suppressedByPage[String(pageNumber)];
    if (!Array.isArray(ids) || !ids.length || wrapped.has(page)) return page;
    wrapped.add(page);
    const suppressed = new Set(ids.map(id => String(id).endsWith("R") ? String(id) : `${id}R`));
    const getAnnotations = page.getAnnotations.bind(page);
    page.getAnnotations = async function (options) {
      const annotations = await getAnnotations(options);
      if (options?.intent && options.intent !== "display") return annotations;
      const popups = new Set(annotations.filter(annotation => suppressed.has(annotation.id))
        .map(annotation => annotation.popupRef).filter(Boolean));
      return annotations.filter(annotation => !popups.has(annotation.id)).map(annotation => {
        if (!suppressed.has(annotation.id)) return annotation;
        normalizedIds.add(`${pageNumber}:${annotation.id}`);
        return { ...annotation, titleObj: { str: "", dir: "ltr" },
          contentsObj: { str: "", dir: "ltr" }, richText: null, popupRef: null };
      });
    };
    return page;
  };
}

function captureView() {
  if (!ready) return null;
  const page = viewer.currentPageNumber;
  const pageRect = viewer.getPageView(page - 1)?.div.getBoundingClientRect();
  const containerRect = $("viewerContainer").getBoundingClientRect();
  if (!pageRect) return null;
  return { url: active.url, page, scaleValue: viewer.currentScaleValue,
    x: (containerRect.left - pageRect.left) / viewer.currentScale,
    y: (containerRect.top - pageRect.top) / viewer.currentScale };
}

function restoreView(snapshot) {
  if (!ready || snapshot?.url !== active?.url) return;
  viewer.currentScaleValue = snapshot.scaleValue;
  viewer.currentPageNumber = Math.min(snapshot.page, pdfDocument.numPages);
  // Wait for both the scale update and the native pane's restored dimensions.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (!ready || expanded || snapshot.url !== active?.url) return;
    const container = $("viewerContainer");
    const pageRect = viewer.getPageView(snapshot.page - 1)?.div.getBoundingClientRect();
    if (!pageRect) return;
    const containerRect = container.getBoundingClientRect();
    container.scrollLeft += pageRect.left - containerRect.left + snapshot.x * viewer.currentScale;
    container.scrollTop += pageRect.top - containerRect.top + snapshot.y * viewer.currentScale;
    reportState();
  }));
}

function runFind(query, type = "", previous = false) {
  if (!ready) return;
  matchCount = { current: 0, total: 0 };
  eventBus.dispatch("find", {
    source: window, type, query, caseSensitive: false,
    entireWord: false, highlightAll: true, findPrevious: previous,
    matchDiacritics: false,
  });
}

function useLibraryTerms() {
  if (!ready) return;
  inPdfFind = false;
  applyMainDefault(active.page);
  missingMainMatchPage = null;
  resetMainHighlights();
  updateSearchAuthority();
  const candidateTerms = mainCandidateTerms();
  pendingMatch = candidateTerms.length ? { page: active.page, ...requestedMatch } : null;
  if (!pendingMatch) requestedMatch.fitWidth = false;
  // Reapplying a main result is not a "find next" action. The normal Find
  // dispatch advances an already selected match after its debounce expires.
  runFind(candidateTerms, "highlightallchange");
  eventBus.dispatch("updatetextlayermatches", { source: findController, pageIndex: -1 });
  updateMatches();
}

function restoreMainSearch() {
  clearTimeout(findTimer);
  findTimer = null;
  inPdfFind = false;
  $("findInput").value = "";
  $("findbar").hidden = true;
  $("findToggle").setAttribute("aria-expanded", "false");
  updateControls();
  useLibraryTerms();
}

function updateMatches() {
  const text = matchCount.total ? `${matchCount.current || 1} / ${matchCount.total}` :
    findStatus === 3 ? "Searching…" : "No matches";
  $("findCount").textContent = inPdfFind && $("findInput").value ? text : "";
  $("findPrevious").disabled = !ready || !$("findInput").value;
  $("findNext").disabled = !ready || !$("findInput").value;
  $("findPrevious").title = !$("findInput").value ? "Enter a word or phrase to navigate PDF matches." :
    "Previous match in this PDF (Shift+Enter). Reveals the match and keeps the page centered.";
  $("findNext").title = !$("findInput").value ? "Enter a word or phrase to navigate PDF matches." :
    "Next match in this PDF (Enter). Reveals the match and keeps the page centered.";
  reportState();
}

// The host selects a zero-based occurrence on the selected result's page.
// PDF.js 6.4.299 exposes selected/pageMatches, but not direct match selection.
// Keep this small pinned-version adapter here so arrow navigation resumes there.
// Optional excerpt context disambiguates hits when another PDF extractor orders
// columns differently. Public match offsets address the concatenated text-layer
// item strings. PDF.js's normalization map excludes synthetic hasEOL newlines;
// adding those newlines here would shift every later hit on the page.
function normalizedWords(text) {
  return String(text || "").normalize("NFKC").toLocaleLowerCase()
    .replace(/ß/g, "ss").replace(/\u00ad/g, "").replace(/[-\u2010]\s+/g, "").match(/[\p{L}\p{N}]+/gu) || [];
}

function matchingEdge(actual, expected, fromEnd = false) {
  let common = 0;
  const length = Math.min(actual.length, expected.length, 18);
  while (common < length) {
    const a = fromEnd ? actual[actual.length - common - 1] : actual[common];
    const b = fromEnd ? expected[expected.length - common - 1] : expected[common];
    if (a !== b) break;
    common++;
  }
  return common;
}

function contextualMatchIndex(request, matches, lengths, text) {
  const fallback = Math.min(Math.max(0, request.index), matches.length - 1);
  const term = normalizedWords(request.normalized_text || request.text || request.term).join(" ");
  const words = normalizedWords(request.context || request.snippet);
  const before = normalizedWords(request.before), after = normalizedWords(request.after);
  if (!term && !words.length && !before.length && !after.length) return fallback;
  const target = new Set(words);
  let best = null, bestScore = -1, equallyGood = 0;
  for (let index = 0; index < matches.length; index++) {
    if (request.allowedCandidates && !request.allowedCandidates.has(index)) continue;
    const start = matches[index], end = start + lengths[index];
    const actualTerm = normalizedWords(text.slice(start, end)).join(" ");
    if (term && actualTerm !== term && actualTerm.replaceAll(" ", "") !== term.replaceAll(" ", "")) continue;
    const radius = Math.min(800, Math.max(160, String(request.context || "").length));
    const nearby = new Set(normalizedWords(text.slice(Math.max(0, start - radius), end + radius)));
    let score = term && actualTerm === term ? 2 : 0;
    const leftEdge = matchingEdge(normalizedWords(text.slice(Math.max(0, start - 180), start)), before, true);
    const rightEdge = matchingEdge(normalizedWords(text.slice(end, end + 180)), after);
    if (before.length + after.length >= 2 && !leftEdge && !rightEdge) continue;
    // Words directly beside this exact occurrence are stronger evidence than
    // a general snippet which might contain several adjacent occurrences.
    score += (leftEdge + rightEdge) / 2;
    if (target.size) {
      let common = 0;
      for (const word of target) if (nearby.has(word)) common++;
      // A typed comment or metadata hit need not occur in the printed PDF.
      // Do not navigate to a stray instance of its query word elsewhere.
      if (target.size >= 4 && common < Math.min(3, target.size)) continue;
      score += common / target.size;
    }
    // Identical contexts keep the requested relative occurrence stable.
    if (score > bestScore + 1e-8) { best = index; bestScore = score; equallyGood = 1; }
    else if (Math.abs(score - bestScore) < 1e-8) {
      equallyGood++;
      if (Math.abs(index - fallback) < Math.abs(best - fallback)) best = index;
    }
  }
  // A one-word note without surrounding text cannot identify which of several
  // identical printed words belongs to its annotation. Prefer no mark to a
  // fabricated location. Full-page PDF hits retain their source-order offset.
  if (request.strict && request.field !== "pdf" && equallyGood > 1 && bestScore <= 3) return null;
  return best;
}

function matchContextKey(request) {
  return JSON.stringify([request.index, request.normalized_text || request.text || request.term,
    request.context || request.snippet, request.before, request.after, request.field]);
}

function quoteCandidatesInSelection(pageIdx, matches, lengths) {
  if (!active.rect) return null;
  const page = viewer.getPageView(pageIdx);
  const mapping = page?.textLayer?.highlighter;
  if (!mapping?.textDivs?.length || !mapping.textContentItemsStr?.length ||
      page.textLayer.div.hidden || !page.textLayer.div.isConnected) return undefined;
  const rectangle = [...page.viewport.convertToViewportPoint(active.rect[0], active.rect[1]),
                     ...page.viewport.convertToViewportPoint(active.rect[2], active.rect[3])];
  const pageBounds = page.div.getBoundingClientRect();
  const left = Math.min(rectangle[0], rectangle[2]) + pageBounds.left;
  const right = Math.max(rectangle[0], rectangle[2]) + pageBounds.left;
  const top = Math.min(rectangle[1], rectangle[3]) + pageBounds.top;
  const bottom = Math.max(rectangle[1], rectangle[3]) + pageBounds.top;
  function textPoint(offset) {
    for (let index = 0; index < mapping.textContentItemsStr.length; index++) {
      const length = mapping.textContentItemsStr[index].length;
      if (offset > length || !length) { offset -= length; continue; }
      const div = mapping.textDivs[index];
      if (!div) return null;
      if (div.nodeType === Node.TEXT_NODE) return [div, Math.min(offset, div.length)];
      const walker = document.createTreeWalker(div, NodeFilter.SHOW_TEXT);
      let node, previous = null;
      while ((node = walker.nextNode())) {
        previous = node;
        if (offset <= node.length) return [node, offset];
        offset -= node.length;
      }
      return previous ? [previous, previous.length] : null;
    }
    return null;
  }
  const accepted = new Set();
  let measurable = false;
  matches.forEach((start, index) => {
    const from = textPoint(start), to = textPoint(start + lengths[index]);
    if (!from || !to) return;
    const range = document.createRange();
    range.setStart(...from);
    range.setEnd(...to);
    if ([...range.getClientRects()].some(box => {
      if (!box.width || !box.height) return false;
      measurable = true;
      const x = (box.left + box.right) / 2, y = (box.top + box.bottom) / 2;
      return x >= left - 2 && x <= right + 2 && y >= top - 2 && y <= bottom + 2;
    })) accepted.add(index);
  });
  return measurable ? accepted : undefined;
}

function keepMainResultPage(pageIdx) {
  const previousPage = findController.selected.pageIdx;
  Object.assign(findController.selected, { pageIdx: -1, matchIdx: -1 });
  findController._scrollMatches = false;
  mainScrollMatches = false;
  viewer.currentPageNumber = pageIdx + 1;
  if (previousPage >= 0) eventBus.dispatch("updatetextlayermatches", { source: findController, pageIndex: previousPage });
  reportState();
}

function applyPendingMatch() {
  if (!pendingMatch || !ready || inPdfFind) return false;
  if (findController._dirtyMatch) return false;
  const pageIdx = pendingMatch.page - 1;
  if (pendingMatch.fitWidth === true) {
    applyMainDefault(pageIdx + 1);
    pendingMatch.fitWidth = false;
    requestedMatch.fitWidth = false;
  }
  const matches = findController.candidateMatches[pageIdx];
  if (!matches) return false;
  if (!matches.length) {
    requestedMatch.fitWidth = false;
    pendingMatch = null;
    missingMainMatchPage = pageIdx;
    keepMainResultPage(pageIdx);
    return false;
  }
  const request = pendingMatch;
  if (active.mainHits.length && !rawPageText.has(pageIdx)) {
    const document = pdfDocument;
    // Cache one promise as well as the result, so repeated find events do not
    // enqueue duplicate extraction or allow stale requests to win the race.
    const extraction = document.getPage(pageIdx + 1).then(page => page.getTextContent({ disableNormalization: true }))
      .then(content => content.items.map(item => item.str).join(""))
      .catch(() => "");
    rawPageText.set(pageIdx, extraction);
    extraction.then(text => {
      if (pdfDocument !== document) return;
      rawPageText.set(pageIdx, text);
      applyPendingMatch();
    });
    return false;
  }
  const raw = rawPageText.get(pageIdx);
  if (raw instanceof Promise) return false;
  const lengths = findController.candidateLengths[pageIdx];
  // Mapping enabled-field hits back to PDF.js text is expensive. Reuse it
  // while navigating this result instead of comparing every hit on every key.
  if (!mainMapping || mainMapping.pageIdx !== pageIdx || mainMapping.matches !== matches ||
      mainMapping.lengths !== lengths || mainMapping.hits !== active.mainHits) {
    const hasQuote = active.mainHits.some(hit => hit.field === "quote");
    const quoteCandidates = hasQuote ? quoteCandidatesInSelection(pageIdx, matches, lengths) : null;
    if (quoteCandidates === undefined) return false;
    const candidates = new Set(), selections = new Map();
    active.mainHits.forEach((hit, index) => {
      if (!["quote", "context", "pdf"].includes(hit.field)) return;
      const descriptor = { ...hit, index, strict: true,
        allowedCandidates: hit.field === "quote" ? quoteCandidates : null };
      const candidate = contextualMatchIndex(descriptor, matches, lengths, raw || "");
      selections.set(matchContextKey(descriptor), candidate);
      if (candidate !== null) candidates.add(candidate);
    });
    const candidateIndices = [...candidates].sort((left, right) => left - right);
    mainMapping = { pageIdx, matches, lengths, hits: active.mainHits,
      quoteCandidates, candidateIndices, selections };
    mainMappingBuilds++;
    mainPageMatches[pageIdx] = candidateIndices.map(index => matches[index]);
    mainPageMatchesLength[pageIdx] = candidateIndices.map(index => lengths[index]);
  }
  const { quoteCandidates, candidateIndices, selections } = mainMapping;
  const hit = active.mainHits[request.index];
  let selectedCandidate = null;
  if (hit && ["quote", "context", "pdf"].includes(hit.field)) {
    const descriptor = { ...hit, ...request, strict: true,
      allowedCandidates: hit.field === "quote" ? quoteCandidates : null };
    const key = matchContextKey(descriptor);
    if (!selections.has(key)) selections.set(key, contextualMatchIndex(descriptor, matches, lengths, raw || ""));
    selectedCandidate = selections.get(key);
  }
  const matchIdx = selectedCandidate === null ? null : candidateIndices.indexOf(selectedCandidate);
  const previousPage = findController.selected.pageIdx;
  if (matchIdx === null || matchIdx < 0) {
    pendingMatch = null;
    missingMainMatchPage = pageIdx;
    keepMainResultPage(pageIdx);
    eventBus.dispatch("updatetextlayermatches", { source: findController, pageIndex: pageIdx });
    return false;
  }
  Object.assign(findController.selected, { pageIdx, matchIdx });
  Object.assign(findController._offset, { pageIdx, matchIdx, wrapped: false });
  mainScrollMatches = true;
  pendingMatch = null;
  missingMainMatchPage = null;
  viewer.currentPageNumber = pageIdx + 1;
  if (previousPage >= 0 && previousPage !== pageIdx) {
    eventBus.dispatch("updatetextlayermatches", { source: findController, pageIndex: previousPage });
  }
  eventBus.dispatch("updatetextlayermatches", { source: findController, pageIndex: pageIdx });
  let total = 0, current = matchIdx + 1;
  findController.pageMatches.forEach((list, index) => {
    total += list?.length ?? 0;
    if (index < pageIdx) current += list?.length ?? 0;
  });
  matchCount = { current, total };
  updateMatches();
  return true;
}

function jumpToSelection() {
  if (!ready || !active) return;
  const page = Math.min(Math.max(1, active.page), pdfDocument.numPages);
  active.page = page;
  if (active.rect) {
    viewer.scrollPageIntoView({
      pageNumber: page,
      destArray: [null, { name: "XYZ" }, active.rect[0], active.rect[3], null],
      ignoreDestinationZoom: true,
    });
  } else viewer.currentPageNumber = page;
  reportState();
}

function updateDocumentTitle(value) {
  const title = typeof value === "string" ? value : "";
  $("documentTitle").textContent = title;
  $("documentTitle").title = title;
  $("documentInfo").hidden = !title;
}

function setTitle(value, id = active?.id) {
  if (!active?.url || id !== active.id) return false;
  active.title = typeof value === "string" && value ? value : "PDF document";
  updateDocumentTitle(active.title);
  reportState();
  return true;
}

function applySelection() {
  if (!ready || !active) return;
  updateDocumentTitle(active.title || "PDF document");
  $("empty").hidden = true;
  $("loading").hidden = true;
  jumpToSelection();
  // open() is a main-result selection. It always restores the main search;
  // visibility changes between the two views do not call this method.
  restoreMainSearch();
  updateControls();
}

async function open(payload) {
  const token = ++generation;
  let passwordRejected = false;
  try {
    endPan();
    setPanReady(false);
    if (!payload || typeof payload.url !== "string") throw new Error("No PDF was selected.");
    const url = new URL(payload.url, location.href);
    if (!/^https?:$/.test(url.protocol) || url.origin !== location.origin) {
      throw new Error("The PDF must be served by this local reader.");
    }
    const oldUrl = active?.url;
    if (typeof payload.expanded === "boolean" && payload.expanded !== expanded) {
      readingSnapshot = payload.expanded ? captureView() : null;
      expanded = payload.expanded;
    }
    lastWarning = "";
    const rectangle = Array.isArray(payload.rect) && payload.rect.length === 4 && payload.rect.every(Number.isFinite) ? payload.rect.slice() : null;
    active = { id: payload.id ?? null, url: url.href,
      title: typeof payload.title === "string" ? payload.title : "PDF document",
      page: Math.max(1, Number.parseInt(payload.page, 10) || 1),
      terms: validTerms(payload.terms), rect: rectangle,
      mainHits: validMainHits(payload.mainHits),
      suppressedPopupIds: payload.suppressedPopupIds || {},
      hasSelection: payload.hasSelection === true };
    updateDocumentTitle(active.title || "PDF document");
    resetMainHighlights();
    requestedMatch = matchRequest(payload.match);
    if (pdfDocument && ready && oldUrl === active.url) {
      applySelection();
      // The host can reveal the existing surface immediately. Debounced
      // progress reports still follow as highlighting/rendering settles.
      report("state", diagnosticState());
      return diagnosticState();
    }
    // Find belongs to the current document. A different paper starts with its
    // library-result terms instead of retaining an unexecuted old Find query.
    clearTimeout(findTimer);
    inPdfFind = false;
    $("findInput").value = "";
    $("findbar").hidden = true;
    $("findToggle").setAttribute("aria-expanded", "false");
    ready = false;
    // Detach the old document before awaiting its asynchronous destruction.
    // Otherwise an old pagesinit can arrive during that await, consume the new
    // generation's pendingOpen, and leave the replacement permanently blank.
    pendingOpen = null;
    pendingMatch = null;
    missingMainMatchPage = null;
    matchCount = { current: 0, total: 0 };
    $("loading").hidden = false;
    $("empty").hidden = true;
    updateControls();
    const previousTask = loadingTask;
    loadingTask = null;
    viewer.setDocument(null);
    linkService.setDocument(null);
    pdfDocument = null;
    rawPageText = new Map();
    suppressedPopups = new Set();
    if (previousTask) await previousTask.destroy();
    if (token !== generation) return;
    const task = loadingTask = pdfjsLib.getDocument({
      url: active.url,
      cMapUrl: new URL("../pdfjs/cmaps/", import.meta.url).href, cMapPacked: true,
      standardFontDataUrl: new URL("../pdfjs/standard_fonts/", import.meta.url).href,
      wasmUrl: new URL("../pdfjs/wasm/", import.meta.url).href,
      enableXfa: false, isEvalSupported: false, stopAtErrors: false,
    });
    task.onPassword = () => {
      if (token !== generation) return;
      passwordRejected = true;
      showError("This PDF is password protected. Open it in your default PDF app to unlock it.");
      task.destroy().catch(() => {});
    };
    const loaded = await task.promise;
    if (token !== generation) { await loaded.destroy(); return; }
    pdfDocument = loaded;
    normalizeImportedPopups(pdfDocument, active.suppressedPopupIds);
    linkService.setDocument(pdfDocument, null);
    pendingOpen = token;
    viewer.setDocument(pdfDocument);
    return { id: active.id, loading: true };
  } catch (error) {
    if (token === generation && !passwordRejected) showError(error?.message || "This PDF could not be opened.");
    return diagnosticState();
  }
}

function showError(message) {
  endPan();
  setPanReady(false);
  ready = false;
  $("loading").hidden = true;
  $("empty").hidden = false;
  $("empty").firstElementChild.textContent = message;
  updateControls();
  report("error", { message, fatal: true });
}

async function clear(message = "Select a paper or note to read its PDF.", id = null) {
  endPan();
  setPanReady(false);
  ++generation;
  active = id === null ? null : { id };
  pendingMatch = null;
  missingMainMatchPage = null;
  requestedMatch = { index: 0 };
  matchCount = { current: 0, total: 0 };
  findStatus = 0;
  lastWarning = "";
  ready = false;
  pendingOpen = null;
  inPdfFind = false;
  $("findbar").hidden = true;
  $("findToggle").setAttribute("aria-expanded", "false");
  $("findInput").value = "";
  updateDocumentTitle("");
  $("empty").firstElementChild.textContent = String(message);
  $("empty").hidden = false;
  $("loading").hidden = true;
  viewer.setDocument(null);
  linkService.setDocument(null);
  pdfDocument = null;
  rawPageText = new Map();
  resetMainHighlights();
  suppressedPopups = new Set();
  if (loadingTask) { const task = loadingTask; loadingTask = null; await task.destroy().catch(() => {}); }
  updateControls();
  reportState();
  return diagnosticState();
}

function setFindVisible(visible) {
  if (visible && !ready) return;
  clearTimeout(findTimer);
  $("findbar").hidden = !visible;
  $("findToggle").setAttribute("aria-expanded", String(visible));
  updateControls();
  if (visible) {
    $("findInput").focus();
    $("findInput").select();
    if ($("findInput").value) findInPdf();
  }
  else { useLibraryTerms(); $("viewerContainer").focus(); }
}

function findInPdf(type = "", previous = false) {
  clearTimeout(findTimer);
  findTimer = null;
  const query = $("findInput").value;
  if (!query) { useLibraryTerms(); return; }
  inPdfFind = true;
  updateSearchAuthority();
  viewer.currentScaleValue = defaultScale();
  $("viewerContainer").scrollLeft = 0;
  missingMainMatchPage = null;
  pendingMatch = null;
  runFind(query, type, previous);
}

eventBus.on("pagesinit", () => {
  if (pendingOpen !== generation || !pdfDocument) return;
  ready = true;
  pendingOpen = null;
  viewer.currentScaleValue = defaultScale();
  applySelection();
  report("state", diagnosticState());
  reportState();
});
eventBus.on("pagechanging", () => { updateControls(); reportState(); });
eventBus.on("scalechanging", updateScale);
eventBus.on("pagerendered", event => {
  if (event.error) reportWarning(event.error.message || String(event.error));
  reportState();
});
eventBus.on("textlayerrendered", () => { applyPendingMatch(); reportState(); });
eventBus.on("annotationlayerrendered", reportState);
eventBus.on("updatetextlayermatches", () => { queueMicrotask(applyPendingMatch); });
eventBus.on("updatefindmatchescount", event => {
  if (inPdfFind) matchCount = event.matchesCount;
  applyPendingMatch();
  updateMatches();
});
eventBus.on("updatefindcontrolstate", event => {
  findStatus = event.state;
  if (inPdfFind) matchCount = event.matchesCount;
  applyPendingMatch();
  if (ready && !inPdfFind && missingMainMatchPage !== null) keepMainResultPage(missingMainMatchPage);
  updateMatches();
});

$("previousPage").addEventListener("click", () => { viewer.currentPageNumber = Math.max(1, viewer.currentPageNumber - 1); });
$("nextPage").addEventListener("click", () => { viewer.currentPageNumber = Math.min(pdfDocument.numPages, viewer.currentPageNumber + 1); });
function goToEnteredPage() {
  if (!ready) return;
  const page = Number.parseInt($("pageNumber").value, 10);
  if (Number.isFinite(page)) viewer.currentPageNumber = Math.min(Math.max(page, 1), pdfDocument.numPages);
  updateControls();
}
$("pageNumber").addEventListener("change", goToEnteredPage);
$("pageNumber").addEventListener("keydown", event => {
  if (event.key === "Enter") { goToEnteredPage(); $("viewerContainer").focus(); }
});
function zoomBy(factor) {
  if (!ready) return;
  viewer.currentScale = Math.min(5, Math.max(.1, viewer.currentScale * factor));
}
$("zoomIn").addEventListener("click", () => zoomBy(1.2));
$("zoomOut").addEventListener("click", () => zoomBy(1 / 1.2));
$("zoom").addEventListener("change", () => {
  if (ready && $("zoom").value !== "custom") viewer.currentScaleValue = $("zoom").value;
});
$("findToggle").addEventListener("click", () => setFindVisible($("findbar").hidden));
$("findClose").addEventListener("click", () => setFindVisible(false));
$("findInput").addEventListener("input", () => { clearTimeout(findTimer); findTimer = setTimeout(() => findInPdf(), 120); });
$("findInput").addEventListener("keydown", event => {
  if (event.key === "Enter") { event.preventDefault(); clearTimeout(findTimer); findInPdf("again", event.shiftKey); }
});
$("findPrevious").addEventListener("click", () => findInPdf("again", true));
$("findNext").addEventListener("click", () => findInPdf("again"));
$("backToSelection").addEventListener("click", () => {
  if (!ready || !active?.hasSelection) return;
  jumpToSelection();
  restoreMainSearch();
});

document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
    event.preventDefault(); if (ready) setFindVisible(true);
  } else if (event.key === "Escape" && !$("findbar").hidden) {
    event.preventDefault(); clearTimeout(findTimer); setFindVisible(false);
  } else if ((event.ctrlKey || event.metaKey) && ["+", "=", "-", "0"].includes(event.key)) {
    event.preventDefault();
    if (event.key === "0" && ready) viewer.currentScaleValue = defaultScale();
    else zoomBy(event.key === "-" ? 1 / 1.2 : 1.2);
  }
});
$("viewerContainer").addEventListener("wheel", event => {
  if (event.ctrlKey || event.metaKey) {
    event.preventDefault(); zoomBy(event.deltaY < 0 ? 1.1 : 1 / 1.1);
  }
}, { passive: false });

// Ctrl reserves a viewport gesture even when it starts on a PDF link. Capture
// it before annotation-link handlers; plain clicks still follow PDF links and
// plain dragging remains text selection.
const viewport = $("viewerContainer");
function resetView() {
  if (!ready) return;
  endPan();
  const page = viewer.currentPageNumber;
  viewer.currentScaleValue = defaultScale();
  // Reset the viewport around the current page rather than unexpectedly
  // sending a reader who browsed away back to the selected search result.
  viewer.scrollPageIntoView({ pageNumber: page });
  viewport.scrollLeft = 0;
  reportState();
}
viewport.addEventListener("dblclick", event => {
  if (!ready || !event.ctrlKey || event.button !== 0 ||
      event.target.closest("button, input, select, textarea, [contenteditable=true]")) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  window.getSelection()?.removeAllRanges();
  resetView();
}, true);
function setPanReady(value) {
  viewport.classList.toggle("pan-ready", !!value && ready);
}
function endPan(event) {
  if (!pan || (event?.pointerId !== undefined && event.pointerId !== pan.pointerId)) return;
  const pointerId = pan.pointerId;
  pan = null;
  suppressLinkClickUntil = performance.now() + 500;
  viewport.classList.remove("panning");
  if (viewport.hasPointerCapture(pointerId)) viewport.releasePointerCapture(pointerId);
  reportState();
}
viewport.addEventListener("pointerdown", event => {
  if (!event.ctrlKey) suppressLinkClickUntil = 0;
  if (!ready || event.button !== 0 || !event.ctrlKey ||
      event.target.closest("button, input, select, textarea, [contenteditable=true]")) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  suppressLinkClickUntil = performance.now() + 1000;
  setPanReady(true);
  pan = { pointerId: event.pointerId, x: event.clientX, y: event.clientY,
    left: viewport.scrollLeft, top: viewport.scrollTop };
  viewport.classList.add("panning");
  viewport.setPointerCapture(event.pointerId);
}, true);
viewport.addEventListener("pointermove", event => {
  setPanReady(event.ctrlKey);
  if (!pan || event.pointerId !== pan.pointerId) return;
  if (!(event.buttons & 1)) { endPan(); return; }
  event.preventDefault();
  viewport.scrollLeft = pan.left - (event.clientX - pan.x);
  viewport.scrollTop = pan.top - (event.clientY - pan.y);
});
viewport.addEventListener("pointerup", endPan);
viewport.addEventListener("pointercancel", endPan);
viewport.addEventListener("lostpointercapture", endPan);
viewport.addEventListener("dragstart", event => {
  if (pan || event.ctrlKey) { event.preventDefault(); event.stopImmediatePropagation(); }
}, true);
document.addEventListener("click", event => {
  if (!viewport.contains(event.target)) return;
  if (event.ctrlKey || performance.now() < suppressLinkClickUntil) {
    event.preventDefault();
    event.stopImmediatePropagation();
  }
}, true);
document.addEventListener("keydown", event => {
  if (event.key === "Control") setPanReady(true);
});
document.addEventListener("keyup", event => {
  if (event.key === "Control") { endPan(); setPanReady(false); }
});
window.addEventListener("blur", () => { endPan(); setPanReady(false); });

// The component's own observer updates its height CSS variable; the full
// Firefox viewer normally reapplies fit presets separately on window resize.
// Do that here for pane drags, expand/restore, and the Find toolbar as well.
let resizeFrame = null;
const containerObserver = new ResizeObserver(() => {
  if (resizeFrame !== null) cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null;
    if (!ready) return;
    const preset = viewer.currentScaleValue;
    if (preset === "page-width" || preset === "page-fit") viewer.currentScaleValue = preset;
    else viewer.update();
    reportState();
  });
});
containerObserver.observe($("viewerContainer"));

// Intercept PDF external links before the browser navigates. Named/internal PDF
// destinations retain PDFLinkService's own click handlers.
document.addEventListener("click", event => {
  const anchor = event.target.closest?.("a[href]");
  if (!anchor || anchor.closest("[data-internal-link]")) return;
  const href = anchor.getAttribute("href");
  if (!href || href.startsWith("#")) return;
  let target;
  try { target = new URL(href, location.href); } catch { target = null; }
  if (target?.origin === location.origin && target.pathname === location.pathname && target.hash) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if (event.isTrusted && target && ["http:", "https:"].includes(target.protocol)) report("link", { url: target.href });
}, true);

window.NotableReader = {
  open, clear, setTitle,
  selectMatch(value) {
    if (!active?.url) return false;
    const request = value && typeof value === "object" ? value : { index: value };
    requestedMatch = matchRequest(request);
    let hitsChanged = false;
    if (Array.isArray(request.mainHits) && JSON.stringify(request.mainHits) !== JSON.stringify(active.mainHits)) {
      active.mainHits = validMainHits(request.mainHits);
      hitsChanged = true;
    }
    if (!ready) return false;
    // Staying in main-search mode only changes the selected occurrence. Avoid
    // restarting Find, clearing all highlights and remapping the same result.
    if (inPdfFind || !$("findbar").hidden || hitsChanged) restoreMainSearch();
    requestedMatch.fitWidth = true;
    pendingMatch = { page: active.page, ...requestedMatch };
    requestedMatch.fitWidth = false;
    return applyPendingMatch();
  },
  resetView,
  setExpanded(value) {
    const next = !!value;
    if (next === expanded) return;
    if (next) {
      readingSnapshot = captureView();
      expanded = true;
      if (ready) viewer.currentScaleValue = "1.25";
    } else {
      const current = captureView();
      expanded = false;
      if (current) restoreView({ ...current, scaleValue:
        readingSnapshot?.url === active?.url ? readingSnapshot.scaleValue : "page-width" });
      readingSnapshot = null;
    }
    reportState();
  },
  state: diagnosticState,
};

window.addEventListener("pywebviewready", () => report("ready"), { once: true });
// Browser layout warnings and a failed individual page must not hide an
// otherwise readable document. Only explicit document-opening failures above
// are fatal; keep these diagnostics available to the host without blanking it.
window.addEventListener("error", event => reportWarning(event.message || "PDF reader error."));
window.addEventListener("unhandledrejection", event => reportWarning(event.reason?.message || String(event.reason)));
updateControls();
if (window.pywebview?.api) report("ready");
