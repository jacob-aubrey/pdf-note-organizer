/* Versioned, authorized native library operations. All deletions use Trash. */
async function notableItem(key) {
  if (!/^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$/.test(key || '')) return null;
  const item = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, key);
  if (item) await item.loadAllData();
  return item;
}

async function notableInventory(parent) {
  const items = [parent];
  for (const id of [...parent.getAttachments(true), ...parent.getNotes(true)]) {
    const item = await Zotero.Items.getAsync(id);
    await item.loadAllData();
    items.push(item);
    if (item.isPDFAttachment()) items.push(...item.getAnnotations());
  }
  const inventory = [];
  for (const item of items) {
    await item.loadAllData();
    const row = {key: item.key, version: item.version, itemType: item.itemType,
      title: item.getDisplayTitle(), deleted: !!item.deleted,
      signature: Zotero.Utilities.Internal.md5(JSON.stringify(item.toJSON()))};
    if (item.isFileAttachment()) {
      const path = await item.getFilePathAsync();
      row.fileMD5 = path ? await Zotero.Utilities.Internal.md5Async(path) : '';
    }
    inventory.push(row);
  }
  return inventory.sort((a, b) => a.key.localeCompare(b.key));
}

// One native import per digest may run at a time. Polling keeps the private
// transport cancellable while Zotero completes its ordinary metadata lookup.
var notableBulkJobs = new Map();

function notableDOI(value) {
  return String(value || '').replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '').replace(/^doi:\s*/i, '').trim().toLowerCase();
}

function notableTitleMatches(candidate, title) {
  // Bibliography text is not evidence of this document's identity. Compare
  // only its independently extracted front title, retaining word boundaries.
  const words = value => new Set(String(value || '').toLowerCase().match(/[\p{L}\p{N}]+/gu) || []);
  const left = words(candidate), right = words(title);
  if (Math.min(left.size, right.size) < 3) return false;
  return [...left].filter(word => right.has(word)).length / Math.max(left.size, right.size) >= .72;
}

