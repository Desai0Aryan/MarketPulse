"""Command line interface:  python -m app.cli <command>

  seed                         backfill the whole universe (full available history)
  backfill SYMBOL --start D    backfill one or more symbols over a date range
  ingest                       incremental update from checkpoints
  reindex [SYMBOL ...]         recompute indicators after data corrections
  worker                       run scheduled incremental ingestion
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services import container


def _print(run) -> int:
    print(json.dumps({k: v for k, v in run.to_dict().items() if k != "stats"} | {"stats": {k: v for k, v in run.stats.items() if k != "per_symbol"}}, indent=2, default=str))
    return 0 if run.status in ("success", "partial") else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="marketpulse")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    b = sub.add_parser("backfill")
    b.add_argument("symbols", nargs="+")
    b.add_argument("--start", type=date.fromisoformat, required=True)
    b.add_argument("--end", type=date.fromisoformat)
    i = sub.add_parser("ingest")
    i.add_argument("symbols", nargs="*")
    r = sub.add_parser("reindex")
    r.add_argument("symbols", nargs="*")
    sub.add_parser("worker")
    args = ap.parse_args(argv)

    configure_logging(get_settings().log_level)
    svc = container.get_ingestion()
    try:
        if args.cmd == "seed":
            return _print(svc.run("backfill", trigger="cli"))
        if args.cmd == "backfill":
            return _print(svc.run("backfill", args.symbols, args.start, args.end, "cli"))
        if args.cmd == "ingest":
            return _print(svc.run("incremental", args.symbols or None, trigger="cli"))
        if args.cmd == "reindex":
            return _print(svc.run("reindex", args.symbols or None, trigger="cli"))
        if args.cmd == "worker":
            from app.ingestion.worker import run_worker

            run_worker()
            return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
