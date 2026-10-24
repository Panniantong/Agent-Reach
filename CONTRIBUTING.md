# Contributing to Agent Reach

Agent Reach makes it easier for AI agents to reach the internet. Contributions that add or repair a channel are the most useful.

## Development setup

```bash
git clone https://github.com/YOUR_USERNAME/Agent-Reach.git
cd Agent-Reach
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Checks before a PR:

```bash
.venv/bin/ruff check agent_reach tests
.venv/bin/pytest
```

## The channel contract

A channel is a `Channel` subclass in `agent_reach/channels/`, registered in `agent_reach/channels/__init__.py`. It declares:

- `name`, `description`, and `can_handle(url)` so `agent-reach read <url>` can route links to it.
- `level`: `"default"` (works with no setup), `"optional"` (turned on with `agent-reach add`), or `"experimental"` (works but may break any time).
- `actions`: a tuple of `Action`s. Each has a `name`, `help`, `params` (a tuple of `Param(name, help, required, type, default)`), and **ordered** `backends` as `(label, method name)` pairs. The dispatcher tries them in order and falls back on retryable errors. `live_test` holds the params `agent-reach check` uses; a backend passes when it returns at least one item. Slow actions can set `timeout`.
- `tools` (optional): keys of `runtime.tools.TOOLS` that `agent-reach add` installs privately under `~/.agent-reach/tools/`. A tool with `tested` is installed at that version by `add` and `update`; other tools get the newest version allowed by `floor` (minimum version) and `exclude` (known-bad versions). Add a version to `exclude` in a release when an upstream release breaks.
- `prereqs` (optional): machine prerequisites (keys of `runtime.manage.PREREQS`: node, chrome, ffmpeg, uv) that `agent-reach add` installs by itself when missing, without an admin password.
- Login, if the platform needs it:
  - `login_url`: page opened in the Agent Reach browser by `agent-reach login`; the user logs in there.
  - `session` + `login_argv`: a CLI tool whose own login runs with its state in `~/.agent-reach/sessions/<session>/`. `legacy_state` lists old locations `login --import-existing` may copy from.
- `setup_problems()`: what still blocks the channel after its tools are installed (missing key, browser not set up). Shown by `agent-reach doctor`.

Backend methods return items built with `make_item(...)` and raise `ReachError(code, message, hint=...)` with one of `NEED_SETUP`, `NEED_LOGIN`, `UPSTREAM_BROKEN`, `TIMEOUT`, `RATE_LIMITED`, `NOT_FOUND`, `BAD_INPUT`. Hints are written for the agent and must never tell it to log in for the user.

Rules:

- Never read a personal browser's Cookie database or log in on the user's behalf. A user may explicitly authorize a one-time, site-scoped import from a selected connected Browser Bridge profile or local state file. Do not retain a standing export grant or expose credential values.
- Everything a channel stores lives under `~/.agent-reach/`.
- Don't install anything globally; add the tool to `runtime.tools.TOOLS`.

## Dependency locking

Use `constraints.txt` with the development install to keep local and CI dependencies reproducible:

```bash
python -m pip install -c constraints.txt -e ".[dev]"
```

When changing dependency ranges, validate compatible versions, update the pinned entries in `constraints.txt`, then run `pytest -q`, `ruff check agent_reach tests`, and `mypy agent_reach`. Include dependency and validation notes in the pull request.

## Before merging a channel

A new or changed channel must pass a live check on your machine:

```bash
agent-reach add <channel>        # optional / experimental channels
agent-reach login <channel>      # if it needs a login
agent-reach check <channel> --text
```

Paste the `check --text` output into the PR. Also add unit tests under `tests/` (see `tests/test_channel_contracts.py`).

## Pull requests

- Small, focused changes.
- Commit messages in English.
- Update the README channel table if you add a channel or change what it needs.
- Never commit keys, cookies, account names or machine-specific paths.

## Release notes

Every version section in `CHANGELOG.md` starts with a short plain summary for users, in Chinese and in English: what changed for them and anything they must do, in 1 to 4 short points, with no jargon (no file names, commands or internal terms). This text becomes the GitHub release body, which the AI reads from `meta.update.notes` and shows the user when it offers an update. Technical entries follow below the summary.

## Releasing (maintainers)

Users install and update from the latest GitHub release, and 1.5 users are sent to `docs/update.md` on `main`, which points to `docs/install.md`, so the merge and the release must land together:

1. On the release branch, with the needed logins and keys in place, run `python scripts/record_release_acceptance.py` until it prints `release_ready: True` (`--only <channel>` rechecks some channels and keeps the rest). Commit `.github/release-acceptance.json`. Any later change under `agent_reach/` invalidates it; the record is valid for 7 days.
2. Set the version's date in `CHANGELOG.md`.
3. Merge the PR, then immediately tag the merge commit (`git tag vX.Y.Z && git push origin vX.Y.Z`). The release workflow tests, checks the record, and publishes the release with `agent-reach.zip`, which the install and update guides point at. Until it finishes, the guides' download link does not work, so don't leave a gap.

## Reporting issues

Include your OS, `agent-reach doctor --text`, `agent-reach check <channel> --text`, steps to reproduce, and what you expected. Remove personal data first.

---

## 中文简述

- 渠道 = `agent_reach/channels/` 里的一个 `Channel` 子类，在 `channels/__init__.py` 注册。需要声明 `level`、`actions`（`Action`/`Param`、有序后端、`live_test`），按需声明 `tools`、`prereqs`、`login_url` / `session` / `login_argv`、`setup_problems()`。
- 不读取个人浏览器 Cookie 数据库，不替用户登录。用户可明确授权通过指定 Browser Bridge 或本地文件做一次该站登录态导入，不保留长期导出授权；数据只放在 `~/.agent-reach/` 下。
- 新渠道合并前必须在本地跑通 `agent-reach check <channel>` 实测，并把输出贴在 PR 里。
- 提交前运行 `ruff check agent_reach tests` 和 `pytest`。Commit message 用英文。
- 发布说明：`CHANGELOG.md` 每个版本开头先写给用户看的大白话摘要（中文和英文各一份，1 到 4 条，不用术语），这段会成为 GitHub release 正文，AI 提示更新时会讲给用户听。
