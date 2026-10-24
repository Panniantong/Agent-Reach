# Shared dedicated browser

CloakBrowser supplies the browser, and OpenCLI/boss-agent-cli supply website extraction. Reach owns one profile at `~/.agent-reach/browser/profile`, one extension directory, and the existing 600-second idle watcher. There are no per-site Cloak workers or custom DOM/API extraction adapters in Reach.

`add` prepares Node, OpenCLI, the browser and extension. CloakBrowser runs through its public persistent-context launcher in a private tool environment. Its binaries are cached under `~/.agent-reach/cloak-binaries`; installation/download failure falls back to installed Chrome. The next browser action automatically prepares/reopens the same profile. BOSS uses this browser's CDP endpoint. On Windows the Cloak extension is loaded automatically; a system-Chrome fallback may need Web Store installation.

Queries default to headless; human login opens a window using the same profile. Existing local site cookies are reused through a connected official Browser Bridge, read-only and scoped to the requested site. Saved Reach sessions remain usable when no local source is connected. Human login is periodically saved; trusted page input and Reach calls reset idle closure. The official OpenCLI Bridge is supervised with the dedicated browser. Existing user-owned bridges are preserved; version conflicts require user action.

Previous Reach-owned per-site snapshots are merged once without replacing newer shared cookies. Logout/removal clears the retired per-site state too. Chrome fallback is remembered; use `agent-reach browser setup --retry-cloak` after fixing the download connection.

An imported local site's Cookie snapshot replaces that site's cookies, expiring destination-only leftovers while preserving every other site. Failed imports attempt a rollback and leave the saved snapshot intact. Selecting another source preserves explicit logout blocks and manually selected dedicated logins.

This candidate installs official OpenCLI 1.8.7 for a new installation; 1.8.8 is excluded because its unchanged Xiaohongshu default-filter path failed local acceptance. OpenCLI 2.x has not completed business acceptance here. Existing user installations require explicit `--allow-upgrade` before an incompatible copy is replaced. Reach does not edit OpenCLI's source files.

CloakBrowser's wrapper and browser binary have separate licenses; see [upstream binary license](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md). Do not describe the binary as MIT/open-source or promise unrestricted redistribution.

See [install.md](install.md), and the packaged Skill session reference for commands. Local acceptance results are recorded separately from unit-test results.
