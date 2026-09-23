"""On-demand NGA exports with atomic, per-page checkpoints."""

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from agent_reach.channels.nga import NGABrowser, thread_url, validate_page


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def task_lock(directory: Path):
    """OS locks are released even when interrupted, so resume needs no stale-lock cleanup."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            if not stream.read(1):
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("此 NGA 导出任务正在运行") from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError("此 NGA 导出任务正在运行") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _save(directory: Path, state: dict) -> None:
    atomic_write(directory / "state.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def _load(directory: Path) -> dict:
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("无法识别 NGA 续传文件版本")
    state["url"] = thread_url(state.get("url", ""), 1)
    if (type(state.get("start_page")) is not int or state["start_page"] < 1
            or type(state.get("only_author")) is not bool
            or type(state.get("all_pages")) is not bool
            or not isinstance(state.get("pages"), dict)):
        raise ValueError("NGA 续传参数损坏")
    end = state.get("end_page")
    if end is not None and (type(end) is not int or end < state["start_page"]):
        raise ValueError("NGA 续传页范围无效")
    meta = state.get("metadata")
    if meta is not None:
        if (not isinstance(meta, dict) or not meta.get("author_uid")
                or not isinstance(meta.get("title"), str)
                or type(meta.get("total_pages")) is not int or meta["total_pages"] < 1):
            raise ValueError("NGA 续传元信息损坏")
    elif state["pages"]:
        raise ValueError("NGA 续传文件缺少元信息")
    for number, data in state["pages"].items():
        if not number.isdigit() or str(int(number)) != number:
            raise ValueError("NGA 续传页码无效")
        page = int(number)
        if page < state["start_page"] or meta is None or page > _target_end(state):
            raise ValueError("NGA 续传数据超出任务范围")
        validate_page(data, thread_url(state["url"], page))
    return state


def _target_end(state: dict) -> int:
    return (state["metadata"]["total_pages"] if state["all_pages"]
            else state["end_page"] or state["start_page"])


def export_thread(url: str | None = None, *, directory: Path, resume: bool = False,
                  start_page: int | None = None, end_page: int | None = None,
                  all_pages: bool = False, only_author: bool = False,
                  max_pages: int = 100, profile: str | None = None,
                  interval: float = 1.0, browser=None, progress=None) -> dict:
    """Freeze the requested range at start; resume fills holes without refetching saved pages.

    `max_pages` is a per-invocation budget, excluding the page-one metadata lookup.
    A capped run returns complete=False and can be continued with --resume.
    """
    if type(max_pages) is not int or max_pages < 1 or not 0 <= interval <= 60:
        raise ValueError("max_pages 必须为正整数，interval 必须在 0–60 秒之间")
    if resume and (url is not None or start_page is not None or end_page is not None
                   or all_pages or only_author):
        raise ValueError("续传时不能更改 URL、页范围或楼主筛选；请创建新任务")
    directory = Path(directory)
    with task_lock(directory):
        if resume:
            state = _load(directory)
            if profile is not None and state.get("profile") != profile:
                raise ValueError("续传请使用原 Chrome profile；更换账号请创建新任务")
        else:
            if (directory / "state.json").exists():
                raise ValueError("任务目录已存在，请用 --resume 续传或换一个目录")
            canonical = thread_url(url or "")
            start = start_page if start_page is not None else int(
                parse_qs(urlsplit(canonical).query)["page"][0])
            if type(start) is not int or start < 1:
                raise ValueError("start_page 必须为正整数")
            if end_page is not None and (type(end_page) is not int or end_page < start):
                raise ValueError("end_page 不能小于 start_page")
            if all_pages and end_page is not None:
                raise ValueError("--all-pages 和 --end-page 不能同时使用")
            state = dict(schema_version=1, url=thread_url(canonical, 1), start_page=start,
                         end_page=end_page, all_pages=all_pages, only_author=only_author,
                         profile=profile or os.environ.get("OPENCLI_PROFILE"), metadata=None,
                         pages={}, started_at=datetime.now(timezone.utc).isoformat(),
                         last_error=None)
            _save(directory, state)
        reader = browser or NGABrowser(profile=state.get("profile"))
        first = None
        fetched = 0
        attempted_page = 1
        try:
            if state["metadata"] is None:
                first = validate_page(reader.read_page(state["url"]), state["url"])
                original = next((p for p in first["posts"] if p["pid"] == "0"), None)
                if original is None:
                    raise ValueError("第一页未找到主帖，无法确认楼主 ID")
                state["metadata"] = dict(title=first["title"], author=original["author"],
                                         author_uid=original["author_uid"],
                                         total_pages=first["total_pages"])
                _save(directory, state)
            end = _target_end(state)
            if state["start_page"] > state["metadata"]["total_pages"] or end > state["metadata"]["total_pages"]:
                raise ValueError("请求页码超出帖子的总页数")
            for page in range(state["start_page"], end + 1):
                if str(page) in state["pages"]:
                    continue
                if fetched >= max_pages:
                    break
                attempted_page = page
                if first is not None and page == 1:
                    data = first
                else:
                    if first is not None or fetched:
                        time.sleep(interval)
                    page_url = thread_url(state["url"], page)
                    data = validate_page(reader.read_page(page_url), page_url)
                previous_ids = {p["pid"] for saved in state["pages"].values() for p in saved["posts"]}
                if previous_ids and all(p["pid"] in previous_ids for p in data["posts"]):
                    raise ValueError("翻页返回了重复内容；停止读取，避免把错误页记为成功")
                state["pages"][str(page)] = data
                state["last_error"] = None
                _save(directory, state)
                fetched += 1
                if progress:
                    progress(page, end)
        except (Exception, KeyboardInterrupt) as exc:
            state["last_error"] = {"page": attempted_page, "type": type(exc).__name__}
            _save(directory, state)
            raise
        finally:
            reader.close()
        result = build_result(state)
        atomic_write(directory / "export.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        atomic_write(directory / "export.md", to_markdown(result))
        return result


def build_result(state: dict) -> dict:
    end = _target_end(state)
    missing = next((p for p in range(state["start_page"], end + 1)
                    if str(p) not in state["pages"]), None)
    posts, seen = [], set()
    for page in sorted(state["pages"], key=int):
        for post in state["pages"][page]["posts"]:
            if post["pid"] in seen:
                continue
            seen.add(post["pid"])
            if state["only_author"] and post["author_uid"] != state["metadata"]["author_uid"]:
                continue
            posts.append({**{k: v for k, v in post.items() if k != "content_present"},
                          "page": int(page)})
    return dict(schema_version=1, url=state["url"], **state["metadata"],
                start_page=state["start_page"], end_page=end, only_author=state["only_author"],
                pages_read=sorted(map(int, state["pages"])), complete=missing is None,
                next_page=missing, exported_at=datetime.now(timezone.utc).isoformat(), posts=posts)


def _literal(value: str) -> str:
    # Forum content stays text, not active HTML or Markdown images/scripts.
    import html
    import re
    return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", html.escape(value, quote=False))


def _link(value: str) -> str | None:
    from urllib.parse import quote
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    return quote(value, safe=":/?=&%#@+~;,")


def to_markdown(result: dict) -> str:
    lines = ["# " + _literal(result["title"]), "", f"来源：<{result['url']}>", "",
             f"楼主：{_literal(result['author'])}（UID {result['author_uid']}）",
             f"范围：第 {result['start_page']}–{result['end_page']} 页；"
             f"已读取 {len(result['pages_read'])} 页；仅楼主：{result['only_author']}",
             "状态：" + ("指定范围已完成" if result["complete"] else f"未完成，从第 {result['next_page']} 页续传"), ""]
    for post in result["posts"]:
        lines += [f"## #{post['floor']} · {_literal(post['author'])} · {_literal(post['created_at'])}",
                  "", _literal(post["text"]), ""]
        for image in post["images"]:
            url = _link(image["url"])
            if url:
                lines += [f"[图片：{_literal(image.get('alt') or '查看原图')}](<{url}>)", ""]
        for link in post["links"]:
            url = _link(link["url"])
            if url:
                lines += [f"[{_literal(link.get('text') or '链接')}](<{url}>)", ""]
        if post.get("edited"):
            lines += [_literal(post["edited"]), ""]
    return "\n".join(lines) + "\n"


def add_parser(subparsers) -> None:
    parser = subparsers.add_parser("nga", help="Read/export NGA via your Chrome session")
    commands = parser.add_subparsers(dest="nga_command", required=True)
    read = commands.add_parser("read", help="Export a thread, page range, or original author")
    read.add_argument("url", nargs="?")
    read.add_argument("--only-author", action="store_true", help="Only the thread starter's posts")
    read.add_argument("--start-page", type=int)
    end = read.add_mutually_exclusive_group()
    end.add_argument("--end-page", type=int)
    end.add_argument("--all-pages", action="store_true", help="Read through the last page at task start")
    read.add_argument("--max-pages", type=int, default=100, help="Per-run page budget (default 100)")
    read.add_argument("--interval", type=float, default=1.0, help="Seconds between pages (default 1)")
    read.add_argument("--profile", help="OpenCLI Chrome profile alias")
    task = read.add_mutually_exclusive_group()
    task.add_argument("--state-dir", type=Path, help="New checkpoint/export directory")
    task.add_argument("--resume", type=Path, help="Resume a previous checkpoint directory")
    read.add_argument("--format", choices=["json", "markdown"], default="markdown")
    read.add_argument("-o", "--output", type=Path)


def run(args: argparse.Namespace) -> None:
    directory = args.resume or args.state_dir
    try:
        if directory is None:
            canonical = thread_url(args.url or "")
            tid = parse_qs(urlsplit(canonical).query)["tid"][0]
            directory = Path.home() / ".agent-reach" / "exports" / f"nga-{tid}-{uuid.uuid4().hex[:8]}"
        if args.output and args.output.resolve() in {
            (directory / "state.json").resolve(), (directory / ".lock").resolve()
        }:
            raise ValueError("输出文件不能覆盖任务的 state.json 或锁文件")
        print(f"NGA 任务目录：{directory}", file=sys.stderr)
        result = export_thread(args.url, directory=directory, resume=bool(args.resume),
                               start_page=args.start_page, end_page=args.end_page,
                               all_pages=args.all_pages, only_author=args.only_author,
                               max_pages=args.max_pages, interval=args.interval, profile=args.profile,
                               progress=lambda p, end: print(f"已保存第 {p}/{end} 页", file=sys.stderr))
        content = (json.dumps(result, ensure_ascii=False, indent=2) + "\n"
                   if args.format == "json" else to_markdown(result))
        if args.output:
            atomic_write(args.output, content)
        else:
            print(content, end="")
        if not result["complete"]:
            print(f"已达到本次页数上限。续传：agent-reach nga read --resume '{directory}'", file=sys.stderr)
            raise SystemExit(3)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"NGA 导出失败：{exc}", file=sys.stderr)
        if directory and (directory / "state.json").exists():
            print(f"进度已保留。续传：agent-reach nga read --resume '{directory}'", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print(f"已中断，进度目录：{directory}", file=sys.stderr)
        raise SystemExit(130) from None
