"""Parallel work-queue scheduler for repository scraping."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

from hugging_face_dataset.config import PipelineConfig
from hugging_face_dataset.repos import RepoEntry, load_repos, repo_slug
from hugging_face_dataset.scheduler.store import RepoStatus, SchedulerStore

log = logging.getLogger(__name__)


def _pipeline_runner_cls():
    from hugging_face_dataset.pipeline.runner import PipelineRunner

    return PipelineRunner


class ParallelScheduler:
    """Process multiple repositories concurrently with automatic work claiming."""

    def __init__(
        self,
        config: PipelineConfig,
        store: SchedulerStore,
        runner: object | None = None,
    ):
        self.config = config
        self.store = store
        self._runner = runner
        self._stop = threading.Event()

    def _get_runner(self):
        if self._runner is None:
            self._runner = _pipeline_runner_cls()(self.config)
        return self._runner

    def _worker_config(self) -> PipelineConfig:
        if not self.config.scale_workers_per_repo:
            return self.config
        n = max(1, self.config.repo_workers)
        return replace(
            self.config,
            upload_workers=max(4, self.config.upload_workers // n),
            url_workers=max(8, self.config.url_workers // n),
        )

    def _run_repo(self, worker_id: str, entry: RepoEntry) -> None:
        slug = repo_slug(entry.repo_id)
        cfg = self._worker_config()
        worker_runner = _pipeline_runner_cls()(cfg)

        stop_heartbeat = threading.Event()

        def heartbeat_loop() -> None:
            while not stop_heartbeat.wait(self.config.heartbeat_interval_sec):
                prog_path = worker_runner.progress_path(slug)
                units = uploaded = skipped = failed = 0
                if prog_path.exists():
                    from hugging_face_dataset.progress.checkpoint import ProgressStore

                    store = ProgressStore(prog_path)
                    units = store.completed_count
                    totals = store.stats
                    uploaded = totals.get("uploaded", 0)
                    skipped = totals.get("skipped", 0)
                    failed = totals.get("failed", 0)
                self.store.heartbeat(
                    entry.repo_id,
                    worker_id,
                    units_done=units,
                    uploaded=uploaded,
                    skipped=skipped,
                    failed=failed,
                )

        hb = threading.Thread(target=heartbeat_loop, daemon=True, name=f"hb-{slug}")
        hb.start()

        try:
            profile = worker_runner.inspect_entry(entry)
            self.store.heartbeat(entry.repo_id, worker_id, strategy=profile.strategy)

            if profile.strategy == "unknown":
                self.store.mark_skipped(entry.repo_id, worker_id, "unknown strategy")
                log.warning("[%s] skipped %s: unknown strategy", worker_id, entry.repo_id)
                return

            print(f"\n[{worker_id}] === {entry.repo_id} === strategy={profile.strategy}")
            progress = worker_runner.progress_path(slug)
            from hugging_face_dataset.progress.checkpoint import ProgressStore
            from hugging_face_dataset.strategies.registry import build_extractor

            prog = ProgressStore(progress)
            extractor = build_extractor(profile, cfg, worker_runner.token, prog)
            stats = extractor.run()

            totals = prog.stats
            self.store.mark_completed(
                entry.repo_id,
                worker_id,
                strategy=profile.strategy,
                units_done=prog.completed_count,
                uploaded=totals.get("uploaded", stats.uploaded),
                skipped=totals.get("skipped", stats.skipped),
                failed=totals.get("failed", stats.failed),
            )
            print(
                f"[{worker_id}] completed {entry.repo_id}: "
                f"uploaded={totals.get('uploaded', 0):,} skipped={totals.get('skipped', 0):,} "
                f"failed={totals.get('failed', 0):,} units={prog.completed_count:,}"
            )
        except Exception as exc:
            log.exception("[%s] failed %s", worker_id, entry.repo_id)
            prog_path = worker_runner.progress_path(slug)
            partial = ""
            if prog_path.exists():
                from hugging_face_dataset.progress.checkpoint import ProgressStore

                totals = ProgressStore(prog_path).stats
                partial = (
                    f" (checkpoint: uploaded={totals.get('uploaded', 0):,} "
                    f"units={ProgressStore(prog_path).completed_count:,})"
                )
            self.store.mark_failed(entry.repo_id, worker_id, str(exc) + partial)
            print(f"[{worker_id}] ERROR {entry.repo_id}: {exc}")
        finally:
            stop_heartbeat.set()
            hb.join(timeout=2)
            from hugging_face_dataset.cache_cleanup import purge_repo_cache

            purge_repo_cache(cfg.cache_for(slug))

    def _worker_loop(self, worker_id: str) -> None:
        while not self._stop.is_set():
            entry = self.store.claim_next(worker_id)
            if entry is None:
                return
            self._run_repo(worker_id, entry)

    def run(
        self,
        repos_file: Path,
        *,
        dry_run: bool = False,
        reinspect: bool = False,
    ) -> None:
        added = self.store.sync_repos(repos_file)
        recovered = self.store.recover_stale()
        if added:
            print(f"Registered {added} new repo(s) in scheduler")
        if recovered:
            print(f"Recovered {len(recovered)} stale in_progress repo(s): {', '.join(recovered)}")

        if reinspect:
            for entry in load_repos(repos_file):
                self._get_runner().inspect_entry(entry, force=True)

        if dry_run:
            states = self.store.all_states()
            pending = [
                s for s in states.values()
                if s.status in (RepoStatus.NOT_STARTED.value, RepoStatus.FAILED.value)
            ]
            print(f"Dry-run: would process {len(pending)} repo(s) with {self.config.repo_workers} workers")
            for st in pending[:10]:
                print(f"  {st.repo_id}: status={st.status} retries={st.retry_count}")
            return

        summary = self.store.summary()
        print(
            f"Scheduler: {self.config.repo_workers} repo worker(s), "
            f"not_started={summary.get('not_started', 0)} "
            f"in_progress={summary.get('in_progress', 0)} "
            f"completed={summary.get('completed', 0)} "
            f"failed={summary.get('failed', 0)}"
        )

        pending = summary.get(RepoStatus.NOT_STARTED.value, 0)
        retryable = sum(
            1
            for st in self.store.all_states().values()
            if st.status == RepoStatus.FAILED.value and st.retry_count < st.max_retries
        )
        if pending + retryable == 0 and summary.get(RepoStatus.IN_PROGRESS.value, 0) == 0:
            print("All repositories processed.")
            return

        worker_ids = [f"w{i}-{uuid.uuid4().hex[:6]}" for i in range(self.config.repo_workers)]

        with ThreadPoolExecutor(max_workers=self.config.repo_workers) as pool:
            futures = [pool.submit(self._worker_loop, wid) for wid in worker_ids]
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc:
                    log.exception("Worker crashed: %s", exc)

        print("Scheduler finished this run.")

    def stop(self) -> None:
        self._stop.set()

    def print_status(self) -> None:
        states = self.store.all_states()
        if not states:
            print("  (no repos registered — run schedule first)")
            return
        for st in sorted(states.values(), key=lambda s: s.repo_id):
            extra = ""
            if st.status == RepoStatus.IN_PROGRESS.value:
                extra = f" worker={st.worker_id} units={st.units_done}"
            elif st.status == RepoStatus.FAILED.value:
                extra = f" retries={st.retry_count}/{st.max_retries} err={st.last_error[:60]}"
            elif st.status == RepoStatus.COMPLETED.value:
                extra = f" uploaded={st.uploaded} units={st.units_done}"
            print(f"  {st.repo_id}: {st.status}{extra}")
