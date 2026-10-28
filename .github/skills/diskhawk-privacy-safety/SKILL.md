---
name: diskhawk-privacy-safety
description: "Use when handling DiskHawk reports, configuration profiles, private paths, Docker contexts, shell startup files, or safety/privacy review of DiskHawk changes."
---

# DiskHawk privacy and safety

## Before changing data boundaries

1. Read `docs/privacy.md` and the SRS security/report requirements.
2. Keep default reports aggregate-only and shorten home paths to `~`.
3. Never read or export environment values, `.env` contents, credentials,
   keychain data, file contents, Docker logs, container environment, or mounts.
4. Require interactive confirmation for detailed filenames; require an explicit
   named opt-in in non-interactive mode.
5. Treat profiles as untrusted JSON: validate the entire schema before writes,
   preview changes, confirm, back up existing settings, and replace atomically.
6. Treat the configured Docker context as potentially remote. Use only bounded,
   read-only commands; never prune, stop, remove, or start Docker resources.
7. Treat shell startup files as user-owned. Check command/alias/function
   conflicts, back up before edits, use exact managed markers, and preserve
   unrelated content on uninstall.
8. Test redaction and integration changes with temporary fixtures. Do not inspect
   personal files or alter actual user shell configuration during automated
   checks.
