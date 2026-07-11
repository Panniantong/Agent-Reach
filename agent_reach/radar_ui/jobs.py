# -*- coding: utf-8 -*-
"""Background jobs for the console: a small thread pool + per-job log capture.

Each job runs one pipeline function; its loguru output (filtered by worker
thread id so concurrent jobs don't cross-talk) is buffered for the SSE
console stream. Finished jobs are persisted to ``RADAR_DIR/jobs/`` for
history. No external deps — usable without the [ui] extra installed.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional

from loguru import logger

from agent_reach.radar import RADAR_DIR

JOBS_DIR = RADAR_DIR / "jobs"
_MAX_LOG_LINES = 2000


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Job:
    def __init__(self, kind: str, params: dict):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind
        self.params = params
        self.status = "queued"  # queued | running | done | error
        self.result: Optional[dict] = None
        self.error = ""
        self.created = _now()
        self.started = ""
        self.finished = ""
        self.log: list[str] = []

    def to_dict(self, with_log: bool = False) -> dict:
        d = {
            "id": self.id, "kind": self.kind, "params": self.params,
            "status": self.status, "error": self.error, "result": self.result,
            "created": self.created, "started": self.started, "finished": self.finished,
            "log_lines": len(self.log),
        }
        if with_log:
            d["log"] = list(self.log)
        return d


class JobManager:
    def __init__(self, workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="radar-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, params: dict, fn: Callable[[], Optional[dict]]) -> Job:
        job = Job(kind, params)
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job, fn)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[dict]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [j.to_dict() for j in sorted(jobs, key=lambda j: j.created, reverse=True)]

    def _append(self, job: Job, line: str) -> None:
        if len(job.log) < _MAX_LOG_LINES:
            job.log.append(line.rstrip("\n"))

    def _run(self, job: Job, fn: Callable[[], Optional[dict]]) -> None:
        job.status = "running"
        job.started = _now()
        tid = threading.get_ident()
        sink_id = logger.add(
            lambda m: self._append(job, str(m)),
            level="INFO",
            filter=lambda r: r["thread"].id == tid,
            format="{time:HH:mm:ss} | {level:<7} | {message}",
        )
        self._append(job, f"▶ job {job.id} ({job.kind}) started")
        final = "done"
        try:
            result = fn()
            job.result = result if isinstance(result, dict) else {"ok": True, "result": result}
            if not job.result.get("ok", True):
                final = "error"
                job.error = str(job.result.get("error", ""))
        except Exception as e:  # noqa: BLE001 - job errors surface in the UI, never crash the server
            final = "error"
            job.error = str(e)
            self._append(job, f"✖ EXCEPTION: {e}")
        finally:
            try:
                logger.remove(sink_id)
            except ValueError:
                pass
            job.finished = _now()
            self._append(job, f"■ job {job.id} {final}")
            # Persist BEFORE flipping to the terminal status — pollers that
            # see done/error must be able to rely on the history file.
            self._persist(job, final)
            job.status = final

    def _persist(self, job: Job, status: str) -> None:
        try:
            snapshot = job.to_dict(with_log=True)
            snapshot["status"] = status
            JOBS_DIR.mkdir(parents=True, exist_ok=True)
            (JOBS_DIR / f"{job.id}.json").write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning(f"job persist failed: {e}")

    def stream(self, job_id: str):
        """SSE generator: replay buffered lines, then follow until the job ends."""
        job = self.get(job_id)
        if job is None:
            yield f"event: end\ndata: {json.dumps({'error': 'unknown job'})}\n\n"
            return
        idx = 0
        while True:
            while idx < len(job.log):
                yield f"data: {json.dumps(job.log[idx], ensure_ascii=False)}\n\n"
                idx += 1
            if job.status in ("done", "error"):
                yield f"event: end\ndata: {json.dumps(job.to_dict(), ensure_ascii=False)}\n\n"
                return
            time.sleep(0.4)
