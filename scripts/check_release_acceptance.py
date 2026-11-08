"""A tag cannot publish an untested channel/action. No network or credentials here."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_digest(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    paths = sorted((root / "agent_reach").rglob("*.py"))
    paths += [root / "pyproject.toml", root / "constraints.txt"]
    for path in paths:
        if "api" in path.relative_to(root).parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate(data: dict, required: set[tuple[str, str]], digest: str) -> list[str]:
    errors = []
    if not isinstance(data, dict):
        return ["Acceptance manifest must be an object"]
    if data.get("source_sha256") != digest:
        errors.append("Acceptance belongs to different source code")
    if data.get("release_ready") is not True:
        errors.append("Acceptance is not marked release_ready")
    if data.get("pending") or data.get("additional_required_validation"):
        errors.append("Acceptance still has pending actions or required validation")
    if not isinstance(data.get("results"), list):
        return errors + ["Acceptance results must be a list"]
    # Maintainer-approved for this release: listed actions may ship untested, each with a reason.
    waived = set()
    for entry in data.get("waived") or []:
        key = (entry.get("channel"), entry.get("action")) if isinstance(entry, dict) else None
        if key not in required or not str(entry.get("reason") or "").strip():
            errors.append(f"Invalid waiver: {entry}")
            continue
        waived.add(key)
    passed = set()
    for row in data.get("results", []):
        if not isinstance(row, dict):
            errors.append("Acceptance result must be an object")
            continue
        key = (row.get("channel"), row.get("action"))
        if key not in required:
            errors.append(f"Unknown acceptance action: {key}")
            continue
        try:
            stamp = row.get("at")
            if not isinstance(stamp, str):
                raise ValueError("Missing timestamp")
            at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - at).total_seconds()
        except (KeyError, TypeError, ValueError):
            age = float("inf")
        if (row.get("source_sha256") == digest and row.get("method") == "real-cli" and row.get("passed") is True
                and type(row.get("item_count")) is int and row["item_count"] > 0
                and row.get("backend") and row.get("os") and 0 <= age <= 7 * 86400):
            passed.add(key)
    errors += [f"Missing real acceptance: {channel}/{action}"
               for channel, action in sorted(required - passed - waived)]
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", default=".github/release-acceptance.json")
    args = parser.parse_args()
    from agent_reach.runtime.cli import unified_channels
    required = {(channel.name, action.name) for channel in unified_channels() for action in channel.actions}
    try:
        data = json.loads(Path(args.manifest).read_text("utf-8"))
        errors = validate(data, required, source_digest())
    except (OSError, ValueError, TypeError) as exc:
        errors = [f"Acceptance manifest unavailable: {exc}"]
    for error in errors:
        print(error)
    if errors:
        print("Release blocked. Unit tests and doctor do not replace real channel acceptance.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
