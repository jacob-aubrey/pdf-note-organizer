# Verified changeset

- Verified source, tests and audit-evidence commit: `16354cec48d647e7c0af3e0d633c70e21d8d42fd`.
- Branch: `main`; tree: `6274a8d8fc1e18db84ffbc83ffe0e637cddcf388`.
- Starting revision: `2f06ac2bed28a569bed56a64f8ceccb47f2e886e`.
- SHA-256 of `git diff --binary <starting-revision> <verified-commit>`: `7de7fc488eb9cfd361ea5135fdc2bfa7c1a48b6727121c413bd4677827855339`.
- Working tree was clean immediately after that commit. This final documentation receipt and ledger refresh follow it in a documentation-only commit; application/test/package code is unchanged.
- Exact tested and installed XPI/helper hashes, runtime identity and source parity are in `package-094-verification.json`, `installed-094-verification.json` and `loaded-094-postrepeat-*.json`.
- Both configured production syncs completed before commit. The repeat changed zero native item keys/versions, selected mappings, publication receipts, review database hashes or configuration hashes.
- XPI/helper binaries and private package/state/grant/document/log snapshots remain local and ignored. No credentials, research document contents or private database snapshots are committed. Public bounded test/build outputs and sanitized structural evidence are intentional audit records.
- The unmodified console-text capture is retained privately; only trailing UI whitespace was normalized in its committed text copy.

Reproduce source identity with `git show <verified-commit>` and the recorded ledger. Ledger hashes describe the exact audited working-tree bytes; Git's configured newline normalization can change text-file bytes on another checkout without changing compiled Python code.
