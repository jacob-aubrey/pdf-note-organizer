# Standalone Notable project

This repository retains Notable's original history and standalone files.
The Zotero extension and its tooling now live in the separate
[reMarkable Sync for Zotero repository](https://github.com/jacob-aubrey/remarkable-sync-for-zotero).

Notable does not import the plugin. The plugin carries a pinned snapshot of the
processing modules it needs, with file hashes and an explicit refresh command.
Both repositories can be cloned and used independently.

Source, tests, assets, tools, manual-generation scripts, requirements and
standalone releases retain their familiar paths within this directory. The
source launcher can use a local `.venv` or the existing parent workspace's
environment. In the original split workspace only, the existing parent
`.local-data` library remains recognized so its embedded absolute file paths
continue to work. Fresh checkouts use their own `.local-data` by default.

Generated artifacts, environments, private libraries and credentials are not
committed. The installed executable's data directory is unchanged.