async function notableBulkImport(data) {
  const collection = await Zotero.Collections.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, data.collection);
  if (!collection || collection.deleted) throw new Error('The destination collection changed. Scan again.');
  const source = Zotero.File.pathToFile(data.source), root = Zotero.File.pathToFile(data.root);
  if (!root.isDirectory() || !root.contains(source, true) || !/\.(pdf|docx|pptx)$/i.test(source.leafName)
      || await Zotero.Utilities.Internal.md5Async(source.path) !== data.md5) throw new Error('The source file changed. Scan again.');
  let attachment = data.existing ? await notableItem(data.existing) : null;
  if (data.existing && (!attachment || attachment.deleted || !attachment.isFileAttachment()
      || await Zotero.Utilities.Internal.md5Async(await attachment.getFilePathAsync()) !== data.existing_md5)) {
    throw new Error('The matching Zotero PDF changed. Scan again.');
  }
  const marker = 'Notable bulk import: ' + data.digest;
  if (!attachment) {
    // Recover a commit whose response was lost. No filename or DOI guessing.
    const matches = [];
    for (const item of await Zotero.Items.getAll(Zotero.Libraries.userLibraryID, false, false)) {
      if (!item.deleted && item.isFileAttachment() && item.getNote().includes(marker)) matches.push(item);
    }
    if (matches.length > 1) throw new Error('Several stored copies claim this import. Review them in Zotero.');
    if (matches.length) {
      attachment = matches[0];
      if (await Zotero.Utilities.Internal.md5Async(await attachment.getFilePathAsync()) !== data.md5) {
        throw new Error('The previously imported PDF changed. Both copies were retained.');
      }
    }
  }
  let parent = attachment?.parentKey ? await notableItem(attachment.parentKey) : null;
  let newMetadata = null;
  if (!attachment) {
    // DOI translators return metadata without saving another reference or PDF.
    // Accept a candidate only when its title matches the source's own title.
    let metadata = null;
    if (data.lookup && !Zotero.HTTP.browserIsOffline()) {
      for (const doi of (data.dois || []).slice(0, 3)) {
        try {
          const translate = new Zotero.Translate.Search(); translate.setIdentifier({DOI: doi});
          const translators = await translate.getTranslators();
          if (!translators.length) continue;
          translate.setTranslator(translators);
          const records = await translate.translate({libraryID: false, saveAttachments: false});
          const candidate = records[0];
          if (candidate && notableTitleMatches(candidate.title, data.identity_title || data.title)
              && notableDOI(candidate.DOI) === notableDOI(doi)) { metadata = candidate; break; }
        } catch (_) { /* A failed citation lookup does not reject a readable PDF. */ }
      }
    }
    if (metadata) {
      const candidates = [];
      for (const item of await Zotero.Items.getAll(Zotero.Libraries.userLibraryID, false, false)) {
        if (!item.deleted && item.isRegularItem() && notableDOI(item.getField('DOI')) === notableDOI(metadata.DOI)) candidates.push(item);
      }
      if (candidates.length > 1 || (candidates.length && candidates[0].getAttachments().some(id => Zotero.Items.get(id).isPDFAttachment()))) {
        throw new Error('A reference with this DOI already has a PDF, or several references match. Review the versions.');
      }
      if (candidates.length) parent = candidates[0];
      else {
        // Store the file first. A failed copy must not leave an empty citation.
        newMetadata = metadata;
      }
    }
    attachment = await Zotero.Attachments.importFromFile({file: source.path, libraryID: Zotero.Libraries.userLibraryID,
      ...(parent ? {parentItemID: parent.id} : {collections: [collection.id]}), title: source.leafName});
    attachment.setNote('<p>' + marker + '</p>'); await attachment.saveTx();
    if (await Zotero.Utilities.Internal.md5Async(await attachment.getFilePathAsync()) !== data.md5) {
      throw new Error('The stored copy did not verify. The original Windows file was retained.');
    }
  }
  // RecognizeDocument creates a parent before its result can be checked.
  // Reuse the metadata-only DOI translators above; otherwise retain a local
  // document reference for manual review rather than risking a cited identity.
  const citationUnavailable = !parent && !newMetadata && !!data.lookup;
  if (!parent) {
    // A shutdown between these two saves must not leave an empty duplicate
    // reference. File storage has finished; only metadata is transactional.
    await Zotero.DB.executeTransaction(async () => {
      parent = new Zotero.Item(newMetadata?.itemType || 'document'); parent.libraryID = Zotero.Libraries.userLibraryID;
      if (newMetadata) parent.fromJSON(newMetadata);
      else parent.setField('title', String(data.title || source.leafName).slice(0, 1000));
      parent.setCollections([collection.id]); await parent.save();
      attachment.parentID = parent.id; attachment.setCollections([]); await attachment.save();
    });
  }
  parent.addToCollection(collection.id); await parent.saveTx();
  const issues = [];
  if (citationUnavailable) issues.push('Citation metadata could not be verified against this document\'s own title. The local document was imported; review its citation metadata in Zotero.');
  const doi = notableDOI(parent.getField('DOI'));
  if (doi) {
    for (const item of await Zotero.Items.getAll(Zotero.Libraries.userLibraryID, false, false)) {
      if (item.id !== parent.id && !item.deleted && item.isRegularItem() && notableDOI(item.getField('DOI')) === doi) {
        issues.push('Another Zotero reference has the same DOI; check the references or versions.'); break;
      }
    }
  }
  return {attachment: attachment.key, parent: parent.key, data: attachment.toJSON(), reference: parent.toJSON(),
    path: await attachment.getFilePathAsync(), issues};
}

