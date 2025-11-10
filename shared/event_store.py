"""Event store for managing the append-only event log."""

import os
import json
import fcntl
import platform
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Iterator
from .models import Event, EventType, Status, Worker, WorkerState


class EventStore:
    """Manages reading and writing to the events.jsonl file."""

    def __init__(self, run_directory: str):
        """Initialize the event store.

        Args:
            run_directory: Path to the run directory (e.g., .claude/runs/R42/)
        """
        self.run_directory = Path(run_directory)
        self.events_file = self.run_directory / "events.jsonl"
        self.status_file = self.run_directory / "status.json"

        # Ensure directory exists
        self.run_directory.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: Event) -> None:
        """Append an event to the event log.

        Thread-safe append operation using file locking on Unix.
        On Windows, relies on atomic append behavior.

        Args:
            event: Event to append
        """
        # Ensure timestamp if not set
        if not event.ts:
            event.ts = datetime.now().isoformat()

        json_line = event.to_json() + '\n'

        # Open in append mode for atomic writes
        with open(self.events_file, 'a', encoding='utf-8') as f:
            if platform.system() != 'Windows':
                # Use file locking on Unix-like systems
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    f.write(json_line)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except:
                    # If locking fails, still write (append is usually atomic)
                    f.write(json_line)
            else:
                # Windows: rely on atomic append
                f.write(json_line)

    def read_events(self) -> List[Event]:
        """Read all events from the event log.

        Returns:
            List of all events in chronological order
        """
        if not self.events_file.exists():
            return []

        events = []
        with open(self.events_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(Event.from_json(line))
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        pass
        return events

    def tail_events(self, last_n: int = 10) -> List[Event]:
        """Read the last N events from the log.

        Args:
            last_n: Number of events to read from the end

        Returns:
            List of the last N events
        """
        if not self.events_file.exists():
            return []

        # Read all lines (could optimize for large files)
        with open(self.events_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        events = []
        for line in lines[-last_n:]:
            line = line.strip()
            if line:
                try:
                    events.append(Event.from_json(line))
                except json.JSONDecodeError:
                    pass
        return events

    def stream_events(self) -> Iterator[Event]:
        """Stream events as they are appended to the log.

        Yields:
            Events as they appear in the log
        """
        if not self.events_file.exists():
            return

        with open(self.events_file, 'r', encoding='utf-8') as f:
            # Start from beginning
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield Event.from_json(line)
                    except json.JSONDecodeError:
                        pass

    def compute_status(self) -> Status:
        """Compute current status from the event log.

        Returns:
            Current status of all workers and tasks
        """
        events = self.read_events()

        # Extract run_id from directory name
        run_id = self.run_directory.name

        # Track worker states
        workers_map = {}
        tasks_done = set()
        tasks_pending = set()

        for event in events:
            if event.w:
                if event.w not in workers_map:
                    workers_map[event.w] = {
                        'id': event.w,
                        'state': 'init',
                        'percent': 0,
                        'last_msg': '',
                        'task': event.task
                    }

                worker = workers_map[event.w]

                if event.t == EventType.START:
                    worker['state'] = 'running'
                    worker['percent'] = 0
                    if event.task:
                        tasks_pending.add(event.task)

                elif event.t == EventType.PROGRESS:
                    if event.pct is not None:
                        worker['percent'] = event.pct
                    if event.msg:
                        worker['last_msg'] = event.msg
                    if 'waiting' in (event.msg or '').lower():
                        worker['state'] = 'waiting'

                elif event.t == EventType.ERROR:
                    worker['state'] = 'error'
                    if event.msg:
                        worker['last_msg'] = event.msg

                elif event.t == EventType.DONE:
                    worker['state'] = 'done'
                    worker['percent'] = 100
                    if event.task:
                        tasks_done.add(event.task)
                        tasks_pending.discard(event.task)

        # Determine what we're blocked on
        blocked_on = list(tasks_pending - tasks_done)

        # Check if merge is ready
        merge_ready = len(tasks_pending) == 0 and len(tasks_done) > 0

        return Status(
            run_id=run_id,
            workers=list(workers_map.values()),
            blocked_on=blocked_on,
            merge_ready=merge_ready
        )

    def save_status(self, status: Optional[Status] = None) -> None:
        """Save current status to status.json.

        Args:
            status: Status to save (if None, computes current status)
        """
        if status is None:
            status = self.compute_status()

        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump(status.to_dict(), f, indent=2)

    def load_status(self) -> Optional[Status]:
        """Load status from status.json if it exists.

        Returns:
            Status object or None if file doesn't exist
        """
        if not self.status_file.exists():
            return None

        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return Status(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    def get_worker_artifacts(self, worker_id: str) -> List[str]:
        """Get all artifacts produced by a worker.

        Args:
            worker_id: Worker ID to query

        Returns:
            List of artifact paths
        """
        artifacts = []
        for event in self.read_events():
            if event.w == worker_id and event.t == EventType.ARTIFACT and event.path:
                artifacts.append(event.path)
        return artifacts

    def is_all_workers_done(self) -> bool:
        """Check if all workers have completed.

        Returns:
            True if all workers are in done state
        """
        status = self.compute_status()
        return all(w['state'] == 'done' for w in status.workers)

    def get_ready_artifacts(self) -> List[str]:
        """Get all artifacts from completed workers.

        Returns:
            List of artifact paths from done workers
        """
        done_workers = set()
        artifacts = []

        # First pass: identify done workers
        for event in self.read_events():
            if event.t == EventType.DONE and event.w:
                done_workers.add(event.w)

        # Second pass: collect artifacts from done workers
        for event in self.read_events():
            if (event.t == EventType.ARTIFACT and
                event.w in done_workers and
                event.path):
                artifacts.append(event.path)

        return artifacts