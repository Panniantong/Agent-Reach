"""Explicit, hash-guarded compatibility patches. Never run during search."""
import hashlib
import json
from pathlib import Path

from .result import NEED_SETUP, ReachError
from .tools import resolve


def package_root():
    exe = resolve("opencli")
    if not exe:
        raise ReachError(NEED_SETUP, "OpenCLI is not installed")
    entry = Path(exe).resolve()
    for parent in list(entry.parents)[:5]:
        for candidate in (parent, parent / "node_modules" / "@jackwener" / "opencli"):
            manifest = candidate / "package.json"
            if manifest.is_file() and json.loads(manifest.read_text()).get("name") == "@jackwener/opencli":
                return candidate
    raise ReachError(NEED_SETUP, "Cannot locate OpenCLI package from executable")


def repair(root=None):
    root = Path(root) if root is not None else package_root()
    if json.loads((root / "package.json").read_text()).get("version") != "1.8.8":
        raise ReachError(NEED_SETUP, "Compatibility patches only verified for OpenCLI 1.8.8; no files changed")
    specs = [
        ("clis/xiaohongshu/search.js", "e96c759f2a3e5bf018dfb7ee4456056ddc08b1274c38b2fc1e4a62b1ad1705bb", [
            ("(max 5s)", "(max 20s)"),
            ("resolve('timeout'); }, 5000);", "resolve('timeout'); }, 20000);"),
            ("const CONTENT_WAIT_SECONDS = 5;", "const CONTENT_WAIT_SECONDS = 20;")]),
    ]
    changes = []
    for relative, original_sha, edits in specs:
        target = root / relative
        current = target.read_text(encoding="utf-8")
        original = current
        for old, new in edits:
            if old not in original:
                original = original.replace(new, old)
        if hashlib.sha256(original.encode()).hexdigest() != original_sha:
            raise ReachError(NEED_SETUP, f"Unrecognized adapter content: {relative}; no files changed")
        desired = original
        for old, new in edits:
            desired = desired.replace(old, new)
        changes.append((target, current, desired))
    # Validate every file before writing any. Keep a rollback copy next to each adapter.
    written = []
    try:
        for target, current, desired in changes:
            if current != desired:
                backup = target.with_suffix(target.suffix + ".before-reach")
                if not backup.exists():
                    backup.write_text(current, encoding="utf-8")
                written.append((target, current))
                target.write_text(desired, encoding="utf-8")
    except OSError:
        for target, current in reversed(written):
            target.write_text(current, encoding="utf-8")
        raise
    return {"version": "1.8.8", "changed": len(written), "patches": [str(p.relative_to(root)) for p, _, _ in changes],
            "scope": "Xiaohongshu content wait 20s"}
