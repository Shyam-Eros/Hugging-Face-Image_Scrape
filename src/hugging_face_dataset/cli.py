#!/usr/bin/env python3
"""CLI for the Hugging Face image scraping pipeline."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from hugging_face_dataset.config import PipelineConfig, load_env
from hugging_face_dataset.paths import PROJECT_ROOT
from hugging_face_dataset.pipeline.runner import PipelineRunner


def _default_repo_workers() -> int:
    cpu = os.cpu_count() or 4
    return max(2, min(8, cpu // 16))


def main(argv: list[str] | None = None) -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    p = argparse.ArgumentParser(description="HF dataset image pipeline → GCS")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--repos",
            type=Path,
            default=PROJECT_ROOT / "repository.txt",
            help="Text file with HF repo ids",
        )
        sp.add_argument("--upload-workers", type=int, default=64)
        sp.add_argument("--url-workers", type=int, default=128)
        sp.add_argument("--prefetch-shards", type=int, default=2)
        sp.add_argument("--scale-workers-per-repo", action="store_true")
        sp.add_argument("--max-shards", type=int, default=0)
        sp.add_argument("--max-images", type=int, default=0)
        sp.add_argument("--reinspect", action="store_true")
        sp.add_argument(
            "--scheduler-file",
            type=Path,
            default=None,
            help="Scheduler state JSON path",
        )

    def add_scheduler(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--repo-workers",
            type=int,
            default=_default_repo_workers(),
            help="Max repositories processed in parallel",
        )
        sp.add_argument("--max-retries", type=int, default=3)
        sp.add_argument("--stale-timeout", type=int, default=600, help="Seconds before stale in_progress is recovered")

    insp = sub.add_parser("inspect", help="Detect schema/strategy for each repo")
    add_common(insp)

    run = sub.add_parser("run", help="Scrape images sequentially (legacy mode)")
    add_common(run)
    run.add_argument("--dry-run", action="store_true")

    sched = sub.add_parser(
        "schedule",
        help="Run parallel work-queue scheduler (recommended)",
    )
    add_common(sched)
    add_scheduler(sched)
    sched.add_argument("--dry-run", action="store_true")

    stat = sub.add_parser("status", help="Show checkpoint and scheduler status")
    add_common(stat)
    stat.add_argument("--scheduler-only", action="store_true")

    args = p.parse_args(argv)

    cfg = PipelineConfig(
        upload_workers=args.upload_workers,
        url_workers=args.url_workers,
        max_shards=args.max_shards,
        max_images=args.max_images,
        prefetch_shards=args.prefetch_shards,
        scale_workers_per_repo=args.scale_workers_per_repo,
    )
    if hasattr(args, "repo_workers"):
        cfg.repo_workers = args.repo_workers
    if hasattr(args, "max_retries"):
        cfg.max_retries = args.max_retries
    if hasattr(args, "stale_timeout"):
        cfg.stale_timeout_sec = args.stale_timeout
    if getattr(args, "scheduler_file", None):
        cfg.scheduler_file = args.scheduler_file

    runner = PipelineRunner(cfg)

    if args.command == "inspect":
        runner.inspect_all(args.repos, force=args.reinspect)
    elif args.command == "run":
        runner.run_all(args.repos, dry_run=args.dry_run, reinspect=args.reinspect)
    elif args.command == "schedule":
        runner.run_scheduled(args.repos, dry_run=args.dry_run, reinspect=args.reinspect)
    elif args.command == "status":
        if not args.scheduler_only:
            print("Unit checkpoints:")
            runner.status(args.repos)
            print()
        print("Scheduler:")
        runner.scheduler_status(args.repos)
    else:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
