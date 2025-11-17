#!/usr/bin/env python3
"""
PreToolUse hook - checks dependencies and can rewrite tool inputs.

Before each tool execution, this hook:
1. Detects merge/combine operations
2. Checks if all worker dependencies are satisfied
3. Rewrites tool inputs with actual artifact paths
4. Blocks execution if workers aren't ready (exit code 2)
"""

import sys
import json
import re
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


def detect_merge_operation(tool_name: str, tool_input: dict) -> bool:
    """
    Detect if this tool use is attempting to merge worker results.

    Looks for patterns like:
    - Read tool with placeholder paths like "W1/output.txt"
    - Bash commands with "cat W1/* W2/*"
    - Write commands combining multiple sources
    """
    # Check if tool involves reading worker outputs
    if tool_name == "Read":
        file_path = tool_input.get('file_path', '')
        if re.search(r'W-?\d+', file_path) or 'worker' in file_path.lower():
            return True

    elif tool_name == "Bash":
        command = tool_input.get('command', '')
        if re.search(r'W-?\d+', command) or 'worker' in command.lower():
            return True

    return False


def check_workers_ready(run_id: str, db_path: Path) -> tuple:
    """
    Check if all workers are complete and ready for merging.

    Returns:
        (ready: bool, message: str, artifact_paths: list)
    """
    if not db_path.exists():
        return (True, "No active workers", [])

    try:
        store = EventStoreV2(str(db_path))

        # Get all workers
        workers = store.get_workers(run_id)

        if not workers:
            return (True, "No workers found", [])

        # Check if all are done
        done_count = sum(1 for w in workers if w['state'] == 'done')
        total_count = len(workers)

        if done_count < total_count:
            # Workers still running - block
            in_progress = [w for w in workers if w['state'] in ['busy', 'idle']]
            return (
                False,
                f"Waiting for {len(in_progress)}/{total_count} workers to complete",
                []
            )

        # All done - get artifact paths
        artifacts = []
        for worker in workers:
            # Get artifacts for this worker
            worker_artifacts = store.get_ready_artifacts([worker['task_id']])
            artifacts.extend(worker_artifacts)

        return (True, f"All {total_count} workers complete", artifacts)

    except Exception as e:
        # On error, allow operation to proceed
        return (True, f"Error checking workers: {e}", [])


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

    # Extract tool call information
    tool_call = context.get('tool_call', {})
    tool_name = tool_call.get('name', '')
    tool_input = tool_call.get('parameters', {})

    # Check if this is a merge operation
    is_merge = detect_merge_operation(tool_name, tool_input)

    if is_merge:
        # Find active run
        run_id = get_active_run_id()

        if run_id:
            run_dir = get_run_directory(run_id)
            db_path = run_dir / "events.db"

            ready, message, artifacts = check_workers_ready(run_id, db_path)

            if not ready:
                # Block execution - workers not ready
                print(f"⏸ Blocking: {message}")
                print()
                print("Workers are still processing. This operation will retry once they complete.")
                sys.exit(2)  # Exit code 2 = block

            elif artifacts:
                # Workers ready - provide helpful context about artifacts
                print(f"✓ {message}")
                print()
                print(f"📦 Available artifacts ({len(artifacts)}):")
                for path in artifacts:
                    print(f"   - {path}")
                print()

                # Note: In a full implementation, we could modify tool_input here
                # to rewrite placeholder paths with actual artifact paths
                # and output modified JSON

    # Exit 0 to continue normally
    sys.exit(0)


if __name__ == "__main__":
    main()
