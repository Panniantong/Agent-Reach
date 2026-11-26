# Sessions and the Dedicated Browser

Read this page when the user wants to log in, log out, switch accounts, or a result returns `NEED_LOGIN`.

## Dedicated browser

- All browser channels share one dedicated browser profile, separate from the user's everyday Chrome. The program does not close or modify their everyday browser.
- CloakBrowser is preferred. If downloading or installing it fails, Agent Reach uses the installed Chrome and remembers that fallback instead of downloading it again every time. Retry after the network is restored with `agent-reach browser setup --retry-cloak`.
- `agent-reach add <channel>` prepares Node, OpenCLI, the browser engine and extension. It installs versions tested for this release. On Windows, using Chrome as a fallback may require the user to click "Add to Chrome" once.
- The browser is headless by default. Only `agent-reach login <channel>` opens a window. While it is open, queries use that window and do not close it; wait for the user to say they are finished logging in before checking again. After the window closes, later queries return to headless mode.
- The browser closes after 10 idle minutes and reopens on the next call. Real page actions and Reach calls reset the timer. During login it saves periodically, so the user does not need to close the window.
- Calls can run in parallel: at most 2 per platform and 4 across all platforms. Additional calls wait in line for up to 2 minutes, then return `BUSY`. Searches on the same platform start at least 10 seconds apart. Opening the login window, logging out, or reinstalling the browser waits for running queries to finish.
- `agent-reach browser status` checks the status, `browser setup` prepares the engine and extension, and `browser stop` closes the browser managed by the program.

## Reusing an existing login

1. The first time a site is used, if the user's Chrome is connected to the OpenCLI extension, Agent Reach copies that site's login (only that site's cookies) to the dedicated browser once. It does not copy the whole browser directory, other sites, or the password store, and it does not change the source browser.
2. After a successful copy, the saved session is reused without another time-based copy. Cookies do not prove that a login is still valid; check the result of a real action.
3. If the user's Chrome is not connected to the extension, do not promise automatic reuse or infer that the user is logged out. Use the session already saved by Reach.
4. If several local browsers are logged in to the site, `agent-reach browser profiles` lists the sources and `agent-reach browser use <ID>` selects one. The program does not switch randomly.
5. `agent-reach login <channel> --import-existing` explicitly copies the site's login again without opening a window. If no login can be copied, or the OpenCLI Bridge is not running, it returns `NEED_SETUP` and leaves the saved session unchanged.
6. After the user logs in through the dedicated window or runs `logout` / `remove`, the program no longer copies that login automatically, so a logged-out session is not restored.

## When the user needs to log in

- Ask the user to log in only when an action actually returns `NEED_LOGIN` and the remaining task needs that path. A login button elsewhere on the page is not enough.
- `agent-reach login <channel>` opens the dedicated browser at the site's login page. The user completes the login themselves. Do not log in for them, ask for their password, or print cookies.
- Follow any next steps in the result's `next` field. Some native-tool channels, such as Xueqiu, need `agent-reach login <channel> --sync` after login.
- After the user finishes, rerun the original action to verify it.

## Platform differences

- Boss Zhipin's in-site search uses OpenCLI and the shared dedicated browser. If a job detail incorrectly reports that login is required because of an upstream issue, do not ask the user to log in repeatedly.
- Bilibili passes an existing login to Bilibili's official command-line tool only when reading subtitles. Normal searches do not prepare a browser.
- Xueqiu community actions require login. Sessions expire within a few hours, so repeat the login steps after expiration.

## Logging out and removing data

- `agent-reach logout <channel>` clears that site's login from the dedicated browser and the channel's own state, while keeping other sites.
- `agent-reach remove <channel>` removes the channel and clears that site's login and stored data, while keeping other sites. If cleanup fails, the channel record stays and an error is returned so the user can retry.
- After either command, that site's login is no longer copied automatically.
- **Structured data cleanup**: Xueqiu quotes, V2EX topics and replies, and GitHub repositories and issues have already been cleaned up.
