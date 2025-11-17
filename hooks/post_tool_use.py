#!/usr/bin/env python3
"""
PostToolUse hook - reads worker progress and injects status into context.

After each tool execution, this hook:
1. Reads events from the database
2. Computes current worker status
3. Generates a compact status line
4. Injects it into Claude's context
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.event_store_v2 import EventStoreV2
from shared.utils import get_run_directory


def get_active_run_id() -> str:
    """
    Find the most recent active run.
    Looks in ~/.claude/runs/ for the latest directory.
    """
    runs_dir = Path.home() / ".claude" / "runs"
    if not runs_dir.exists():
        return None

    # Find most recent run directory
    run_dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    if not run_dirs:
        return None

    # Sort by modification time
    latest = max(run_dirs, key=lambda d: d.stat().st_mtime)
    return latest.name


def format_worker_status(worker_id: str, state: str, progress: int, last_message: str) -> str:
    """Format a single worker's status."""
    if state == "done":
        return f"{worker_id} ✓"
    elif state == "error":
        return f"{worker_id} ✗ (error)"
    elif state == "busy":
        if progress is not None:
            return f"{worker_id} {progress}%"
        else:
            return f"{worker_id} ⚙"
    elif state == "blocked":
        return f"{worker_id} ⏸ (blocked)"
    elif state == "idle":
        return f"{worker_id} ○"
    else:
        return f"{worker_id} ?"


def generate_status_line(run_id: str, db_path: Path) -> str:
    """Generate compact status line for all workers."""
    if not db_path.exists():
        return None

    try:
        store = EventStoreV2(str(db_path))

        # Get all workers for this run
        workers = store.get_workers(run_id)

        if not workers:
            return None

        # Format each worker status
        statuses = []
        for worker in workers:
            status = format_worker_status(
                worker['id'],
                worker['state'],
                worker['progress'],
                worker['last_message']
            )
            statuses.append(status)

        # Compose status line
        status_line = f"R{run_id} — " + "; ".join(statuses)

        # Check if all done
        all_done = all(w['state'] == 'done' for w in workers)
        if all_done:
            status_line += " — All workers complete! 🎉"

        return status_line

    except Exception as e:
        # Don't fail the hook, just skip status injection
        print(f"# Warning: Could not read worker status: {e}", file=sys.stderr)
        return None


def main():
    """Hook entry point."""
    # Read hook context from stdin (if provided)
    try:
        input_data = sys.stdin.read()
        if input_data:
            context = json.loads(input_data)
        else:
            context = {}
    except json.JSONDecodeError:
        context = {}

    # Find active run
    run_id = get_active_run_id()

    if run_id:
        run_dir = get_run_directory(run_id)
        db_path = run_dir / "events.db"

        status_line = generate_status_line(run_id, db_path)

        if status_line:
            # Output status line (will be injected into Claude's context)
            print()
            print(f"📊 Worker Status: {status_line}")
            print()

    # Exit 0 to continue normally
    sys.exit(0)


if __name__ == "__main__":
    main()
