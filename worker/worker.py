#!/usr/bin/env python3
"""
Worker process for executing tasks.
Can be invoked standalone or by orchestrator.
"""

import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.event_store_v2 import EventStoreV2
from shared.models import EventType


class Worker:
    """Worker process that executes tasks and reports via event store."""

    def __init__(self, run_id: str, worker_id: str, task_id: str, db_path: str):
        self.run_id = run_id
        self.worker_id = worker_id
        self.task_id = task_id
        self.store = EventStoreV2(db_path)

        # Create worker record
        self.store.create_worker(worker_id, run_id, task_id)

    def send_heartbeat(self):
        """Send heartbeat to indicate worker is alive."""
        self.store.append_event(
            run_id=self.run_id,
            worker_id=self.worker_id,
            event_type=EventType.HEARTBEAT.value,
            task_id=self.task_id,
            payload={}
        )

        self.store.update_worker_status(
            worker_id=self.worker_id,
            state="busy",
            progress=None,  # Keep current progress
            last_message=None  # Keep current message
        )

    def update_progress(self, percent: int, message: str = ""):
        """Update task progress."""
        self.store.append_event(
            run_id=self.run_id,
            worker_id=self.worker_id,
            event_type=EventType.PROGRESS.value,
            task_id=self.task_id,
            payload={"percent": percent, "message": message}
        )

        self.store.update_worker_status(
            worker_id=self.worker_id,
            state="busy",
            progress=percent,
            last_message=message
        )

    def report_artifact(self, path: str):
        """Report an artifact (output file) created by this task."""
        self.store.append_event(
            run_id=self.run_id,
            worker_id=self.worker_id,
            event_type=EventType.ARTIFACT.value,
            task_id=self.task_id,
            payload={"path": path}
        )

    def report_error(self, error: str):
        """Report task failure."""
        self.store.append_event(
            run_id=self.run_id,
            worker_id=self.worker_id,
            event_type=EventType.ERROR.value,
            task_id=self.task_id,
            payload={"error": error}
        )

        self.store.update_worker_status(
            worker_id=self.worker_id,
            state="error",
            progress=0,
            last_message=error
        )

    def report_done(self):
        """Report successful completion."""
        self.store.append_event(
            run_id=self.run_id,
            worker_id=self.worker_id,
            event_type=EventType.DONE.value,
            task_id=self.task_id,
            payload={"success": True}
        )

        self.store.update_worker_status(
            worker_id=self.worker_id,
            state="done",
            progress=100,
            last_message="Completed successfully"
        )

    def execute_command(self, command: str, working_dir: Path, timeout: int = 300):
        """
        Execute a shell command and report progress.

        Args:
            command: Shell command to execute
            working_dir: Directory to execute in
            timeout: Maximum execution time in seconds
        """
        # Start task
        self.store.append_event(
            run_id=self.run_id,
            worker_id=self.worker_id,
            event_type=EventType.START.value,
            task_id=self.task_id,
            payload={"command": command}
        )

        self.update_progress(0, "Starting...")

        try:
            # Execute command
            self.update_progress(10, "Executing command...")

            result = subprocess.run(
                command,
                shell=True,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=timeout
            )

            self.update_progress(90, "Command completed, processing output...")

            # Save output
            output_file = working_dir / "output.txt"
            output_file.write_text(result.stdout)

            if result.stderr:
                error_file = working_dir / "error.txt"
                error_file.write_text(result.stderr)

            # Report artifact
            self.report_artifact(str(output_file))

            if result.returncode == 0:
                self.report_done()
                return True
            else:
                self.report_error(f"Command exited with code {result.returncode}")
                return False

        except subprocess.TimeoutExpired:
            self.report_error(f"Command timed out after {timeout}s")
            return False

        except Exception as e:
            self.report_error(f"Exception: {str(e)}")
            return False


def main():
    """CLI entry point for worker."""
    if len(sys.argv) < 6:
        print("Usage: worker.py <run_id> <worker_id> <task_id> <db_path> <command> [working_dir]")
        print()
        print("Example:")
        print("  worker.py R42 W1 task1 /path/to/events.db 'ls -la' /tmp/worker1")
        sys.exit(1)

    run_id = sys.argv[1]
    worker_id = sys.argv[2]
    task_id = sys.argv[3]
    db_path = sys.argv[4]
    command = sys.argv[5]
    working_dir = Path(sys.argv[6]) if len(sys.argv) > 6 else Path.cwd()

    # Create working directory if needed
    working_dir.mkdir(parents=True, exist_ok=True)

    # Create worker and execute
    worker = Worker(run_id, worker_id, task_id, db_path)

    print(f"Worker {worker_id} starting task {task_id}")
    print(f"Command: {command}")
    print(f"Working directory: {working_dir}")
    print()

    success = worker.execute_command(command, working_dir)

    if success:
        print(f"✓ Task {task_id} completed successfully")
        sys.exit(0)
    else:
        print(f"✗ Task {task_id} failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