function notableRegisterLibraryEndpoint(Base) {
  notableEndpoints['/api/notable/action'] = class extends Base {
    supportedMethods = ['POST'];
    supportedDataTypes = ['application/json'];
    async run(request) {
      const reply = (status, value) => [status, 'application/json', JSON.stringify(value)];
      if (!request.headers.get('Zotero-Server-ID')) return reply(428, {error: 'Select a Zotero instance'});
      const data = typeof request.data === 'string' ? JSON.parse(request.data) : request.data;
      if (data.action === 'bulk_import' || data.action === 'bulk_import_status') {
        if (!/^[a-f0-9]{64}$/.test(data.digest || '')) return reply(400, {error: 'Invalid import identity'});
        if (!/^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$/.test(data.collection || '')) return reply(400, {error: 'Choose a collection'});
        // Different destination choices share a digest lock. An import which
        // outlives Stop may finish before the next destination is applied.
        const key = data.digest;
        let group = notableBulkJobs.get(key);
        if (!group && data.action === 'bulk_import') {
          group = {tail: Promise.resolve(), jobs: new Map()}; notableBulkJobs.set(key, group);
        }
        let job = group?.jobs.get(data.collection);
        const signature = data.action === 'bulk_import' ? JSON.stringify(data) : null;
        if (job && !job.pending && signature && job.signature !== signature) {
          group.jobs.delete(data.collection); job = null;
        }
        if (!job && data.action === 'bulk_import') {
          job = {pending: true, signature}; group.jobs.set(data.collection, job);
          group.tail = group.tail.catch(() => {}).then(() => notableBulkImport(data)).then(result => { job.result = result; job.pending = false; }, error => {
            job.error = error.message; job.pending = false;
          });
        }
        if (!job) return reply(409, {error: 'This import was interrupted. Scan the folder again.'});
        if (job.pending) return reply(200, {pending: true});
        if (job.error) { group.jobs.delete(data.collection); return reply(200, {error: job.error}); }
        // Keep completed results for a lost HTTP response or repeated poll.
        // Different collection choices have separate, revalidated operations.
        if (notableBulkJobs.size > 1000) {
          for (const [oldKey, old] of notableBulkJobs) {
            if (oldKey !== key && [...old.jobs.values()].every(value => !value.pending)) { notableBulkJobs.delete(oldKey); break; }
          }
        }
        return reply(200, job.result);
      }
      if (data.action === 'catalog') {
        const attachments = [], parents = {};
        const items = (await Zotero.Items.getAll(Zotero.Libraries.userLibraryID, false, false))
          .filter(item => !item.deleted && (item.isRegularItem() || item.isFileAttachment()));
        // Zotero's existing batch loader avoids thousands of sequential database
        // reads on a cold library. Annotation bodies are not catalog entries.
        await Zotero.Items.loadDataTypes(items);
        for (const item of items) {
          if (item.isRegularItem()) { parents[item.key] = item.toJSON(); continue; }
          if (!item.isFileAttachment()) continue;
          const path = await item.getFilePathAsync();
          if (!path || !/\.(pdf|docx|pptx)$/i.test(path)) continue;
          attachments.push({data: item.toJSON(), path});
          if (item.parentKey && !parents[item.parentKey]) {
            const parent = Zotero.Items.getByLibraryAndKey(Zotero.Libraries.userLibraryID, item.parentKey);
            if (parent && !parent.deleted) parents[item.parentKey] = parent.toJSON();
          }
        }
        return reply(200, {attachments, parents, data_directory: Zotero.DataDirectory.dir});
      }
      if (data.action === 'reparent') {
        const item = await notableItem(data.key), parent = await notableItem(data.parent);
        if (!item || item.deleted || !item.isFileAttachment() || !parent || parent.deleted || !parent.isRegularItem()
            || item.libraryID !== parent.libraryID) return reply(409, {error: 'Attachment or destination unavailable'});
        const previous = item.parentKey || '';
        const path = await item.getFilePathAsync();
        if (!path || await Zotero.Utilities.Internal.md5Async(path) !== data.md5
            || ![data.previous_parent || '', parent.key].includes(previous)) return reply(409, {error: 'Attachment changed'});
        if (previous !== parent.key) { item.parentKey = parent.key; await item.saveTx(); }
        if (item.parentKey !== parent.key || await Zotero.Utilities.Internal.md5Async(await item.getFilePathAsync()) !== data.md5) {
          return reply(409, {error: 'Reparent verification failed'});
        }
        return reply(200, {key: item.key, parent: parent.key});
      }
      if (data.action === 'inventory') {
        const parent = await notableItem(data.parent);
        if (!parent || !parent.isRegularItem()) return reply(404, {error: 'Reference unavailable'});
        return reply(200, {inventory: await notableInventory(parent)});
      }
      if (data.action === 'prepare_upload') {
        const item = await notableItem(data.key);
        if (!item || item.deleted || !item.isFileAttachment() || !item.isStoredFileAttachment()) {
          return reply(409, {error: 'Stored attachment unavailable'});
        }
        if (typeof data.md5 !== 'string' || !/^(?:[a-f0-9]{32})?$/.test(data.md5)) return reply(400, {error: 'Invalid PDF hash'});
        const path = await item.getFilePathAsync();
        const actual = path && await IOUtils.exists(path) ? await Zotero.Utilities.Internal.md5Async(path) : '';
        if (actual !== data.md5) return reply(409, {error: 'PDF changed'});
        const remote_md5 = item.attachmentSyncedHash || '';
        const remote_mtime = item.attachmentSyncedModificationTime || 0;
        // The local API authorizes against attachmentSyncedHash, including
        // If-None-Match:* for unsynced imports which already have local bytes.
        // Keep preparation read-only so a lost response cannot turn a local
        // seed into a fictitious account receipt before Python persists it.
        const verified = path && await IOUtils.exists(path) ? await Zotero.Utilities.Internal.md5Async(path) : '';
        if (verified !== data.md5) return reply(409, {error: 'PDF changed'});
        return reply(200, {md5: data.md5, authorization_md5: item.attachmentSyncedHash || '', remote_md5, remote_mtime});
      }
      if (data.action === 'finish_upload') {
        const item = await notableItem(data.key);
        if (!item || item.deleted || !item.isFileAttachment() || !item.isStoredFileAttachment()) {
          return reply(409, {error: 'Stored attachment unavailable'});
        }
        if (typeof data.md5 !== 'string' || !/^[a-f0-9]{32}$/.test(data.md5)
            || typeof data.remote_md5 !== 'string' || !/^(?:[a-f0-9]{32})?$/.test(data.remote_md5)
            || !Number.isSafeInteger(data.remote_mtime) || data.remote_mtime < 0) {
          return reply(400, {error: 'Invalid upload receipt'});
        }
        const path = await item.getFilePathAsync();
        if (!path || !await IOUtils.exists(path) || await Zotero.Utilities.Internal.md5Async(path) !== data.md5) {
          return reply(409, {error: 'PDF changed'});
        }
        // Account upload uses this previous remote hash for If-Match. The
        // local API's hash describes local bytes and must not replace it.
        item.attachmentSyncedHash = data.remote_md5 || null;
        item.attachmentSyncedModificationTime = data.remote_mtime;
        item.attachmentSyncState = 'to_upload';
        await item.saveTx();
        if (await Zotero.Utilities.Internal.md5Async(path) !== data.md5) return reply(409, {error: 'PDF changed'});
        return reply(200, {md5: data.md5, sync_state: 'to_upload'});
      }
      if (data.action === 'rename') {
        const item = await notableItem(data.key);
        if (!item || item.deleted || !item.isFileAttachment()) return reply(404, {error: 'Attachment unavailable'});
        const name = data.filename;
        if (typeof name !== 'string' || name.length > 240 || /[\\/\x00-\x1f]/.test(name)
            || !/\.(pdf|docx|pptx)$/i.test(name)) return reply(400, {error: 'Invalid filename'});
        const path = await item.getFilePathAsync();
        if (!path || await Zotero.Utilities.Internal.md5Async(path) !== data.md5) return reply(409, {error: 'File changed'});
        if (await item.renameAttachmentFile(name, {overwrite: false, unique: false, updateTitle: false}) !== true) {
          return reply(409, {error: 'Filename unavailable'});
        }
        return reply(200, {key: item.key, filename: name});
      }
      if (data.action === 'adopt') {
        const item = await notableItem(data.key);
        if (!item || item.deleted || !item.isPDFAttachment() || item.parentKey !== data.parent
            || !/^Notable pilot: [a-f0-9]{64}$/.test(data.marker || '')) return reply(409, {error: 'Source link changed'});
        const path = await item.getFilePathAsync();
        if (!path || await Zotero.Utilities.Internal.md5Async(path) !== data.md5) return reply(409, {error: 'Source bytes changed'});
        const independent = item.getAnnotations().filter(a => !a.deleted && !a.annotationIsExternal).length;
        if (independent || item.attachmentLinkMode === Zotero.Attachments.LINK_MODE_LINKED_FILE) return reply(200, {adopted: false, native: independent});
        if (item.getNote().includes('Notable pilot:') && !item.getNote().includes(data.marker)) return reply(409, {error: 'Another managed link owns this PDF'});
        if (!item.getNote().includes(data.marker)) {
          item.setNote(item.getNote() + '<p>' + data.marker + '</p>');
          await item.saveTx();
        }
        return reply(200, {adopted: true, native: 0});
      }
      if (data.action === 'trash') {
        const parent = await notableItem(data.parent), view = await notableItem(data.attachment);
        if (!parent || !view || !parent.isRegularItem() || view.parentKey !== parent.key
            || !view.getNote().includes('Notable pilot:')) return reply(409, {error: 'Link changed'});
        if (!['pdf_only', 'everything'].includes(data.choice)) return reply(400, {error: 'Choose a deletion scope'});
        const targets = data.choice === 'everything' ? [parent] : [view];
        if (data.choice === 'pdf_only' && data.source_attachment) {
            const source = await notableItem(data.source_attachment);
          if (!source || source.parentKey !== parent.key
              || !view.getNote().includes('Notable source attachment: ' + source.key)) return reply(409, {error: 'Source link changed'});
          targets.push(source);
        }
        if (targets.every(item => item.deleted)) return reply(200, {status: 'trashed', keys: targets.map(i => i.key)});
        let stale = false;
        await Zotero.DB.executeTransaction(async () => {
          if (JSON.stringify(await notableInventory(parent)) !== JSON.stringify(data.inventory)) { stale = true; return; }
          await Zotero.Items.trash(targets.map(item => item.id));
        });
        return reply(stale ? 409 : 200, stale ? {error: 'Reference or notes changed'} : {status: 'trashed', keys: targets.map(i => i.key)});
      }
      return reply(400, {error: 'Unknown library action'});
    }
  };
}
