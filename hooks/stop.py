#!/usr/bin/env python3
"""
Stop hook - verifies all workers complete before session ends.

Before Claude Code ends the session, this hook:
1. Checks all worker completion status
2. Blocks termination if workers are pending (exit code 2)
3. Allows graceful termination when all complete
4. Ensures no orphaned processes
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.event_store_v2 import EventStoreV2
from shared.utils import get_run_directory


def get_active_run_id() -> str:
    """Find the most recent active run."""
    runs_dir = Path.home() / ".claude" / "runs"
    if not runs_dir.exists():
        return None

    run_dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    if not run_dirs:
        return None

    latest = max(run_dirs, key=lambda d: d.stat().st_mtime)
    return latest.name


def check_workers_complete(run_id: str, db_path: Path) -> tuple:
    """
    Check if all workers are complete.

    Returns:
        (all_complete: bool, message: str, worker_summary: dict)
    """
    if not db_path.exists():
        return (True, "No active workers", {})

    try:
        store = EventStoreV2(str(db_path))

        # Get all workers
        workers = store.get_workers(run_id)

        if not workers:
            return (True, "No workers found", {})

        # Categorize workers by state
        summary = {
            'done': [],
            'error': [],
            'busy': [],
            'blocked': [],
            'idle': [],
            'dead': []
        }

        for worker in workers:
            state = worker['state']
            summary[state].append({
                'id': worker['id'],
                'task_id': worker['task_id'],
                'progress': worker['progress'],
                'message': worker['last_message']
            })

        # Check if all are in terminal states (done, error, dead)
        terminal_states = ['done', 'error', 'dead']
        active_count = sum(
            len(summary[state])
            for state in ['busy', 'blocked', 'idle']
        )

        if active_count > 0:
            # Workers still active
            return (False, f"{active_count} workers still active", summary)

        # All terminal
        total = len(workers)
        done = len(summary['done'])
        errors = len(summary['error'])

        return (True, f"{done}/{total} succeeded, {errors} failed", summary)

    except Exception as e:
        # On error, allow termination
        return (True, f"Error checking workers: {e}", {})


def main():
    """Hook entry point."""
    # Read hook context from stdin
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

    if not run_id:
        # No active run - allow termination
        print("✓ No active parallel execution")
        sys.exit(0)

    run_dir = get_run_directory(run_id)
    db_path = run_dir / "events.db"

    complete, message, summary = check_workers_complete(run_id, db_path)

    if not complete:
        # Workers still running - block termination
        print()
        print("⚠️  Cannot end session - workers still active")
        print()
        print(f"Status: {message}")
        print()

        # Show active workers
        if summary['busy']:
            print("Busy workers:")
            for w in summary['busy']:
                progress = f"{w['progress']}%" if w['progress'] is not None else "working"
                print(f"  - {w['id']}: {progress} - {w['message']}")

        if summary['blocked']:
            print("Blocked workers:")
            for w in summary['blocked']:
                print(f"  - {w['id']}: {w['message']}")

        print()
        print("💡 Tip: Wait for workers to complete, or manually terminate them.")
        print(f"   Run directory: {run_dir}")

        sys.exit(2)  # Exit code 2 = block termination

    else:
        # All workers complete
        print()
        print("✓ All workers complete")
        print()
        print(f"Summary: {message}")

        if summary['done']:
            print(f"  Successful: {len(summary['done'])} tasks")

        if summary['error']:
            print(f"  Failed: {len(summary['error'])} tasks")
            for w in summary['error']:
                print(f"    - {w['id']}: {w['message']}")

        print()
        print(f"📊 Results available in: {run_dir}")

        sys.exit(0)  # Allow termination


if __name__ == "__main__":
    main()
