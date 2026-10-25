# Retained-source revision verification correction

The original verifier's **7 matching revisions out of 147 received mappings** does not establish missing annotations or lost source archives. Its path layout was correct; it compared two revision receipts that can intentionally diverge after a tag write.

`note_organizer/zotero_bridge.py:490-494` saves and reads the observed source bundle. `:548` records that received revision after native publication. Tag reconciliation then calls `cloud.update_item` and assigns the returned hash to the same mapping revision (`note_organizer/zotero_tags.py:121-124`). That tag-write hash is a later remote metadata receipt; no new downloaded bundle is saved for that write. The renderer's fingerprint deliberately removes tags/pageTags and ignores `.metadata` (`zotero_tags.py:48-55`). Thus an exact local archive named by the later mapping revision is not required to represent the previously rendered annotations.

Read-only inspection used the parent's stopped-state SQLite **copy**, plus JSON manifest metadata and referenced-file existence. No live database, credentials, APIs or product data were modified. All identifiers remain private.

- 147 mappings have received revisions.
- 7 have an exact immutable history manifest for the mapping revision.
- 140 select the latest retained manifest with a different revision; all 140 also have completed tag state, rendered-input receipts and page-map receipts.
- All 147 selected manifests match their mapping's baseline PDF digest and item identity, have valid manifest self-hashes, and reference existing baseline/layer files.
- All 147 selected source revisions have their own immutable history files. Across the local history tree, all 223 history filenames match the `cloud_hash` in their payload.

These observations are consistent with tag-write revision advancement. They do not independently establish current cloud/device content or prove the bytes of every retained PDF/layer file. Manifest self-hashes validate the manifest's internal consistency; reference existence is weaker than full content hashing. No product repair is justified by this mismatch alone.

The pre-update backup deliberately excluded source files. Its previous `missing:139` and zero original-baseline existence count described that exclusion, not production source loss. `verify_sync_state.py` now marks source checks for the known default baseline backup as **not checked**, reports its original-baseline count as null, and has `--baseline-sources-excluded` for equivalent custom backups.

The audit-only verifier now distinguishes mapping-revision history, latest-manifest fallback, source/mapping revision differences, completed tag-state observations and existence of the selected source's own history. It retains true missing-manifest detection. `retained-source-manifest-verification.json` records the corrected counts. The historical `post-086-stopped-verification.json` was preserved as originally produced.

Validation: `python documentation/audits/2026-10-25/verify_manifest_fixtures.py -v` passes five synthetic cases covering exact history, a later post-tag mapping revision, legacy latest-only manifests, intentional backup exclusion, and a genuinely missing manifest. `verify-manifest-fixtures.log` records the result. No product source or package changed.
