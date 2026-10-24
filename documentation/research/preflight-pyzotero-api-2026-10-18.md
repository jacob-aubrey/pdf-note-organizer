# Executed Pyzotero local API preflight

Synthetic disposable Zotero 10.0.6 profile only. Pyzotero 1.16.0. Endpoint `http://127.0.0.1:23129/api/`; per-request timeout 10 seconds. A request hook blocked all other hosts, ports, and path prefixes. No cloud/account/production library calls.

Authorization was simulated by the test harness for the exact application name `Notable disposable preflight`; this does not test a human confirmation dialog. API keys are omitted. The first sandbox socket attempt was blocked before connection. A subsequent attempt passed the first five checks but its full-text result inspection assumed an HTTP response rather than the method's decorated boolean return. That harness assumption was corrected before this run; prior attempt evidence is retained in JSON.

| Check | Result | Detail |
| --- | --- | --- |
| read_seeded_thesis_and_attachments | PASS |  |
| authorize_local_simulated_consent | PASS |  |
| create_thesis_metadata_and_tag | PASS |  |
| update_item_and_reread | PASS |  |
| upload_stored_synthetic_PDF_and_reread | PASS |  |
| set_fulltext_and_reread | PASS |  |

Full results: `preflight-pyzotero-api-2026-10-18.json`. These exercised local API operations do not establish tablet synchronization or plugin interoperability.
