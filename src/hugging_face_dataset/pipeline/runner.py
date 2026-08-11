"""Orchestrate inspect → route → extract for each repo."""

from __future__ import annotations

import logging
from pathlib import Path

from hugging_face_dataset.config import PipelineConfig, get_hf_token, load_env
from hugging_face_dataset.inspect.inspector import inspect_repo
from hugging_face_dataset.profile import DatasetProfile
from hugging_face_dataset.progress.checkpoint import ProgressStore
from hugging_face_dataset.repos import RepoEntry, load_repos, repo_slug
from hugging_face_dataset.scheduler.store import SchedulerStore
from hugging_face_dataset.strategies.base import RunStats
from hugging_face_dataset.strategies.registry import build_extractor

log = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(self, config: PipelineConfig | None = None):
        load_env()
        self.config = config or PipelineConfig()
        self.token = get_hf_token()

    def profile_path(self, slug: str) -> Path:
        return self.config.profile_dir / f"{slug}.json"

    def progress_path(self, slug: str) -> Path:
        return self.config.progress_dir / f"{slug}.jsonl"

    def inspect_entry(self, entry: RepoEntry, *, force: bool = False) -> DatasetProfile:
        slug = repo_slug(entry.repo_id)
        path = self.profile_path(slug)
        if path.exists() and not force:
            return DatasetProfile.load(path)
        print(f"Inspecting {entry.repo_id} ...")
        profile = inspect_repo(entry, self.token, self.config.cache_for(slug))
        profile.save(path)
        print(f"  → strategy={profile.strategy} cols={profile.image_columns or profile.url_columns}")
        return profile

    def run_entry(
        self,
        entry: RepoEntry,
        *,
        dry_run: bool = False,
        reinspect: bool = False,
    ) -> RunStats:
        slug = repo_slug(entry.repo_id)
        profile = self.inspect_entry(entry, force=reinspect)

        if profile.strategy == "unknown":
            log.warning("Skipping %s: unknown strategy", entry.repo_id)
            return RunStats()

        print(f"\n=== {entry.repo_id} ===")
        print(f"  strategy:  {profile.strategy}")
        print(f"  GCS:       gs://{self.config.gcs_bucket}/{self.config.gcs_prefix_for(slug)}/images/")
        print(f"  progress:  {self.progress_path(slug)}")

        progress = ProgressStore(self.progress_path(slug))
        print(f"  checkpoint: {progress.completed_count} unit(s) done")

        extractor = build_extractor(profile, self.config, self.token, progress)
        stats = extractor.run(dry_run=dry_run)
        if not dry_run:
            print(
                f"  finished: uploaded={stats.uploaded} skipped={stats.skipped} failed={stats.failed}"
            )
        return stats

    def inspect_all(self, repos_file: Path, *, force: bool = False) -> None:
        for entry in load_repos(repos_file):
            self.inspect_entry(entry, force=force)

    def run_all(
        self,
        repos_file: Path,
        *,
        dry_run: bool = False,
        reinspect: bool = False,
    ) -> None:
        entries = load_repos(repos_file)
        print(f"Pipeline: {len(entries)} repo(s) from {repos_file}")
        print(f"upload_workers={self.config.upload_workers} url_workers={self.config.url_workers}")

        for entry in entries:
            try:
                self.run_entry(entry, dry_run=dry_run, reinspect=reinspect)
            except Exception as e:
                log.exception("Failed %s: %s", entry.repo_id, e)
                print(f"ERROR {entry.repo_id}: {e}")

    def run_scheduled(
        self,
        repos_file: Path,
        *,
        dry_run: bool = False,
        reinspect: bool = False,
    ) -> None:
        from hugging_face_dataset.scheduler.pool import ParallelScheduler

        store = SchedulerStore(
            self.config.scheduler_path(),
            stale_timeout_sec=self.config.stale_timeout_sec,
            max_retries=self.config.max_retries,
        )
        scheduler = ParallelScheduler(self.config, store, runner=self)
        scheduler.run(repos_file, dry_run=dry_run, reinspect=reinspect)

    def scheduler_status(self, repos_file: Path | None = None) -> None:
        from hugging_face_dataset.scheduler.pool import ParallelScheduler

        store = SchedulerStore(
            self.config.scheduler_path(),
            stale_timeout_sec=self.config.stale_timeout_sec,
            max_retries=self.config.max_retries,
        )
        if repos_file:
            store.sync_repos(repos_file)
        summary = store.summary()
        print(
            f"Scheduler summary: "
            f"not_started={summary.get('not_started', 0)} "
            f"in_progress={summary.get('in_progress', 0)} "
            f"completed={summary.get('completed', 0)} "
            f"failed={summary.get('failed', 0)} "
            f"skipped={summary.get('skipped', 0)}"
        )
        ParallelScheduler(self.config, store).print_status()

    def status(self, repos_file: Path) -> None:
        for entry in load_repos(repos_file):
            slug = repo_slug(entry.repo_id)
            prog = self.progress_path(slug)
            prof = self.profile_path(slug)
            done = ProgressStore(prog).completed_count if prog.exists() else 0
            strategy = DatasetProfile.load(prof).strategy if prof.exists() else "?"
            print(f"  {entry.repo_id}: strategy={strategy} checkpoint={done}")
