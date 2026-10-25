/* Zotero owns this interface and the lifetime of the bundled worker. */
var NotableUI = {
  // Display names may change; the extension ID, profile directory, API paths
  // and managed-attachment markers must keep their existing identities.
  name: 'reMarkable Sync for Zotero', shortName: 'reMarkable Sync',
  id: 'notable-companion@local.invalid', process: null, pending: new Map(), serial: 0,
  view: null, latest: null, busy: false, timer: null, windows: new Set(),
  filingQueue: [], reviewDrafts: new Map(), tagDrafts: new Map(), linkDrafts: new Map(),
  async start(rootURI) {
    this.stopped = false;
    this.rootURI = rootURI;
    Zotero.Notable = this;
    this.readerToolbar = ({reader, doc, append}) => {
      if (reader.type !== 'pdf') return;
      const button = doc.createElement('button');
      button.textContent = 'Tag this page'; button.className = 'notable-page-tag';
      button.style.cssText = 'display: inline-flex; align-items: center; gap: 6px; margin-inline: 8px; padding: 4px 8px;';
      const icon = doc.createElement('span');
      icon.setAttribute('aria-hidden', 'true');
      icon.style.cssText = 'display: inline-block; width: 16px; height: 16px; flex: 0 0 16px; background: currentColor; mask: url("chrome://notable/content/icons/tag.svg") center / contain no-repeat;';
      button.prepend(icon);
      button.title = 'Paper and page tags shared with reMarkable';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try { await this.openPageTags(reader); }
        catch (error) { reader._iframeWindow.alert(error.message); }
        finally { button.disabled = false; }
      });
      append(button);
    };
    Zotero.Reader.registerEventListener('renderToolbar', this.readerToolbar, this.id);
    this.collectionObserver = Zotero.Notifier.registerObserver({notify: (event, type) => {
      if (type === 'collection') this.refreshCollectionNames();
    }}, ['collection'], this.id);
    this.statePath = PathUtils.join(Zotero.Profile.dir, 'notable');
    await IOUtils.makeDirectory(this.statePath, {ignoreExisting: true});
    const queuePath = PathUtils.join(this.statePath, 'filing-queue.json');
    if (await IOUtils.exists(queuePath)) {
      try {
        const saved = JSON.parse(await IOUtils.readUTF8(queuePath));
        if (!Array.isArray(saved.jobs) || saved.jobs.some(job => !this.validFilingJob(job))
          || new Set(saved.jobs.map(job => job.id)).size !== saved.jobs.length) throw Error('Invalid filing queue');
        this.filingQueue = saved.jobs;
        // Restoring approvals never starts transfers without a visible resume.
        this.filingQueuePaused = !!saved.jobs.length;
      } catch (_) { this.queueError = 'The saved filing queue could not be read. Your documents remain in Review.'; }
    }
    for (const target of ['main/menubar/tools', 'main/library/item']) {
      Zotero.MenuManager.registerMenu({menuID: 'notable-' + target.replaceAll('/', '-'), pluginID: this.id, target,
        menus: [{menuType: 'menuitem', onShowing: (event, context) => { context.menuElem.setAttribute('label', this.name + '…'); },
          onCommand: () => this.open()}]});
    }
    // Startup is awaited while Zotero initializes plugins, before its first
    // normal window can finish loading. Do not block that chain on UI ready.
    Zotero.uiReadyPromise.then(async () => {
      if (this.stopped) return;
      for (const window of Zotero.getMainWindows()) this.attach(window);
      if (await IOUtils.exists(PathUtils.join(this.statePath, 'config.json'))) {
        this.refresh().then(() => this.schedule()).catch(() => {});
      }
    });
  },
  attach(window) {
    if (this.stopped) return;
    if (this.windows.has(window)) return;
    const toolbar = window.document.getElementById('zotero-tabs-toolbar');
    if (!toolbar) return;
    const button = window.document.createXULElement('toolbarbutton');
    button.id = 'notable-open'; button.setAttribute('label', 'reMarkable');
    button.setAttribute('aria-label', 'Open reMarkable Sync');
    button.style.cssText = 'margin-inline: 8px; padding-inline: 8px; list-style-image: url("chrome://notable/content/icons/tablet.svg");';
    button.setAttribute('tooltiptext', 'Open reMarkable Sync — folders, review, and settings');
    button.addEventListener('command', () => this.open());
    toolbar.appendChild(button); this.windows.add(window);
  },
  detach(window) { window.document.getElementById('notable-open')?.remove(); this.windows.delete(window); },
  async stop() {
    this.stopped = true;
    Zotero.Reader.unregisterEventListener('renderToolbar', this.readerToolbar);
    if (this.collectionObserver) Zotero.Notifier.unregisterObserver(this.collectionObserver);
    this.collectionObserver = null;
    for (const reader of Zotero.Reader._readers) reader._iframeWindow?.document.querySelectorAll('.notable-page-tag').forEach(node => node.remove());
    clearTimeout(this.timer);
    clearInterval(this.activityTimer);
    this.reviewObserver?.disconnect();
    this.view?.close(); this.view = null;
    for (const window of this.windows) this.detach(window);
    for (const target of ['main-menubar-tools', 'main-library-item']) Zotero.MenuManager.unregisterMenu('notable-' + target);
    // A launch which is already awaiting Subprocess.call must observe stopped
    // and finish its child before replacement can create another writer.
    if (this.launching) { try { await this.launching; } catch (_) {} }
    if (this.process) await this.closeProcess(this.process);
    for (const value of this.pending.values()) { clearTimeout(value.timer); value.reject(new Error(this.shortName + ' stopped')); }
    this.pending.clear();
    if (Zotero.Notable === this) delete Zotero.Notable;
  },
  async closeProcess(process, graceful = true) {
    let timeout;
    try {
      if (graceful) {
        await Promise.race([(async () => {
          await process.stdin.write(JSON.stringify({method: 'shutdown'}) + '\n');
          await process.wait();
        })(), new Promise(resolve => { timeout = setTimeout(resolve, 5000); })]);
      }
      // Mozilla's existing Subprocess API waits for process exit; on Windows
      // kill() terminates immediately. Never release a writer before exit.
      await process.kill();
      if (this.process === process) { this.process = null; this.processError = ''; }
    } catch (error) {
      if (this.process === process) this.processError = 'The previous helper could not be stopped. Restart Zotero before retrying.';
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  },
  async launch() {
    if (this.stopped) throw new Error(this.shortName + ' is closed.');
    if (this.process) return;
    Zotero.Prefs.set('httpServer.enabled', true);
    Zotero.Prefs.set('httpServer.localAPI.enabled', true);
    await Zotero.Server.init();
    const {Subprocess} = ChromeUtils.importESModule('resource://gre/modules/Subprocess.sys.mjs');
    let command, args;
    // A test harness can override the private transport in its disposable
    // profile. This is deliberately absent from all user setup controls.
    const development = Zotero.Prefs.get('notable.developmentWorker', true);
    if (development) {
      const value = JSON.parse(development); command = value.command; args = value.arguments;
    } else {
      let manifest;
      try { manifest = await (await fetch(this.rootURI + 'runtime-manifest.json')).json(); }
      catch (_) { throw new Error('This development build has no bundled helper. Install the complete ' + this.name + ' package.'); }
      const directory = PathUtils.join(this.statePath, 'runtime', manifest.id);
      const marker = PathUtils.join(directory, 'ready.json');
      const executable = PathUtils.join(directory, 'notable-worker.exe');
      const executableManifest = manifest.files.find(file => file.path === 'notable-worker.exe');
      for (const file of manifest.files) {
        if (file.path.includes('..') || file.path.startsWith('/') || file.path.includes('\\')) throw new Error('Invalid packaged runtime path');
      }
      // A directory runtime also depends on its DLLs and models. A ready
      // marker must not hide a member removed or changed after extraction.
      let healthy = !this.repairRuntime && !!executableManifest && await IOUtils.exists(marker);
      if (healthy) for (const file of manifest.files) {
        const destination = PathUtils.join(directory, ...file.path.split('/'));
        if (!await IOUtils.exists(destination) || await Zotero.Utilities.Internal.md5Async(destination) !== file.md5) {
          healthy = false; break;
        }
      }
      if (!healthy) {
        this.message('Preparing or repairing the bundled helper…');
        for (const file of manifest.files) {
          const destination = PathUtils.join(directory, ...file.path.split('/'));
          await IOUtils.makeDirectory(PathUtils.parent(destination), {ignoreExisting: true});
          const response = await fetch(this.rootURI + 'runtime/' + file.path);
          if (!response.ok) throw new Error('The bundled helper is incomplete. Reinstall ' + this.shortName + '.');
          await IOUtils.write(destination, new Uint8Array(await response.arrayBuffer()));
          if (await Zotero.Utilities.Internal.md5Async(destination) !== file.md5) throw new Error('A helper file failed verification. Reinstall ' + this.shortName + '.');
        }
        await IOUtils.writeUTF8(marker, JSON.stringify({id: manifest.id}));
        this.repairRuntime = false;
      }
      command = PathUtils.join(directory, 'notable-worker.exe'); args = [];
    }
    this.message('Starting the background helper…');
    if (this.stopped) throw new Error(this.shortName + ' is closed.');
    const diagnostics = Zotero.Prefs.get('notable.testDiagnostics', true) ? ['--debug-stacks'] : [];
    // PyMuPDF caches its message stream at import, before per-request redirects.
    const process = await Subprocess.call({command, arguments: [...args, '--state', this.statePath, '--port', String(Zotero.Server.port), ...diagnostics],
      stderr: 'pipe', environmentAppend: true, environment: {PYTHONUNBUFFERED: '1', PYTHONDONTWRITEBYTECODE: '1', PYMUPDF_MESSAGE: 'fd:2'}});
    this.process = process;
    if (this.stopped) { await this.closeProcess(process); throw new Error(this.shortName + ' is closed.'); }
    // Drain diagnostics without logging paper contents or credentials.
    (async () => { try { while (await process.stderr.readString()) {} } catch (_) {} })();
    (async () => {
      let buffer = '', failure = 'The background helper stopped. Retry your action to restart it.';
      try {
        while (true) {
          const chunk = await process.stdout.readString(); if (!chunk) break;
          buffer += chunk;
          let boundary;
          while ((boundary = buffer.indexOf('\n')) !== -1) {
            const line = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 1);
            const response = JSON.parse(line);
            if (response.event === 'progress') { this.touchRequests(); this.receiveProgress(response); continue; }
            const pending = this.pending.get(response.id);
            if (!pending) continue;
            this.pending.delete(response.id);
            clearTimeout(pending.timer);
            if (response.error) pending.reject(new Error(response.error.message)); else pending.resolve(response.result);
          }
        }
      } catch (error) {
        if (error instanceof SyntaxError) failure = 'The background helper sent an invalid response. Retry your action to restart it.';
      }
      try { await this.closeProcess(process, false); } catch (_) {}
      this.rejectProcessRequests(process, this.processError || failure);
    })();
  },
  async rpc(method, params = {}) {
    if (this.stopped) throw new Error(this.shortName + ' is closed.');
    if (this.processError) throw new Error(this.processError);
    if (!this.process) {
      if (!this.launching) this.launching = this.launch().finally(() => { this.launching = null; });
      await this.launching;
    }
    if (this.stopped || !this.process) throw new Error(this.shortName + ' is closed.');
    const id = ++this.serial;
    const answer = new Promise((resolve, reject) => this.pending.set(id, {resolve, reject, process: this.process}));
    this.touchRequests();
    try { await this.process.stdin.write(JSON.stringify({id, method, params}) + '\n'); }
    catch (error) { clearTimeout(this.pending.get(id)?.timer); this.pending.delete(id); throw error; }
    return answer;
  },
  touchRequests() {
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.timer = setTimeout(async () => {
        const process = request.process;
        if (process) { try { await this.closeProcess(process, false); } catch (_) {} }
        this.rejectProcessRequests(process, this.processError || 'The helper stopped responding and was stopped safely. Retry your action to restart it.');
      }, this.requestTimeout || 600000);
    }
  },
  rejectProcessRequests(process, message) {
    for (const [id, pending] of this.pending) if (pending.process === process) {
      clearTimeout(pending.timer); this.pending.delete(id); pending.reject(new Error(message));
    }
  },
  async refresh() {
    this.latest = await this.rpc('status'); this.refreshCollectionNames(); this.badge(); return this.latest;
  },
  refreshCollectionNames() {
    if (!this.latest || this.stopped) return;
    // Read Zotero's current collection objects, using stable keys for every
    // connection. Renaming a collection changes labels, never the binding.
    const collections = Zotero.Collections.getByLibrary(Zotero.Libraries.userLibraryID, true)
      .map(row => ({key: row.key, name: row.name, parentCollection: row.parentKey || false}));
    this.latest.collections = collections;
    this.collectionsCurrent = true;
    if (this.folderCatalog) this.folderCatalog.collections = collections;
    const paths = new Map(this.paths(collections, 'key', 'parentCollection', 'name'));
    const root = paths.get(this.latest.config?.zotero_root);
    if (root) this.latest.config.zotero_path = root;
    if (!this.view || this.view.closed) return;
    const doc = this.view.document;
    for (const select of doc.querySelectorAll('select[data-zotero-collections]')) {
      const choices = [...paths].filter(([key]) => select.dataset?.zoteroCollections !== 'research' || !this.latest.mappings?.[key]);
      const empty = [...select.options].filter(option => !option.value).map(option => ['', option.textContent]);
      this.reconcileOptions(select, [...empty, ...choices]);
    }
    for (const select of doc.querySelectorAll('select[data-folder-destination]')) select.notableRefreshNames();
    const label = doc.getElementById('notable-connected-zotero');
    if (label && root) label.textContent = 'Zotero: ' + root;
  },
  reconcileOptions(select, choices) {
    const selected = new Set([...select.options].filter(option => option.selected || option.value === select.value).map(option => option.value));
    if (choices.length === select.options.length && choices.every(([key], index) => select.options[index].value === key)) {
      choices.forEach(([, label], index) => { select.options[index].textContent = label; }); return;
    }
    select.replaceChildren();
    for (const [key, label] of choices) {
      const option = this.el('option', label, select, {value: key}); option.selected = selected.has(key);
    }
    if (!select.multiple && !choices.some(([key]) => selected.has(key))) select.value = '';
  },
  receiveProgress(response) {
    this.message(response.message);
    if (!this.latest || !Array.isArray(response.links)) return;
    const previous = new Map((this.latest.links || []).map(row => [row.cloud, row]));
    this.latest.links = response.links.map(row => ({...previous.get(row.cloud), ...row, unavailable: !!row.unavailable}));
    const available = this.latest.links.filter(row => !row.unavailable);
    if (this.latest.connection) this.latest.connection.linked_papers = available.length;
    if (this.latest.filing_summary) {
      this.latest.filing_summary.linked = available.length;
      this.latest.filing_summary.pdfs_received = available.filter(row => row.revision).length;
    }
    if (this.view && !this.view.closed) {
      const summary = this.view.document.getElementById('notable-paper-status');
      if (summary) summary.textContent = this.paperStatusMessage();
    }
    // A link can be committed before a long sync ends. Keep that list live
    // without replacing an in-progress review form or issuing queued RPCs.
    if (this.view && !this.view.closed && this.tab === 'links') {
      const focus = this.captureFocus();
      const content = this.view.document.querySelector('main');
      if (content) { content.replaceChildren(); this.renderLinks(content); this.disable(this.busy); this.restoreFocus(focus); }
    }
  },
  isQueueMessage(issue) { return /^Review (the filename|this new tablet document)/.test(issue.reason || ''); },
  paperStatusMessage() {
    const queued = this.queuedReviewIds(), reviews = (this.latest?.reviews || []).filter(row => !queued.has(row.id)).length;
    const saved = queued.size ? ` · ${queued.size} decisions saved in filing queue` : '';
    const linked = (this.latest?.links || []).filter(row => !row.unavailable).length;
    if (this.operation?.method === 'sync') return `${reviews} need review${saved} · ${linked} linked so far`;
    const waiting = this.latest?.filing_summary?.approved_waiting_sync;
    return `${reviews} need review${saved}${waiting == null ? '' : ` · ${waiting} approved, waiting for sync`} · ${linked} linked`;
  },
  statusMessage() {
    if (!this.latest?.config?.tablet_root && this.latest?.status?.state === 'setup_required') {
      return 'No folder connected. Choose your folders in Setup; syncing is off.';
    }
    const issues = this.latest?.status?.result?.review || [];
    const pending = this.latest?.reviews?.length || 0;
    if (pending && ((issues.length && issues.every(issue => this.isQueueMessage(issue))) || !this.latest?.status?.message)) {
      return `${pending} documents waiting in Review. Approve their filing here, then use Sync now to transfer PDFs and tablet notes.`;
    }
    return this.latest?.status?.message || 'Ready';
  },
  badge() {
    const count = (this.latest?.reviews || []).filter(row => !row.payload.routine).length
      + (this.latest?.bulk?.rows || []).filter(row => row.issues.length && row.status !== 'dismissed').length
      + (this.latest?.deletions?.length || 0) + (this.latest?.local_deletions?.length || 0);
    const attention = this.latest?.status?.state === 'needs_attention';
    for (const window of this.windows) window.document.getElementById('notable-open')?.setAttribute('label', 'reMarkable' + (count ? ` (${count})` : attention ? ' (!)' : ''));
  },
  schedule() {
    clearTimeout(this.timer); this.timer = null;
    if (this.automaticAllowed()) this.timer = setTimeout(async () => {
      // Recheck when the timer fires: opening a window must win a timer race.
      if (this.automaticAllowed()) { try { await this.action('sync', {automatic: true}, false); } catch (_) {} }
      this.schedule();
    }, Math.min(900000, 300000 * 2 ** Math.min(this.failures || 0, 2)));
  },
  workspaceOpen() { return !!this.workspaceOpening || !!(this.view && !this.view.closed); },
  automaticAllowed() {
    return !this.stopped && !this.workspaceOpen() && !this.busy && !this.pausing && !this.changingFolder && !this.filingQueue.length && !this.drainingFilings
      && !this.setupDirty && !!this.latest?.config?.tablet_root && !this.latest.config.sync_paused && !!this.latest.config.automatic;
  },
  async yieldBackground() {
    if (!this.operation?.automatic || this.operation.stopping) return;
    this.operation.stopping = true;
    this.message('Finishing the background check so you can use the workspace…');
    // A transient cancellation keeps the user's automatic-sync preference.
    // The existing worker transport acknowledges it through the running job.
    try { await this.process?.stdin.write(JSON.stringify({method: 'cancel'}) + '\n'); }
    catch (error) { this.message(error.message, true); }
  },
  async yieldSyncForFiling() {
    if (this.launching) { try { await this.launching; } catch (_) { return; } }
    const operation = this.operation;
    if (operation?.method !== 'sync' || operation.stopping || this.pausing || !this.process) return;
    // Approvals have already been saved before asking the single writer to
    // yield. Transient cancel stops at its existing safe boundary; it does
    // not change automatic-sync settings or start another sync afterwards.
    operation.stopping = true; operation.yielding = true;
    this.message('Finishing the current paper so your filing can run…');
    try { await this.process.stdin.write(JSON.stringify({method: 'cancel'}) + '\n'); }
    catch (error) { this.message(error.message, true); }
  },
  canSync() { return !!this.latest?.config?.tablet_root && !this.changingFolder && !this.setupDirty && !this.disconnectPreview && !this.pausing; },
  async pauseSync() {
    if (this.pausing) return;
    this.filingQueuePaused = true;
    try { await this.saveFilingQueue(); } catch (_) { this.queueError = 'The queue could not be saved. Sync is being paused.'; }
    this.pausing = true; clearTimeout(this.timer);
    if (this.operation) { this.operation.stopping = true; this.operation.yielding = false; }
    if (this.latest?.config) this.latest.config.sync_paused = true;
    this.disable(this.busy);
    try {
      this.latest = await this.rpc('pause_sync'); this.badge();
      if (this.view && !this.view.closed) this.render();
    } catch (error) { this.message(error.message, true); throw error; }
    finally { this.pausing = false; this.disable(this.busy); }
  },
  clearFolderEditor() {
    this.changingFolder = false; this.setupDirty = false; this.setupDraft = null;
    this.folderPreview = null; this.disconnectPreview = null;
    this.tagEditor = null; this.tagResults = null; this.selected = null;
  },
  open() {
    if (this.view && !this.view.closed) { this.view.focus(); return; }
    this.workspaceOpening = true; clearTimeout(this.timer); this.yieldBackground();
    this.view = Zotero.getMainWindow().openDialog('chrome://notable/content/workspace.xhtml', 'notable-workspace',
      'chrome,dialog=no,resizable,centerscreen,width=1040,height=760', {controller: this});
  },
  async openPageTags(reader) {
    const state = reader._internalReader?._state;
    const page = (state?.primary !== false ? state?.primaryViewStats : state?.secondaryViewStats)?.pageIndex;
    if (!Number.isInteger(page)) throw new Error('Wait for this PDF page to finish loading.');
    const item = await Zotero.Items.getAsync(reader.itemID);
    if (!item?.isPDFAttachment()) throw new Error('Choose a PDF first.');
    this.requestedTab = 'tags'; this.open(); await this.yieldBackground();
    const context = await this.rpc('tag_context', {key: item.key, page});
    this.tagEditor = context; this.requestedTab = 'tags';
    if (this.view?.document.getElementById('app')?.querySelector('h1')) { this.tab = 'tags'; this.render(); }
  },
  async action(method, params = {}, render = true) {
    if (method === 'sync' && params.automatic && !this.automaticAllowed()) return;
    if (this.busy) return;
    clearTimeout(this.timer);
    this.busy = true;
    const labels = {sync: 'Syncing with reMarkable', scan_library: 'Scanning your Windows library',
      suggest_paper_tags: 'Finding paper keywords and tag suggestions', save_paper_tags: 'Saving your paper-tag choices',
      import_library: 'Importing papers into Zotero', approve_routine: 'Filing the selected papers',
      approve: 'Filing this paper', reindex: 'Rebuilding the search index', folders: 'Loading folders'};
    this.operation = {method, automatic: !!params.automatic, title: labels[method] || 'Updating your setup',
      started: Date.now(), updated: Date.now(), detail: 'Starting…'};
    this.message('Starting…');
    this.disable(true);
    try {
      const connection = this.filingConnection();
      const result = await this.rpc(method, params);
      this.failures = 0;
      this.latest = result.reviews ? result : await this.rpc('status');
      this.refreshCollectionNames();
      if (connection !== this.filingConnection()) {
        this.reviewDrafts.clear(); this.tagDrafts.clear(); this.linkDrafts.clear(); this.batchCollection = null; this.selected = null;
      }
      this.badge(); if (render && this.view && !this.view.closed) this.render();
      this.message(this.statusMessage()); return result;
    } catch (error) {
      this.failures = (this.failures || 0) + 1;
      if (this.latest) this.latest.status = {state: 'needs_attention', message: error.message};
      this.badge(); this.message(error.message, true); throw error;
    }
    finally {
      this.busy = false; this.operation = null; this.disable(false); this.updateActivity(); this.schedule();
      if (this.filingQueue.length && !this.drainingFilings) this.drainFilings().catch(error => this.message(error.message, true));
    }
  },
  filingConnection() {
    const config = this.latest?.config || {};
    return JSON.stringify([config.connection_id || 'legacy', config.zotero_root, config.tablet_root]);
  },
  saveFilingQueue() {
    const path = PathUtils.join(this.statePath, 'filing-queue.json');
    // Snapshot only after earlier writes and their rollback continuations have
    // settled; a queued write must never resurrect a rejected approval.
    this.queueSave = (this.queueSave || Promise.resolve()).catch(() => {}).then(() => IOUtils.writeUTF8(path,
      JSON.stringify({jobs: this.filingQueue, paused: !!this.filingQueuePaused}), {tmpPath: path + '.tmp'}));
    return this.queueSave;
  },
  validFilingJob(job) {
    const text = value => typeof value === 'string' && value.length > 0;
    if (!job || typeof job !== 'object' || !text(job.id) || !text(job.connection)
      || !['approve', 'approve_routine'].includes(job.method) || !job.params || typeof job.params !== 'object' || Array.isArray(job.params)) return false;
    const params = job.params;
    if (job.title != null && typeof job.title !== 'string') return false;
    if (params.research != null && (!Array.isArray(params.research) || params.research.some(key => !text(key)))) return false;
    return job.method === 'approve' ? text(params.identity) && text(params.digest)
      : text(params.collection) && Array.isArray(params.entries) && params.entries.length > 0
        && params.entries.every(row => row && text(row.id) && text(row.digest))
        && new Set(params.entries.map(row => row.id)).size === params.entries.length;
  },
  changeFilingQueue(change) {
    this.queueMutation = (this.queueMutation || Promise.resolve()).catch(() => {}).then(async () => {
      const before = this.filingQueue.slice();
      change();
      try { await this.saveFilingQueue(); }
      catch (error) { this.filingQueue = before; throw error; }
    });
    return this.queueMutation;
  },
  queuedReviewIds() {
    return new Set(this.filingQueue.flatMap(job => job.method === 'approve' ? [job.params.identity] : job.params.entries.map(row => row.id)));
  },
  async queueFiling(method, params, title) {
    const ids = method === 'approve' ? [params.identity] : params.entries.map(row => row.id);
    const job = {id: `${Date.now()}-${++this.serial}`, method, params: JSON.parse(JSON.stringify(params)), title: title || params.title || 'Reviewed paper', connection: this.filingConnection()};
    let added = false;
    await this.changeFilingQueue(() => {
      if (!ids.some(id => this.queuedReviewIds().has(id))) { this.filingQueue.push(job); added = true; }
    });
    if (!added) return;
    if (!this.filingQueuePaused) await this.yieldSyncForFiling();
    if (this.view && !this.view.closed) this.render();
    await this.drainFilings();
  },
  async removeFiling(job) {
    if (job.id === this.activeFiling) throw Error('This paper is already being filed. Use Stop to interrupt it safely.');
    const index = this.filingQueue.indexOf(job);
    if (index < 0) return;
    try { await this.changeFilingQueue(() => { this.filingQueue = this.filingQueue.filter(row => row !== job); }); }
    catch (error) {
      this.filingQueuePaused = true; this.queueError = 'The queue could not be saved. This paper remains queued; retry removing it.';
      throw error;
    }
    if (!this.filingQueue.length) this.queueError = '';
    if (this.view && !this.view.closed) this.render();
  },
  async drainFilings() {
    if (this.busy || this.drainingFilings || this.filingQueuePaused || this.stopped || !this.filingQueue.length) return;
    this.drainingFilings = true;
    try {
      await this.queueMutation;
      await this.queueSave;
      while (this.filingQueue.length && !this.filingQueuePaused && !this.stopped) {
        // Queue persistence yields to the event loop. A manual sync may have
        // acquired the writer since our first check; never discard its
        // waiting approval because action() declined a busy operation.
        if (this.busy || this.pausing) break;
        const job = this.filingQueue[0];
        if (job.connection !== this.filingConnection()) throw Error('Queued papers belong to a different folder connection. Return to that connection before resuming.');
        this.activeFiling = job.id;
        if (this.view && !this.view.closed) this.render();
        // An interrupted job may already have finished. A fresh status tells
        // us whether its review still exists before repeating any writes.
        const pending = new Set((this.latest.reviews || []).map(row => row.id));
        if (job.method !== 'approve' || pending.has(job.params.identity)) {
          await this.action(job.method, job.params);
          const remaining = new Set((this.latest.reviews || []).map(row => row.id));
          if (job.method === 'approve' ? remaining.has(job.params.identity) : job.params.entries.some(row => remaining.has(row.id))) {
            // A stopped batch can have completed some of its papers. Keep
            // only unfinished decisions so resuming does not replay writes.
            if (job.method === 'approve_routine') job.params.entries = job.params.entries.filter(row => remaining.has(row.id));
            if (this.latest.status?.state !== 'paused') this.queueError = 'Some papers still need review or recovery. Resume to retry, or remove the waiting job to edit its choices.';
            this.filingQueuePaused = true; break;
          }
        }
        await this.changeFilingQueue(() => { this.filingQueue = this.filingQueue.filter(row => row.id !== job.id); });
        this.activeFiling = null;
      }
      // Filing saves the user's decision. A transfer is a separate, explicit
      // Sync now action (or the existing closed-workspace schedule), never a
      // whole-library scan between individual approvals.
    } catch (error) {
      this.filingQueuePaused = true; this.queueError = error.message;
    } finally {
      this.activeFiling = null; this.drainingFilings = false;
      await this.saveFilingQueue();
      if (this.view && !this.view.closed) this.render();
      if (this.filingQueue.length && !this.filingQueuePaused && !this.stopped) this.drainFilings().catch(error => this.message(error.message, true));
    }
  },
  renderFilingQueue(parent) {
    if (!this.filingQueue.length && !this.queueError) return;
    const card = this.el('section', '', parent, {class: 'card'});
    this.el('h2', `${this.filingQueue.length} filing ${this.filingQueue.length === 1 ? 'job' : 'jobs'} ${this.filingQueuePaused ? 'paused' : 'queued'}`, card);
    this.el('p', this.operation?.method === 'sync'
      ? 'Your choices are saved. Sync is finishing its current paper so filing can continue. You can keep reviewing.'
      : 'Your choices are saved and will be filed one at a time. Use Sync now afterward to transfer PDFs and tablet notes.', card);
    if (this.queueError) {
      this.el('p', this.queueError, card, {class: 'message error'});
      this.el('p', 'Remove a waiting job from the queue to edit it in Review, or resume the queue to retry.', card, {class: 'hint'});
    }
    if (this.filingQueuePaused && this.filingQueue.length) {
      const resume = this.button('Resume queued filings', card, async () => {
        this.queueError = ''; this.filingQueuePaused = false; await this.saveFilingQueue(); await this.drainFilings();
      }, true); resume.dataset.browse = 'true';
    }
    for (const job of this.filingQueue) {
      const line = this.el('div', '', card, {class: 'queued-filing'});
      this.el('p', `${job.id === this.activeFiling ? 'Filing: ' : 'Waiting: '}${job.title}`, line);
      if (job.id !== this.activeFiling) {
        const cancel = this.button('Remove from queue', line, async () => {
          await this.removeFiling(job);
        }); cancel.dataset.browse = 'true';
      }
    }
  },
  disable(value) {
    if (this.view && !this.view.closed) for (const button of this.view.document.querySelectorAll('button')) {
      if (button.id === 'notable-pause') { button.disabled = !!this.pausing; continue; }
      if (button.dataset.browse === 'true') { button.disabled = false; continue; }
      if (button.dataset.queue === 'true') {
        button.disabled = !!this.pausing;
        if (button.dataset.approve === 'true') button.querySelector('.button-label').textContent = value ? 'Add to filing queue' : 'Approve & file';
        continue;
      }
      button.disabled = value || !!this.pausing || button.dataset.invalid === 'true' || (button.id === 'notable-sync' && !this.canSync());
    }
    if (this.view && !this.view.closed) for (const field of this.view.document.querySelectorAll('input, select, textarea')) field.disabled = !field.closest('.review-form') && (value || !!this.pausing);
    this.updateActivity();
  },
  message(value, error = false) {
    if (this.operation) { this.operation.detail = value; this.operation.updated = Date.now(); }
    if (!this.view || this.view.closed) return;
    const node = this.view.document.getElementById('message');
    if (node) { node.textContent = value; node.setAttribute('role', error ? 'alert' : 'status'); node.className = error ? 'message error' : 'message'; }
    this.updateActivity();
  },
  updateActivity() {
    if (!this.view || this.view.closed) return;
    const doc = this.view.document, panel = doc.getElementById('activity');
    if (!panel) return;
    const summary = doc.getElementById('notable-paper-status');
    if (summary) summary.textContent = this.paperStatusMessage();
    panel.hidden = !this.busy;
    const message = doc.getElementById('message'); if (message) message.hidden = !!this.busy;
    doc.getElementById('app').setAttribute('aria-busy', String(!!this.busy));
    const stop = doc.getElementById('notable-pause');
    if (stop) stop.querySelector('.button-label').textContent = this.pausing ? 'Stopping…' : this.busy ? 'Stop' : 'Pause sync';
    if (!this.operation) return;
    const job = this.operation, seconds = Math.floor((Date.now() - job.started) / 1000);
    const title = job.yielding ? 'Finishing the current paper so filing can continue…' : job.stopping ? 'Stopping the current check…' : job.title;
    for (const [id, text] of [['activity-title', title], ['activity-detail', job.detail]]) {
      const node = doc.getElementById(id); if (node.textContent !== text) node.textContent = text;
    }
    const quiet = Math.floor((Date.now() - job.updated) / 1000);
    doc.getElementById('activity-time').textContent = `Working for ${seconds < 60 ? seconds + ' seconds' : Math.floor(seconds / 60) + ' min ' + seconds % 60 + ' sec'}`
      + (quiet >= 15 ? ` · Last progress update ${quiet} seconds ago` : '');
    const bar = doc.getElementById('activity-progress'), count = job.detail.match(/(\d+) of (\d+)/);
    if (count && Number(count[2]) > 0) { bar.max = Number(count[2]); bar.value = Number(count[1]); }
    else bar.removeAttribute('value');
  },
  async mount(window) {
    this.view = window;
    this.workspaceOpening = false; clearTimeout(this.timer); this.yieldBackground();
    clearInterval(this.activityTimer); this.activityTimer = setInterval(() => this.updateActivity(), 1000);
    this.latest ||= {config: {}, status: {}, reviews: [], deletions: [], links: [], types: {}};
    this.tab = this.requestedTab || (this.latest.config.tablet_root ? 'review' : 'setup'); this.render();
    window.addEventListener('unload', () => { if (this.view === window) { this.view = null; clearInterval(this.activityTimer); this.reviewObserver?.disconnect(); this.schedule(); } }, {once: true});
    try { await this.refresh(); this.tab = this.requestedTab || (this.latest.config.tablet_root ? 'review' : 'setup'); this.requestedTab = null; this.render(); }
    catch (error) { this.message(error.message, true); }
  },
  el(tag, text, parent, attrs = {}) {
    const node = this.view.document.createElementNS('http://www.w3.org/1999/xhtml', tag);
    if (text) node.textContent = text;
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    parent?.appendChild(node); return node;
  },
  buttonIcons: {
    'Sync now': 'refresh-cw', 'Stop': 'x', 'Import library': 'folder-input',
    'Review': 'file-search', 'Tags': 'tag', 'Linked papers': 'link', 'Setup': 'settings',
    'Combine current tags and retry': 'refresh-cw', 'Remove tags from that unavailable page': 'trash-2',
    'Add tag': 'tag', 'Save tags': 'save', 'Close page editor': 'x', 'Search tags': 'search',
    'Open page': 'book-open', 'Open paper': 'book-open', 'Review linked papers': 'link',
    'Keep tablet copy': 'check', 'Trash tablet copy': 'trash-2', 'Restore on tablet': 'rotate-ccw',
    'Delete PDF only': 'trash-2', 'Delete everything': 'trash-2', 'Update filename preview': 'refresh-cw',
    'Open reference in Zotero': 'external-link', 'Approve & file': 'check', 'Connect Zotero': 'plug',
    'Choose literature folder…': 'folder-open', 'Scan folder — no library changes': 'folder-search',
    'Show matching reference in Zotero': 'external-link', 'Show in Zotero': 'external-link',
    'Resume link': 'link', 'Unlink (keep both copies)': 'unlink', 'Rebuild search index': 'refresh-cw',
    'Save name & destination': 'save', 'Get reMarkable pairing code': 'external-link',
    'Pair reMarkable': 'plug', 'Refresh folders': 'folder-sync', 'Choose ToSort folder…': 'folder-open',
    'Save setup': 'save', 'Save folder change': 'save', 'Review folder change': 'folder-search',
    'Browse all papers': 'file-search', 'Show only papers needing attention': 'file-search',
    'Find papers': 'search', 'Find keywords and suggest tags': 'tag', 'Use these tags when filing': 'save', 'Add keywords and selected tags': 'save',
    'Change folder': 'folder-open', 'Disconnect folder': 'unlink', 'Confirm disconnect': 'unlink',
    'Cancel change': 'x', 'Cancel': 'x', 'Pause sync': 'x'
  },
  button(text, parent, click, primary = false, icon = null) {
    // Every action row gets the same wrapping and spacing. Navigation, review
    // lists and tag chips already own their layouts.
    if (!parent.matches('nav, aside, .actions, .tag-chips')) {
      parent = parent.lastElementChild?.classList.contains('actions') ? parent.lastElementChild
        : this.el('div', '', parent, {class: 'actions'});
    }
    const node = this.el('button', '', parent, {type: 'button', class: primary ? 'primary' : ''});
    icon ||= this.buttonIcons[text] || (/^(File \d+ routine|Import \/ reuse \d+ routine)/.test(text) ? 'folder-input' : /^Use (desktop|tablet):/.test(text) ? 'check' : null);
    if (icon) this.el('span', '', node, {class: 'button-icon icon-' + icon, 'aria-hidden': 'true'});
    this.el('span', text, node, {class: 'button-label'});
    if (icon === 'trash-2') node.classList.add('danger');
    node.addEventListener('click', () => Promise.resolve().then(click).catch(error => this.message(error.message, true))); return node;
  },
  field(label, parent, value = '', type = 'input') {
    const wrapper = this.el('label', '', parent, {class: 'field'}); this.el('span', label, wrapper);
    const input = this.el(type, '', wrapper); input.value = value; input.dataset.notableField = label; return input;
  },
  checkbox(label, parent, checked) {
    const wrapper = this.el('label', '', parent, {class: 'checkbox-field'});
    const input = this.el('input', '', wrapper, {type: 'checkbox'}); input.checked = checked;
    this.el('span', label, wrapper); return input;
  },
  select(label, parent, options, selected = '', multiple = false) {
    const input = this.field(label, parent, '', 'select');
    if (multiple) { input.multiple = true; input.size = 5; }
    for (const [key, label] of options) { const option = this.el('option', label, input, {value: key}); option.selected = multiple ? selected.includes(key) : key === selected; }
    return input;
  },
  paths(rows, id, parent, name) {
    const by = new Map(rows.map(row => [row[id], row]));
    const label = row => { const parts = [], seen = new Set(); while (row && !seen.has(row[id])) { seen.add(row[id]); parts.unshift(row[name]); row = by.get(row[parent]); } return parts.join(' / '); };
    return rows.map(row => [row[id], label(row)]).sort((a, b) => a[1].localeCompare(b[1]));
  },
  mappedDestinations() {
    const config = this.latest.config, mappings = this.latest.mappings || {};
    const unknown = 'Folder name unavailable (refresh folders in Setup)';
    const collections = new Map((this.latest.collections || []).map(row => [row.key, row]));
    const folders = new Map((this.folderCatalog?.folders || []).map(row => [row.id, row]));
    // Saved mappings keep both paths readable before a folder refresh. The
    // roots may have different names; never substitute the Zotero root name
    // for the tablet root. Prefer current catalog names when available.
    for (const [key, link] of Object.entries(mappings)) {
      if (this.collectionsCurrent && !collections.has(key)) continue;
      const root = key === config.zotero_root;
      if (!collections.has(key)) collections.set(key, {key, name: root ? config.zotero_path || unknown : link.name || unknown,
        parentCollection: root ? false : link.zparent});
      if (!folders.has(link.cloud)) folders.set(link.cloud, {id: link.cloud,
        name: root ? config.tablet_path || unknown : link.name || unknown,
        parent: root ? '' : link.cparent || mappings[link.zparent]?.cloud});
    }
    const tabletPaths = new Map(this.paths([...folders.values()], 'id', 'parent', 'name'));
    return this.paths([...collections.values()], 'key', 'parentCollection', 'name')
      .filter(([key]) => mappings[key]).map(([key, zotero]) => {
        const tablet = tabletPaths.get(mappings[key].cloud) || unknown;
        return {key, zotero, tablet, label: `Zotero: ${zotero} → reMarkable: ${tablet}`};
      });
  },
  destinationSelect(label, parent, selected) {
    const destinations = this.mappedDestinations();
    const input = this.select(label, parent, destinations.map(row => [row.key, row.label]), selected);
    input.dataset.folderDestination = 'true';
    const summary = this.el('div', '', parent, {class: 'folder-pair', 'aria-live': 'polite'});
    const update = () => {
      summary.replaceChildren();
      const destination = this.mappedDestinations().find(row => row.key === input.value);
      if (!destination) { this.el('p', 'Refresh folders in Setup to see the linked folders.', summary); return; }
      for (const [label, path] of [['Zotero collection: ', destination.zotero], ['reMarkable folder: ', destination.tablet]]) {
        const line = this.el('p', '', summary); this.el('strong', label, line); this.el('span', path, line);
      }
      input.title = destination.label;
    };
    input.notableRefreshNames = () => {
      this.reconcileOptions(input, this.mappedDestinations().map(row => [row.key, row.label]));
      update();
    };
    input.addEventListener('change', update); update();
    return input;
  },
  supportingInformationPicker(parent, initial = {}) {
    const panel = this.el('section', '', parent);
    this.el('p', 'Supporting information is an extra attachment under its main paper. The main paper’s citation stays unchanged.', panel, {class: 'hint'});
    const query = this.field('Main paper title contains', panel, initial.main_query || '');
    const select = this.select('Main paper in Zotero (required)', panel, [['', 'Choose the main paper…']], '');
    const status = this.el('p', '', panel, {class: 'hint', role: 'status'});
    const load = async () => {
      const items = await Zotero.Items.getAll(Zotero.Libraries.userLibraryID, false, false);
      const choices = [];
      for (const item of items) {
        if (item.deleted || !item.isRegularItem()) continue;
        await item.loadAllData();
        const record = item.toJSON(), title = record.title || '(Untitled reference)';
        if (title.toLocaleLowerCase().includes(query.value.toLocaleLowerCase())) choices.push({key: item.key, title, record});
      }
      if (!select.isConnected) return;
      const selected = select.value || initial.main_reference || '';
      select.replaceChildren(); this.el('option', 'Choose the main paper…', select, {value: ''});
      for (const choice of choices.sort((a, b) => a.title.localeCompare(b.title))) {
        const option = this.el('option', choice.title, select, {value: choice.key});
        option.dataset.metadata = JSON.stringify(Object.fromEntries(['title', 'itemType', 'creators', 'date', 'DOI', 'publicationTitle', 'publisher', 'university', 'extra'].map(key => [key, choice.record[key] ?? ''])));
      }
      select.value = choices.some(choice => choice.key === selected) ? selected : '';
      status.textContent = `${choices.length} papers found. Select the main article, not another supporting file.`;
      select.dispatchEvent(new this.view.Event('change'));
    };
    const find = this.button('Find main paper', panel, load); find.dataset.browse = 'true';
    return {panel, query, select, load: () => load().catch(error => { if (status.isConnected) status.textContent = error.message; })};
  },
  render() {
    const focus = this.captureFocus();
    const previousList = this.view.document.querySelector('.review-layout > aside');
    if (previousList) this.reviewScrollTop = previousList.scrollTop;
    this.reviewObserver?.disconnect();
    const root = this.view.document.getElementById('app'); root.replaceChildren();
    const head = this.el('header', '', root); const title = this.el('div', '', head);
    this.el('h1', this.shortName, title); this.el('p', 'Sync papers, handwriting, and tags with Zotero.', title);
    const sync = this.button('Sync now', head, () => this.action('sync'), true);
    sync.id = 'notable-sync'; sync.disabled = this.busy || !this.canSync();
    const pause = this.button('Pause sync', head, () => this.pauseSync()); pause.id = 'notable-pause'; pause.disabled = !!this.pausing;
    const nav = this.el('nav', '', root, {'aria-label': this.shortName + ' sections'});
    for (const [tab, label] of [['review', 'Review'], ['links', 'Linked papers'], ['tags', 'Tags'], ['import', 'Import library'], ['setup', 'Setup']]) {
      const button = this.button(label, nav, () => { this.tab = tab; this.render(); });
      button.dataset.browse = 'true';
      button.setAttribute('aria-pressed', String(this.tab === tab));
    }
    const message = this.el('div', this.statusMessage(), root, {id: 'message', role: 'status', class: 'message'});
    if (this.latest.config.automatic) this.el('p', 'Automatic checks wait while this workspace is open. Use Sync now when you want to sync.', root, {class: 'hint'});
    const activity = this.el('section', '', root, {id: 'activity', class: 'activity', 'aria-label': 'Current activity'});
    this.el('span', '', activity, {class: 'activity-spinner', 'aria-hidden': 'true'});
    const info = this.el('div', '', activity, {class: 'activity-content'});
    const announcement = this.el('div', '', info, {role: 'status'});
    this.el('strong', '', announcement, {id: 'activity-title'});
    this.el('p', '', announcement, {id: 'activity-detail'});
    this.el('progress', '', announcement, {id: 'activity-progress', 'aria-label': 'Current step progress'});
    this.el('small', '', info, {id: 'activity-time', 'aria-live': 'off'});
    if (this.latest.config.tablet_root) this.el('p', this.paperStatusMessage(), root, {id: 'notable-paper-status', class: 'hint', role: 'status'});
    this.renderFilingQueue(root);
    const content = this.el('main', '', root);
    if (this.tab === 'setup') this.renderSetup(content);
    else if (this.tab === 'import') this.renderImport(content);
    else if (this.tab === 'links') this.renderLinks(content);
    else if (this.tab === 'tags') this.renderTags(content);
    else this.renderReview(content);
    this.disable(this.busy);
    this.restoreReviewList();
    this.restoreFocus(focus);
  },
  captureFocus() {
    const doc = this.view?.document, active = doc?.activeElement;
    const label = active?.dataset?.notableField;
    if (!label) return null;
    const fields = [...doc.querySelectorAll('[data-notable-field]')].filter(node => node.dataset.notableField === label);
    return {label, index: fields.indexOf(active), start: active.selectionStart, end: active.selectionEnd};
  },
  restoreFocus(focus) {
    if (!focus) return;
    const field = [...this.view.document.querySelectorAll('[data-notable-field]')].filter(node => node.dataset.notableField === focus.label)[focus.index];
    if (!field) return;
    field.closest('details')?.setAttribute('open', ''); field.focus({preventScroll: true});
    if (Number.isInteger(focus.start) && typeof field.setSelectionRange === 'function') { try { field.setSelectionRange(focus.start, focus.end); } catch (_) {} }
  },
  restoreReviewList() {
    const list = this.view.document.querySelector('.review-layout > aside');
    if (!list) return;
    list.scrollTop = this.reviewScrollTop || 0;
    const keepVisible = () => {
      const selected = list.querySelector('[aria-pressed="true"]');
      if (!selected || !list.isConnected) return;
      const box = list.getBoundingClientRect(), item = selected.getBoundingClientRect();
      if (item.top < box.top) list.scrollTop -= box.top - item.top;
      else if (item.bottom > box.bottom) list.scrollTop += item.bottom - box.bottom;
    };
    if (this.reviewFocus) { list.querySelector('[aria-pressed="true"]')?.focus({preventScroll: true}); this.reviewFocus = false; }
    keepVisible();
    this.reviewObserver = new this.view.ResizeObserver(keepVisible);
    this.reviewObserver.observe(list.nextElementSibling);
    list.addEventListener('scroll', () => { this.reviewScrollTop = list.scrollTop; });
  },
  renderTags(content) {
    if (!this.tagEditor) {
    const finder = this.el('details', '', content, {class: 'card'});
    this.el('summary', 'Find keywords and suggest paper tags', finder);
    this.el('p', 'Choose a stored PDF by title. Keywords can be added automatically; additional topic suggestions need your approval.', finder);
    const titleQuery = this.field('Paper title contains', finder);
    const results = this.el('div', '', finder);
    this.button('Find papers', finder, async () => {
      const value = await this.action('paper_tag_candidates', {query: titleQuery.value}, false);
      if (!value) return;
      results.replaceChildren();
      this.el('p', `${value.total} matching PDFs${value.total > 50 ? '; showing the first 50' : ''}.`, results);
      for (const paper of value.candidates) {
        const card = this.el('section', '', results, {class: 'card'});
        this.el('strong', paper.title, card); this.el('p', paper.filename, card, {class: 'hint'});
        this.paperTagPanel(card, {key: paper.key});
      }
    });
    }
    if (this.tagEditor) {
      const context = this.tagEditor;
      const draftKey = JSON.stringify([this.filingConnection(), context.key, context.page_id ?? context.page]);
      if (!this.tagDrafts.has(draftKey)) this.tagDrafts.set(draftKey, {paper: [...context.paper_tags], page: [...context.page_tags], token: context.token});
      const draft = this.tagDrafts.get(draftKey);
      const card = this.el('section', '', content, {class: 'card'});
      this.el('h2', `${context.title} — page ${context.page + 1}`, card);
      this.el('p', 'Paper tags categorize the whole reference. Page tags identify this exact page. Both sync with reMarkable.', card);
      if (context.interrupted) {
        this.el('p', 'A previous tag sync was interrupted. Sync normally to retry. If tags changed on both copies during that interruption, combine their current tags to recover; labels present on either copy will be retained.', card);
        this.button('Combine current tags and retry', card, async () => {
          const result = await this.action('combine_tag_copies', {key: context.key, page: context.page, token: context.token}, false);
          if (result) {
            draft.paper = [...new Set([...draft.paper, ...result.paper_tags])]; draft.page = [...new Set([...draft.page, ...result.page_tags])];
            draft.token = result.token; this.tagEditor = result; this.render();
          }
        });
      }
      for (const [pageID, tags] of Object.entries(context.orphaned_pages || {})) {
        this.el('p', 'A removed or unavailable page still has these tags: ' + tags.join(' · '), card);
        this.button('Remove tags from that unavailable page', card, async () => {
          const result = await this.action('remove_unavailable_page_tags', {key: context.key, page: context.page, page_id: pageID, token: context.token}, false);
          if (result) { draft.token = result.token; this.tagEditor = result; this.render(); }
        });
      }
      const suggestions = this.el('datalist', '', card, {id: 'notable-tag-vocabulary'});
      for (const value of context.vocabulary) this.el('option', '', suggestions, {value});
      const editor = (title, kind) => {
        this.el('h3', title, card);
        const tags = new Set(draft[kind]), chips = this.el('div', '', card, {class: 'tag-chips'});
        const remember = () => { draft[kind] = [...tags]; };
        const draw = () => { chips.replaceChildren(); for (const value of [...tags].sort()) {
          const chip = this.button(`${value} ×`, chips, () => { tags.delete(value); remember(); draw(); });
          chip.setAttribute('aria-label', `Remove ${value} from ${title.toLowerCase()}`);
        }};
        draw();
        const input = this.field(`Add ${title.toLowerCase().replace('tags', 'tag')}`, card, draft[kind + 'Input'] || '');
        input.addEventListener('input', () => { draft[kind + 'Input'] = input.value; });
        input.setAttribute('list', 'notable-tag-vocabulary'); input.maxLength = 255;
        const add = () => { const value = input.value.trim(); if (value) { tags.add(value); input.value = ''; draft[kind + 'Input'] = ''; remember(); draw(); }};
        input.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); add(); }});
        this.button('Add tag', card, add);
        return {tags, add};
      };
      const paper = editor('Paper tags', 'paper'), page = editor('Page tags', 'page');
      this.button('Save tags', card, async () => {
        paper.add(); page.add();
        const result = await this.action('set_page_tags', {key: context.key, page: context.page, page_id: context.page_id,
          tags: [...page.tags], paper_tags: [...paper.tags], token: draft.token}, false);
        if (!result) return;
        this.tagDrafts.delete(draftKey); this.tagEditor = result; this.render(); this.message('Tags saved. They will reach reMarkable on the next sync.');
      }, true);
      this.button('Close page editor', card, () => { this.tagEditor = null; this.render(); });
    }
    const search = this.el('section', '', content, {class: 'card'});
    this.el('h2', 'Find tagged papers and pages', search);
    const query = this.field('Tag name (leave blank for all tags)', search, this.tagQuery || '');
    const scope = this.select('Show', search, [['both', 'Papers and pages'], ['paper', 'Papers'], ['page', 'Pages']], this.tagScope || 'both');
    const run = async () => {
      this.tagQuery = query.value; this.tagScope = scope.value;
      const result = await this.action('tag_search', {query: query.value, scope: scope.value}, false);
      if (result) { this.tagResults = result.results; this.render(); }
    };
    this.button('Search tags', search, run, true);
    query.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); run().catch(e => this.message(e.message, true)); }});
    this.el('p', 'Whole-paper tags also work in Zotero’s usual tag selector. Use this view to find individual tagged pages.', search);
    for (const result of this.tagResults || []) {
      const row = this.el('section', '', content, {class: 'card'});
      this.el('p', `${result.title} · ${result.scope === 'page' ? 'Page ' + (result.page + 1) : 'Whole paper'}`, row);
      this.el('p', result.tags.join(' · '), row);
      this.button(result.scope === 'page' ? 'Open page' : 'Open paper', row, async () => {
        if (result.scope === 'page') {
          const fresh = await this.rpc('tag_context', {key: result.key, page: result.page});
          if (fresh.page_id !== result.page_id) throw new Error('The page order changed. Search again before opening this result.');
        }
        const item = result.key && await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, result.key);
        if (item) await Zotero.Reader.open(item.id, result.scope === 'page' ? {pageIndex: result.page} : undefined);
        else {
          const parent = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, result.parent);
          if (parent) await Zotero.getMainWindow().ZoteroPane.selectItem(parent.id);
        }
      });
    }
    if (this.tagResults && !this.tagResults.length) this.el('p', 'No matching tags.', content);
  },
  renderReview(content) {
    const queuedIds = this.queuedReviewIds();
    const routine = (this.latest.reviews || []).filter(row => row.status === 'pending' && row.payload.routine && !queuedIds.has(row.id));
    if (routine.length) {
      const card = this.el('section', '', content, {class: 'card review-form'});
      this.el('h2', `${routine.length} routine documents ready`, card);
      this.el('p', 'Missing citation fields do not block filing. Only uncertain identity, versions, unreadable files, or destination conflicts need individual review.', card);
      const destination = this.destinationSelect('Linked folders for this batch (Zotero → reMarkable)', card, this.batchCollection || this.latest.config.zotero_root);
      destination.addEventListener('change', () => { this.batchCollection = destination.value; });
      this.el('p', 'Papers already on the tablet keep their folders. New tablet copies use the destination above. Use Sync now after filing to transfer PDFs and tablet notes.', card, {class: 'hint'});
      const batch = this.button(`File ${routine.length} routine documents together`, card, async () => {
        await this.queueFiling('approve_routine', {collection: destination.value,
          entries: routine.map(row => ({id: row.id, digest: row.digest, review_token: row.payload.review_token}))}, `${routine.length} routine documents`);
      }, true); batch.dataset.queue = 'true';
      const preview = this.el('details', '', card); this.el('summary', 'Optional filename preview', preview);
      for (const row of routine) this.el('p', row.payload.filename, preview);
      const browse = this.button(this.showAllReviews ? 'Show only papers needing attention' : 'Browse all papers', card,
        () => { this.showAllReviews = !this.showAllReviews; this.selected = null; this.render(); });
      browse.dataset.browse = 'true';
    }
    const queued = new Set((this.latest.reviews || []).map(r => r.identity));
    const pendingTrash = new Set((this.latest.deletions || []).map(r => r.payload.cloud));
    for (const issue of this.latest.status?.result?.review || []) {
      if (this.isQueueMessage(issue) || queued.has(issue.attachment) || queued.has(issue.cloud) || pendingTrash.has(issue.cloud)) continue;
      const card = this.el('section', '', content, {class: 'card decision'});
      const linked = (this.latest.links || []).some(row => row.cloud === issue.cloud || row.source_key === issue.attachment || row.view_key === issue.attachment);
      this.el('h2', linked ? 'A linked paper needs attention' : 'A paper needs attention', card); this.el('p', issue.reason, card);
      if (linked) this.button('Review linked papers', card, () => { this.tab = 'links'; this.render(); });
      else this.el('p', 'Resolve the reported file problem, then use Sync now to retry this paper.', card, {class: 'hint'});
    }
    for (const row of this.latest.local_deletions || []) {
      const card = this.el('section', '', content, {class: 'card decision'});
      this.el('h2', 'Trashed in Zotero: ' + row.payload.title, card);
      this.el('p', 'The tablet copy is still present. Choose whether to keep it or send it to tablet Trash. The link stays paused.', card);
      for (const [choice, label] of [['keep_tablet', 'Keep tablet copy'], ['trash_tablet', 'Trash tablet copy']]) {
        this.button(label, card, () => this.action('local_delete_decision', {identity: row.id, choice}));
      }
    }
    const deletions = this.latest.deletions || [];
    for (const row of deletions) {
      const card = this.el('section', '', content, {class: 'card decision'});
      this.el('h2', 'Trashed on reMarkable: ' + row.payload.title, card);
      this.el('p', 'Choose what happens next. Closing this window leaves the decision pending. Zotero deletions go to Trash.', card);
      const names = (row.payload.inventory || []).filter(i => i.key !== row.payload.parent && !i.deleted).map(i => i.title || i.itemType);
      this.el('p', 'This reference contains: ' + names.join('; '), card);
      const folderChoices = this.mappedDestinations().map(folder => [this.latest.mappings[folder.key].cloud, folder.tablet]);
      const restoreHome = this.select('Restore to tablet folder', card, [['', 'Use its previous tablet folder'], ...folderChoices], '');
      this.el('p', 'If its previous folder was removed, choose another linked folder before restoring.', card, {class: 'hint'});
      const buttons = this.el('div', '', card, {class: 'actions'});
      for (const [choice, label] of [['restore', 'Restore on tablet'], ['pdf_only', 'Delete PDF only'], ['everything', 'Delete everything']]) {
        this.button(label, buttons, () => this.action('delete_decision', {identity: row.id, choice, destination: choice === 'restore' ? restoreHome.value : ''}), choice === 'restore');
      }
    }
    const rows = (this.latest.reviews || []).filter(row => !queuedIds.has(row.id) && (this.showAllReviews || !row.payload.routine || row.status === 'applying'));
    if (!rows.length) { this.el('h2', 'No individual reviews needed', content); this.el('p', 'Routine documents can be filed together above. Use Sync now after filing to transfer PDFs and tablet notes. Use Import library to bring in an existing Windows collection.', content); return; }
    const layout = this.el('div', '', content, {class: 'review-layout'}), list = this.el('aside', '', layout, {'aria-label': 'Documents awaiting review'});
    for (const row of rows) {
      const button = this.button(row.payload.title || row.payload.desktop?.[0] || 'Folder conflict', list, () => { this.selected = row.id; this.reviewFocus = true; this.render(); }, false, 'file-text');
      button.dataset.browse = 'true';
      button.setAttribute('aria-pressed', String(row.id === (this.selected || rows[0].id)));
      button.addEventListener('keydown', event => {
        if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const index = rows.findIndex(value => value.id === row.id);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1 : Math.max(0, Math.min(rows.length - 1, index + (event.key === 'ArrowUp' ? -1 : 1)));
        this.selected = rows[next].id; this.reviewFocus = true; this.render();
      });
    }
    const row = rows.find(r => r.id === this.selected) || rows[0], detail = this.el('section', '', layout, {class: 'card review-form'});
    if (row.kind === 'conflict') {
      this.el('h2', (row.payload.type === 'paper' ? 'Paper' : 'Folder') + ' changed on both devices', detail);
      this.el('p', 'Choose the name and location to keep. Files and notes remain in place.', detail);
      if (row.payload.type === 'paper') this.reviewOpenButton(row, detail);
      for (const side of ['desktop', 'tablet']) this.button(`Use ${side}: ${row.payload[side][0]}`, detail,
        () => this.action('resolve_conflict', {identity: row.id, digest: row.digest, side}));
      return;
    }
    this.el('h2', 'Review document', detail); this.el('p', row.kind === 'cloud' ? 'Added on reMarkable' : row.kind === 'inbox' ? 'Downloaded to ToSort' : 'Added to Zotero', detail);
    this.reviewOpenButton(row, detail);
    this.paperTagPanel(detail, {identity: row.id});
    for (const issue of row.payload.issues || []) this.el('p', issue, detail, {class: 'message error'});
    if (row.kind === 'inbox' && row.status !== 'applying') this.button('Dismiss this intake review', detail,
      () => this.action('dismiss_review', {identity: row.id, digest: row.digest}));
    const savedDraft = this.reviewDrafts.get(row.id);
    const draft = savedDraft?.digest === row.digest ? savedDraft : {};
    const title = this.field('Title', detail, draft.title ?? row.payload.title);
    const isSupplement = row.payload.details?.is_supplementary_material || /(?:^|[_ -])si(?:\.pdf)?$/i.test(row.payload.filename || '');
    const type = this.select('Document type', detail, [...Object.entries(this.latest.types), ['supporting_information', 'Supporting Information']],
      draft.document_type ?? (isSupplement ? 'supporting_information' : row.payload.document_type));
    const main = this.supportingInformationPicker(detail, draft);
    const updateSupplement = () => {
      main.panel.hidden = type.value !== 'supporting_information';
      if (!main.panel.hidden && !main.loaded) { main.loaded = true; main.load(); }
    };
    type.addEventListener('change', updateSupplement); updateSupplement();
    const filename = this.field('Filename', detail, draft.filename ?? row.payload.filename);
    this.button('Update filename preview', detail, async () => {
      const value = await this.action('preview', {identity: row.id, document_type: type.value, title: title.value}, false);
      if (value?.filename) { filename.value = value.filename; saveDraft(); }
    });
    const collections = this.latest.collections || [];
    const paths = this.paths(collections, 'key', 'parentCollection', 'name');
    const mapped = this.latest.mappings || {};
    const cloudHome = row.payload.tablet_parent || this.latest.config.default_folder || this.latest.config.tablet_root;
    const originalHomes = (row.payload.source_collections || []).filter(key => mapped[key]);
    const matchHome = row.kind === 'zotero' && row.payload.matches?.length === 1
      ? Object.entries(mapped).find(([, value]) => value.cloud === row.payload.matches[0].parent)?.[0] : null;
    const defaultHome = matchHome || (row.kind === 'zotero' && originalHomes.length === 1 ? originalHomes[0]
      : Object.entries(mapped).find(([key, value]) => value.cloud === cloudHome)?.[0] || this.latest.config.zotero_root);
    const previousHome = (this.latest.links || []).find(link => link.parent === row.payload.parent)?.collection;
    const home = this.destinationSelect('Linked folders for this paper (Zotero → reMarkable; one tablet copy)', detail, draft.collection ?? previousHome ?? defaultHome);
    const research = this.select('Research collections (optional; Ctrl-click for several)', detail, paths.filter(([key]) => !mapped[key]), draft.research || [], true);
    research.dataset.zoteroCollections = 'research';
    let match;
    if (row.payload.matches?.length) match = this.select(row.kind === 'cloud' ? 'An identical PDF already exists on this PC' : 'An identical PDF already exists on reMarkable', detail,
      [['', 'Keep separate'], ...row.payload.matches.map(m => [m.key, 'Link to: ' + m.title])],
      draft.match ?? (row.payload.matches.length === 1 ? row.payload.matches[0].key : ''));
    if (match) this.el('p', 'Link to reuses the identical PDF already found. Keep separate creates a separate paper.', detail, {class: 'hint'});
    const citation = this.el('details', '', detail); this.el('summary', 'Citation details found locally', citation);
    const details = row.payload.details || {};
    this.el('p', [details.primary_creator, details.year, details.venue_or_publisher, details.identifier?.doi].filter(Boolean).join(' · ') || 'No reliable citation fields found. You can edit the reference in Zotero.', citation);
    if (row.payload.parent) this.button('Open reference in Zotero', citation, async () => { const item = await notableItem(row.payload.parent); if (item) { Zotero.getMainWindow().focus(); await Zotero.getActiveZoteroPane().selectItem(item.id); } });
    this.el('p', (row.payload.path || '').toLowerCase().endsWith('.pdf') ? 'Approve & file saves your choices. Use Sync now afterward to transfer the PDF and tablet notes.' : 'This Office document will be stored in Zotero. Attach a PDF version to read it on reMarkable.', detail, {class: 'hint'});
    const approve = this.button(this.busy ? 'Add to filing queue' : 'Approve & file', detail, async () => {
      if (!main.panel.hidden && !main.select.value) throw Error('Choose the main paper in Zotero for this supporting information.');
      await this.queueFiling('approve', {identity: row.id, digest: row.digest, filename: filename.value, title: title.value,
        document_type: type.value, collection: home.value, research: Array.from(research.selectedOptions, o => o.value), match: match?.value || '', review_token: row.payload.review_token || '',
        main_reference: main.panel.hidden ? '' : main.select.value,
        main_reference_metadata: main.panel.hidden ? null : JSON.parse(main.select.selectedOptions[0].dataset.metadata)});
    }, true); approve.dataset.queue = 'true'; approve.dataset.approve = 'true';
    const saveDraft = () => this.reviewDrafts.set(row.id, {digest: row.digest, title: title.value, document_type: type.value, filename: filename.value,
      collection: home.value, research: Array.from(research.selectedOptions, o => o.value), match: match?.value || '',
      main_reference: main.select.value, main_query: main.query.value});
    for (const field of [title, type, filename, home, research, match, main.select, main.query].filter(Boolean)) {
      field.addEventListener('input', saveDraft); field.addEventListener('change', saveDraft);
    }
  },
  async openReviewPaper(row) {
    const path = row.payload?.path || '';
    if (!path) {
      const link = (this.latest.links || []).find(link => link.cloud === row.payload?.cloud);
      const item = (link?.view_key || link?.source_key) && await notableItem(link.view_key || link.source_key);
      if (!item?.isPDFAttachment()) throw new Error('No readable paper is available for this review.');
      await Zotero.Reader.open(item.id); return;
    }
    if (!/\.(pdf|docx|pptx)$/i.test(path) || !PathUtils.isAbsolute(path)) throw new Error('No readable paper is available for this review.');
    const file = Zotero.File.pathToFile(path);
    if (!file.exists() || !file.isFile()) throw new Error('This saved paper is unavailable. Refresh its review before opening it.');
    // Use Zotero's existing local-file launcher; opening never approves,
    // imports, renames, or transfers this document.
    Zotero.launchFile(file);
  },
  paperTagPanel(parent, scope) {
    const panel = this.el('details', '', parent, {class: 'paper-tag-proposal'});
    this.el('summary', 'Paper keywords and suggested tags', panel);
    this.el('p', 'Stated keywords come from the paper. Extra topic tags are suggestions until you select and save them.', panel);
    const output = this.el('div', '', panel);
    this.button('Find keywords and suggest tags', panel, async () => {
      const value = await this.action('suggest_paper_tags', scope, false);
      if (!value) return;
      const proposal = value.proposal; output.replaceChildren();
      this.el('h3', 'Stated keywords', output);
      if (!proposal.keywords.length) this.el('p', 'No reliable keyword list found. Existing tags will be kept.', output);
      for (const row of proposal.keywords) this.el('p', `${row.tag} — ${row.source}`, output);
      this.el('h3', 'Suggested topic tags — choose any you want', output);
      const options = proposal.suggestions.map(row => {
        const input = this.checkbox(row.tag, output, proposal.selected.includes(row.tag));
        this.el('p', row.source + ' · Found in text: ' + row.evidence, output, {class: 'hint'});
        return [row.tag, input];
      });
      this.el('p', proposal.notice, output, {class: 'hint'});
      const save = this.button(scope.identity ? 'Use these tags when filing' : 'Add keywords and selected tags', output, async () => {
        const result = await this.action('save_paper_tags', {target: proposal.target, token: proposal.token,
          selected: options.filter(([, input]) => input.checked).map(([tag]) => tag)}, false);
        if (result?.saved) { save.disabled = true; this.el('p', result.deferred_until_filing ? 'Tag choices saved. They will be added when this paper is filed.' : 'Paper tags saved. Linked tablet copies receive them on the next sync.', output, {role: 'status'}); }
      }, true);
    });
  },
  reviewOpenButton(row, parent) {
    const link = (this.latest.links || []).find(link => link.cloud === row.payload?.cloud);
    if (!row.payload?.path && !link?.view_key && !link?.source_key) return;
    const button = this.button('Open paper', parent, () => this.openReviewPaper(row));
    button.dataset.browse = 'true';
    button.title = 'Open the saved file in your usual reader without approving or importing it';
    if (row.kind === 'cloud') this.el('p', 'Opens the downloaded original PDF. Tablet handwriting is added when the approved paper syncs.', parent, {class: 'hint'});
  },
  renderImport(content) {
    this.el('h2', 'Bring your Windows library into Zotero', content);
    this.el('p', 'Scan first, then import routine files together. Exact copies are grouped, existing Zotero files are reused, and your original Windows folders stay in place.', content);
    if (!(this.latest.collections || []).length) {
      this.el('p', 'Connect Zotero and create a personal collection for these imports. Tablet pairing can wait.', content);
      this.button('Connect Zotero', content, () => this.action('connect'), true); return;
    }
    const plan = this.latest.bulk;
    const results = content;
    content = this.el('section', '', results, {class: 'card'});
    const path = this.field('Literature folder, including subfolders', content, this.intakeRoot || plan?.root || '');
    this.button('Choose literature folder…', content, async () => {
      const {FilePicker} = ChromeUtils.importESModule('chrome://zotero/content/modules/filePicker.mjs');
      const picker = new FilePicker(); picker.init(this.view, 'Choose your existing literature folder', picker.modeGetFolder);
      if (await picker.show() === picker.returnOK) { path.value = this.intakeRoot = picker.file; invalidate(); }
    });
    const collection = this.select('Zotero collection for imports', content,
      this.paths(this.latest.collections, 'key', 'parentCollection', 'name'), this.intakeCollection || plan?.collection || this.latest.collections[0].key);
    collection.dataset.zoteroCollections = 'true';
    const lookup = this.checkbox('Retrieve citations using title-verified DOI metadata', content, this.intakeLookup ?? plan?.lookup !== false);
    const scanSettings = () => ({root: path.value, collection: collection.value, lookup: lookup.checked});
    const sameSettings = () => !!plan && path.value.toLowerCase().replace(/[\\/]+$/, '') === plan.root.toLowerCase().replace(/[\\/]+$/, '')
      && collection.value === plan.collection && lookup.checked === (plan.lookup !== false);
    let importButton;
    const planActions = [];
    const notice = this.el('p', '', content, {role: 'status', class: 'hint'});
    const invalidate = () => {
      this.intakeRoot = path.value; this.intakeCollection = collection.value; this.intakeLookup = lookup.checked;
      const stale = !!plan && !sameSettings();
      notice.textContent = stale ? 'These choices changed after scanning. Scan again before importing.' : '';
      for (const button of [importButton, ...planActions].filter(Boolean)) { button.dataset.invalid = String(stale); button.disabled = stale || this.busy; }
    };
    for (const node of [path, collection, lookup]) { node.addEventListener('input', invalidate); node.addEventListener('change', invalidate); }
    this.el('p', 'DOI metadata is used only when its title matches this document’s own title. If no citation can be verified, the file keeps a local document reference and a warning to review its citation in Zotero. This route does not send PDF text to Zotero’s recognition service.', content, {class: 'hint'});
    this.button('Scan folder — no library changes', content, async () => {
      this.intakeRoot = path.value; this.intakeCollection = collection.value;
      this.intakeLookup = lookup.checked;
      await this.action('scan_library', scanSettings(), false);
      this.intakeRoot = this.latest.bulk?.root || path.value; this.render();
    }, true);
    content = results;
    if (!plan) return;
    const rows = plan.rows, ready = rows.filter(row => !row.issues.length && !['complete', 'dismissed'].includes(row.status));
    const complete = rows.filter(row => row.status === 'complete').length;
    const copies = rows.reduce((n, row) => n + row.copies.length, 0);
    const summary = this.el('section', '', content, {class: 'card'});
    this.el('h2', 'Folder scan', summary);
    this.el('p', `${copies} files · ${rows.length} unique contents · ${copies - rows.length} extra exact copies grouped · ${complete} completed`, summary);
    this.el('p', `${ready.length} routine files ready; ${rows.filter(row => row.issues.length && row.status !== 'dismissed').length + plan.failures.length} cases need attention.`, summary);
    this.el('p', `${rows.filter(row => row.existing).length} unique contents already exist in Zotero and will be reused. This import does not rename or move your Windows files.`, summary);
    if (ready.length) importButton = this.button(`Import / reuse ${ready.length} routine files`, summary, () => {
      if (!sameSettings()) throw Error('Scan again to apply the visible folder, collection, and citation-lookup choices.');
      return this.action('import_library', {plan_id: plan.id, ...scanSettings()});
    }, true);
    invalidate();
    if (complete) this.el('p', 'After tablet Setup, run Sync now to prepare the routine filing batch in Review.', summary);
    const filter = this.field('Filter import exceptions', content, this.importFilter || '');
    const exceptions = [];
    for (const row of rows.filter(row => row.issues.length && row.status !== 'dismissed')) {
      const card = this.el('section', '', content, {class: 'card decision'});
      exceptions.push([card, [row.path, ...row.issues].join(' ').toLocaleLowerCase()]);
      this.el('strong', row.path, card);
      for (const issue of row.issues) this.el('p', issue, card);
      const key = row.parent || row.existing || row.candidates?.[0]?.key;
      if (key) this.button('Show matching reference in Zotero', card, async () => {
        const item = await notableItem(key); if (item) await Zotero.getActiveZoteroPane().selectItem(item.id);
      });
      planActions.push(this.button('Retry import for this file', card, () => {
        if (!sameSettings()) throw Error('Scan again to apply the visible folder, collection, and citation-lookup choices.');
        return this.action('retry_bulk', {plan_id: plan.id, row_id: row.id, ...scanSettings()});
      }));
      this.button('Dismiss this exception', card, () => this.action('retry_bulk', {plan_id: plan.id, row_id: row.id, dismiss: true}));
    }
    const applyFilter = () => { this.importFilter = filter.value; for (const [card, text] of exceptions) card.hidden = !text.includes(filter.value.toLocaleLowerCase()); };
    filter.addEventListener('input', applyFilter); applyFilter();
    invalidate();
    for (const failure of plan.failures) this.el('p', failure.path + ': ' + failure.reason, content, {class: 'message error'});
  },
  renderLinks(content) {
    this.el('h2', 'Linked papers', content);
    const links = this.latest.links || [], received = links.filter(row => row.revision && !row.unavailable).length;
    const unavailable = links.filter(row => row.unavailable).length;
    this.el('p', `${links.length - unavailable} connected papers · ${received} tablet copies received · ${unavailable} unavailable`, content);
    this.el('p', 'Linked means the Zotero and tablet copies are connected. PDFs and tablet notes arrive during Sync now.', content);
    if (!links.length) this.el('p', 'No paper connections yet. Approve papers in Review, then use Sync now.', content);
    const filter = this.field('Filter linked papers', content, this.linkFilter || ''), cards = [];
    for (const row of links) {
      const card = this.el('section', '', content, {class: 'card'}); this.el('h2', row.name, card);
      cards.push([card, row.name.toLocaleLowerCase()]);
      this.el('p', row.unavailable ? 'The tablet document is unavailable. The link and retained files are kept; sync again when it is available.'
        : row.paused ? 'Link paused. Both copies are kept; changes will not sync until you resume.'
        : row.revision ? 'Tablet PDF and available notes received' : 'Connected; waiting for the first PDF and tablet notes sync', card);
      this.button('Show in Zotero', card, async () => { const item = await notableItem(row.parent); if (item) await Zotero.getActiveZoteroPane().selectItem(item.id); });
      this.button(row.paused ? 'Resume link' : 'Unlink (keep both copies)', card, () => this.action('link', {identity: row.cloud, paused: !row.paused}));
      if (row.view_key) this.button('Rebuild search index', card, () => this.action('reindex', {key: row.view_key}));
      if (row.keyword_check) {
        const labels = {found: 'Paper keywords checked and added where missing.', no_stated_keywords: 'No stated keyword list found in the readable first pages.',
          needs_text_recognition: 'Keywords need text recognition or manual checking.', extraction_failed: 'The keyword check failed; sync will retry.'};
        this.el('p', labels[row.keyword_check.status] || 'Keyword check pending.', card, {class: 'hint'});
      }
      const edit = this.el('details', '', card); this.el('summary', 'Rename or move', edit);
      const key = JSON.stringify([this.filingConnection(), row.cloud]), draft = this.linkDrafts.get(key) || {};
      edit.open = !!draft.open;
      const name = this.field('PDF name', edit, draft.name ?? row.name);
      const home = this.destinationSelect('Linked folders for this paper (Zotero → reMarkable)', edit, draft.collection ?? row.collection);
      const saveDraft = () => this.linkDrafts.set(key, {name: name.value, collection: home.value, open: edit.open, revision: draft.revision ?? row.revision});
      for (const field of [name, home]) { field.addEventListener('input', saveDraft); field.addEventListener('change', saveDraft); }
      edit.addEventListener('toggle', saveDraft);
      this.button('Save name & destination', edit, async () => {
        await this.action('move_link', {identity: row.cloud, name: name.value, collection: home.value, revision: draft.revision ?? row.revision}, false);
        this.linkDrafts.delete(key); this.render();
        this.message('Name and destination saved. Use Sync now to apply them to reMarkable.');
      });
      const history = this.el('details', '', card); this.el('summary', 'Link & recovery history', history);
      this.el('p', 'Clean baseline and downloaded tablet sources are retained privately for recovery.', history);
      for (const event of row.history || []) this.el('p', new Date(event.time * 1000).toLocaleString() + ' — ' + event.action, history);
      if (row.desktop_annotations_preserved) this.el('p', 'Independent desktop annotations are preserved in their original attachment.', history);
    }
    const applyFilter = () => { this.linkFilter = filter.value; for (const [card, text] of cards) card.hidden = !text.includes(filter.value.toLocaleLowerCase()); };
    filter.addEventListener('input', applyFilter); applyFilter();
  },
  renderSetup(content) {
    const config = this.latest.config, draft = this.setupDraft || config, connected = !!config.tablet_root;
    const main = content;
    this.el('h2', 'Setup', main);
    this.el('p', 'Save your folder choices first. Sync starts when you click Sync now.', main);
    content = this.el(connected ? 'details' : 'section', '', main, {class: 'card'});
    this.el(connected ? 'summary' : 'h2', connected ? 'Zotero and tablet connection settings' : 'Connect Zotero and reMarkable', content);
    const steps = this.el('div', '', content, {class: 'actions'});
    this.button('Connect Zotero', steps, async () => { await this.action('connect'); if (config.tablet_root) await this.loadFolders(); });
    this.button('Repair bundled helper', steps, async () => {
      if (this.process) await this.closeProcess(this.process);
      this.repairRuntime = true; await this.refresh(); this.render();
      this.message('The bundled helper was checked and reinstalled from this plugin package.');
    });
    this.button('Get reMarkable pairing code', steps, () => Zotero.launchURL('https://my.remarkable.com/device/desktop/connect'));
    const code = this.field('Single-use reMarkable pairing code', content); code.maxLength = 8; code.autocomplete = 'off'; code.className = 'pairing-code';
    this.button('Pair reMarkable', content, async () => { const value = code.value; code.value = ''; await this.action('pair', {code: value}); await this.loadFolders(); });
    if (!connected) this.button('Refresh folders', content, () => this.loadFolders());
    const scope = this.el('section', '', main, {class: 'card'});
    this.el('h2', connected ? 'Your synced folders' : 'Choose your synced folders', scope);
    const folders = this.folderCatalog;
    const zpaths = folders ? this.paths(folders.collections, 'key', 'parentCollection', 'name') : [];
    const cpaths = folders ? this.paths(folders.folders, 'id', 'parent', 'name') : [];
    const name = (paths, key, fallback) => paths.find(([id]) => id === key)?.[1] || fallback;
    if (connected) {
      this.el('p', 'Zotero: ' + name(zpaths, config.zotero_root, config.zotero_path || 'Saved Zotero collection'), scope, {id: 'notable-connected-zotero'});
      this.el('p', 'reMarkable: ' + name(cpaths, config.tablet_root, config.tablet_path || 'Saved reMarkable folder'), scope);
      this.el('p', 'These two folders are linked. Their names can be different.', scope, {class: 'hint'});
      this.el('p', `${this.latest.connection?.linked_papers ?? this.latest.links?.length ?? 0} linked papers · ${config.sync_paused ? 'Sync paused' : 'Ready to sync'}`, scope, {class: 'hint'});
      if (!this.changingFolder && !this.disconnectPreview) {
        this.button('Change folder', scope, async () => {
          this.changingFolder = true; this.setupDraft = {...this.latest.config}; this.folderPreview = null;
          await this.pauseSync(); if (!this.folderCatalog) await this.loadFolders(); else this.render();
        });
        this.button('Disconnect folder', scope, async () => {
          await this.pauseSync(); this.disconnectPreview = await this.action('preview_disconnect', {}, false); this.render();
        });
      }
      this.button('Refresh folders', scope, () => this.loadFolders());
    }
    if (this.disconnectPreview) {
      const preview = this.disconnectPreview;
      this.el('h3', 'Disconnect this folder?', scope);
      this.el('p', `Your papers and handwritten notes will stay in both libraries. ${preview.linked_papers} paper links and ${preview.pending_reviews} reviews will be kept with this connection. Your tablet will stay paired.`, scope);
      this.button('Confirm disconnect', scope, async () => {
        await this.action('disconnect_folder', {confirmation: preview.token}, false);
        this.clearFolderEditor(); this.render();
      }, true);
      this.button('Cancel', scope, () => { this.disconnectPreview = null; this.render(); });
      return;
    }
    if (!folders) this.el('p', 'Refresh folders to choose synced folders. Local intake, search, and naming settings remain available below.', scope);
    let zroot, croot, destination;
    if ((!connected || this.changingFolder) && folders) {
      this.el('p', 'Choose a dedicated Zotero collection and the reMarkable folder you want to use. Saving keeps papers and notes in place.', scope);
      zroot = this.select('Zotero collection tree for tablet locations', scope, [['', 'Choose a Zotero collection…'], ...zpaths], draft.zotero_root || '');
      zroot.dataset.zoteroCollections = 'true';
      croot = this.select('reMarkable folder tree to sync', scope, [['', 'Choose a reMarkable folder…'], ...cpaths], draft.tablet_root || '');
      destination = this.select('Default tablet destination for new papers', scope, [], '');
      const updateDestinations = () => {
        const by = new Map(folders.folders.map(row => [row.id, row]));
        const inside = id => { const seen = new Set(); while (id && !seen.has(id)) { if (id === croot.value) return true; seen.add(id); id = by.get(id)?.parent; } return false; };
        const selected = destination.value || draft.default_folder;
        destination.replaceChildren();
        for (const [key, label] of [['', 'Choose a destination…'], ...cpaths.filter(([id]) => inside(id))]) this.el('option', label, destination, {value: key});
        destination.value = [...destination.options].some(o => o.value === selected) ? selected : croot.value;
      };
      croot.addEventListener('change', updateDestinations); updateDestinations();
      if (this.changingFolder) this.button('Cancel change', scope, () => { this.clearFolderEditor(); this.render(); });
    } else {
      this.el('p', 'Default destination: ' + name(cpaths, config.default_folder, 'Selected folder'), scope, {class: 'hint'});
    }
    const previous = this.latest.connection?.previous || [];
    if (previous.length) {
      const saved = this.el('details', '', scope); this.el('summary', 'Previous folder connections', saved);
      for (const row of previous) this.el('p', `${row.tablet_path || name(cpaths, row.tablet_root, 'Previous reMarkable folder')} · ${row.linked_papers} paper links paused`, saved);
      this.el('p', 'Choose the same Zotero and reMarkable folders again to restore that connection. Its files and page tags are retained.', saved, {class: 'hint'});
    }
    content = this.el('section', '', main, {class: 'card'});
    this.el('h2', 'Intake and search', content);
    const inbox = this.field('Watched ToSort folder (optional)', content, draft.inbox || '');
    this.button('Choose ToSort folder…', content, async () => {
      const {FilePicker} = ChromeUtils.importESModule('chrome://zotero/content/modules/filePicker.mjs');
      const picker = new FilePicker(); picker.init(this.view, 'Choose ToSort folder', picker.modeGetFolder);
      if (await picker.show() === picker.returnOK) { inbox.value = picker.file; dirty(); }
    });
    const automatic = this.checkbox('Sync automatically while this workspace is closed, after I start the saved connection', content, draft.automatic === true);
    const ocr = this.checkbox('Search scanned text and handwriting locally', content, draft.ocr !== false);
    this.el('p', 'Handwriting recognition can misread scientific notation. Your original ink stays intact.', content, {class: 'hint'});
    const section = this.el('details', '', main, {class: 'card'}); this.el('summary', 'Naming templates by document type', section);
    this.el('p', 'Leave blank for Smart naming. Tokens include {author_last}, {year}, {title}, {journal}, {document_type}, and {patent_number}.', section);
    const fields = {};
    for (const [key, label] of Object.entries(this.latest.types)) fields[key] = this.field(label, section, draft.templates?.[key] || '');
    const values = () => ({zotero_root: zroot ? zroot.value : config.zotero_root,
      tablet_root: croot ? croot.value : config.tablet_root, default_folder: destination ? destination.value : config.default_folder,
      inbox: inbox.value, automatic: automatic.checked, ocr: ocr.checked,
      templates: Object.fromEntries(Object.entries(fields).map(([key, field]) => [key, field.value]))});
    const dirty = () => { this.setupDirty = true; this.folderPreview = null; this.setupDraft = values(); this.disable(this.busy); };
    for (const node of [...scope.querySelectorAll('select'), ...content.querySelectorAll('input'), ...section.querySelectorAll('input')]) node.addEventListener('input', dirty);
    if (this.folderPreview) {
      const preview = this.folderPreview, card = this.el('section', '', main, {class: 'card decision'});
      this.el('h2', 'Check your folder selection', card);
      this.el('p', 'Zotero: ' + preview.proposed.zotero_path, card);
      this.el('p', 'reMarkable: ' + preview.proposed.tablet_path, card);
      this.el('p', `Your papers and notes stay in place. ${preview.linked_papers} current paper links will be kept with the previous connection. Automatic sync will be off.`, card);
      if (preview.restored_papers) this.el('p', `${preview.restored_papers} previous paper links will be restored for these folders.`, card);
      for (const [title, names] of [['Zotero subfolders included', preview.zotero_folders], ['reMarkable subfolders included', preview.tablet_folders],
          ['Old Zotero folders kept out of this sync', preview.excluded_zotero_folders], ['Old reMarkable folders kept out of this sync', preview.excluded_tablet_folders]]) {
        if (!names.length) continue;
        const detail = this.el('details', '', card); this.el('summary', `${title} (${names.length})`, detail);
        for (const value of names) this.el('p', value, detail);
      }
      this.el('p', 'Included subfolders mirror each other only after you click Sync now. Previously linked papers stay paused with their previous connection.', card, {class: 'hint'});
      this.button('Save folder change', card, async () => {
        if (!this.folderPreview) {
          const result = await this.action('preview_connection', this.setupDraft, false);
          this.folderPreview = result?.proposed && result?.token ? result : null; this.render(); return;
        }
        await this.action('configure', {...this.setupDraft, confirmation: preview.token}, false);
        this.clearFolderEditor(); this.render();
      }, true);
    } else {
      this.button(this.changingFolder || (!connected && previous.length) ? 'Review folder change' : 'Save setup', main, async () => {
        this.setupDraft = values();
        if (this.changingFolder || (!connected && previous.length)) {
          const result = await this.action('preview_connection', this.setupDraft, false);
          this.folderPreview = result?.proposed && result?.token ? result : null; this.render();
        } else {
          await this.action('configure', this.setupDraft, false); this.clearFolderEditor(); this.render();
        }
      }, true);
    }
  },
  async loadFolders() { this.folderCatalog = await this.action('folders', {}, false); this.refreshCollectionNames(); this.render(); }
};

