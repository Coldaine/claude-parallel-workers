"""SQLite-based event store with ACID guarantees and efficient queries."""

import sqlite3
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
from enum import Enum


class EventType(Enum):
    """Types of events that workers can emit."""
    START = "start"
    PROGRESS = "progress"
    ARTIFACT = "artifact"
    ERROR = "error"
    DONE = "done"
    MERGE_READY = "merge_ready"
    HEARTBEAT = "heartbeat"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"


class WorkerState(Enum):
    """States a worker can be in."""
    IDLE = "idle"
    BUSY = "busy"
    BLOCKED = "blocked"
    ERROR = "error"
    DONE = "done"
    DEAD = "dead"


class EventStoreV2:
    """SQLite-based event store with ACID guarantees."""

    def __init__(self, db_path: str = ".claude/state.db"):
        """Initialize the event store with SQLite backend.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Thread-local storage for connections
        self._local = threading.local()

        # Initialize schema
        self.init_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                isolation_level=None  # Autocommit mode
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable foreign keys and JSON support
            self._local.conn.execute("PRAGMA foreign_keys = ON")
        return self._local.conn

    @contextmanager
    def transaction(self):
        """Context manager for explicit transactions."""
        self.conn.execute("BEGIN")
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def init_schema(self):
        """Initialize database schema if not exists."""
        with self.transaction() as conn:
            # Events table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    run_id TEXT NOT NULL,
                    worker_id TEXT,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    payload JSON
                )
            """)

            # Indexes for events
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_run_id
                ON events(run_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp
                ON events(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_worker_task
                ON events(worker_id, task_id)
            """)

            # Workers table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    task_id TEXT,
                    state TEXT NOT NULL DEFAULT 'idle',
                    pid INTEGER,
                    started_at TEXT,
                    last_heartbeat TEXT,
                    progress INTEGER DEFAULT 0,
                    last_message TEXT
                )
            """)

            # Indexes for workers
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workers_state
                ON workers(state)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workers_run_id
                ON workers(run_id)
            """)

            # Tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    description TEXT,
                    dependencies JSON,
                    inputs JSON,
                    outputs JSON,
                    state TEXT DEFAULT 'pending',
                    assigned_worker TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                )
            """)

            # Indexes for tasks
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_state
                ON tasks(state)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_run_id
                ON tasks(run_id)
            """)

            # Blocks table for managing blocking operations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    worker_id TEXT NOT NULL,
                    hook_event TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT NOT NULL,
                    reason TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3
                )
            """)

            # Index for blocks
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_blocks_expires
                ON blocks(expires_at)
            """)

            # Plans table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    prompt TEXT,
                    plan JSON,
                    state TEXT DEFAULT 'active'
                )
            """)

    def append_event(
        self,
        event_type: EventType,
        run_id: str,
        worker_id: Optional[str] = None,
        task_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> int:
        """Atomically append an event.

        Args:
            event_type: Type of event
            run_id: Run identifier
            worker_id: Worker identifier (optional)
            task_id: Task identifier (optional)
            payload: Arbitrary JSON payload (optional)

        Returns:
            Event ID
        """
        with self.transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO events (run_id, worker_id, event_type, task_id, payload)
                VALUES (?, ?, ?, ?, json(?))
            """, (
                run_id,
                worker_id,
                event_type.value,
                task_id,
                json.dumps(payload) if payload else None
            ))
            return cursor.lastrowid

    def get_events(
        self,
        run_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        task_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Query events with filters.

        Args:
            run_id: Filter by run ID
            worker_id: Filter by worker ID
            task_id: Filter by task ID
            event_type: Filter by event type
            limit: Maximum events to return
            offset: Number of events to skip

        Returns:
            List of event dictionaries
        """
        query = "SELECT * FROM events WHERE 1=1"
        params = []

        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if worker_id:
            query += " AND worker_id = ?"
            params.append(worker_id)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)

        query += " ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def update_worker_status(
        self,
        worker_id: str,
        run_id: str,
        state: Optional[WorkerState] = None,
        progress: Optional[int] = None,
        task_id: Optional[str] = None,
        message: Optional[str] = None
    ):
        """Update worker status atomically.

        Args:
            worker_id: Worker identifier
            run_id: Run identifier
            state: New worker state
            progress: Progress percentage (0-100)
            task_id: Assigned task ID
            message: Status message
        """
        with self.transaction() as conn:
            # Check if worker exists
            cursor = conn.execute(
                "SELECT id FROM workers WHERE id = ?",
                (worker_id,)
            )
            exists = cursor.fetchone() is not None

            if exists:
                # Update existing worker
                updates = ["last_heartbeat = CURRENT_TIMESTAMP"]
                params = []

                if state:
                    updates.append("state = ?")
                    params.append(state.value)
                if progress is not None:
                    updates.append("progress = ?")
                    params.append(progress)
                if task_id is not None:
                    updates.append("task_id = ?")
                    params.append(task_id)
                if message is not None:
                    updates.append("last_message = ?")
                    params.append(message)

                params.append(worker_id)
                conn.execute(
                    f"UPDATE workers SET {', '.join(updates)} WHERE id = ?",
                    params
                )
            else:
                # Insert new worker
                conn.execute("""
                    INSERT INTO workers (
                        id, run_id, state, progress, task_id,
                        last_message, started_at, last_heartbeat
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    worker_id,
                    run_id,
                    state.value if state else WorkerState.IDLE.value,
                    progress or 0,
                    task_id,
                    message
                ))

    def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get current worker status.

        Args:
            worker_id: Worker identifier

        Returns:
            Worker status dictionary or None if not found
        """
        cursor = self.conn.execute(
            "SELECT * FROM workers WHERE id = ?",
            (worker_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_workers(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all workers for a run.

        Args:
            run_id: Run identifier

        Returns:
            List of worker status dictionaries
        """
        cursor = self.conn.execute(
            "SELECT * FROM workers WHERE run_id = ? ORDER BY id",
            (run_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def detect_dead_workers(self, timeout_seconds: int = 60) -> List[Dict[str, Any]]:
        """Detect workers that haven't sent heartbeat recently.

        Args:
            timeout_seconds: Seconds without heartbeat to consider dead

        Returns:
            List of potentially dead workers
        """
        cursor = self.conn.execute("""
            SELECT * FROM workers
            WHERE state IN ('busy', 'blocked')
            AND datetime(last_heartbeat) < datetime('now', ? || ' seconds')
        """, (f'-{timeout_seconds}',))

        return [dict(row) for row in cursor.fetchall()]

    def create_block(
        self,
        worker_id: str,
        hook_event: str,
        reason: str,
        duration_seconds: int = 5,
        max_retries: int = 3
    ) -> bool:
        """Create a time-limited block.

        Args:
            worker_id: Worker requesting the block
            hook_event: Hook event to block
            reason: Reason for blocking
            duration_seconds: How long to block
            max_retries: Maximum retry attempts

        Returns:
            True if block created, False if retry limit exceeded
        """
        with self.transaction() as conn:
            # Check current retry count
            cursor = conn.execute("""
                SELECT retry_count FROM blocks
                WHERE worker_id = ? AND hook_event = ?
                ORDER BY created_at DESC LIMIT 1
            """, (worker_id, hook_event))

            row = cursor.fetchone()
            retry_count = (row['retry_count'] + 1) if row else 0

            if retry_count >= max_retries:
                return False

            # Create new block
            expires_at = (
                datetime.now() + timedelta(seconds=duration_seconds)
            ).isoformat()

            conn.execute("""
                INSERT INTO blocks (
                    worker_id, hook_event, expires_at,
                    reason, retry_count, max_retries
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                worker_id, hook_event, expires_at,
                reason, retry_count, max_retries
            ))

            return True

    def get_active_blocks(self, hook_event: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get currently active blocks.

        Args:
            hook_event: Filter by hook event type

        Returns:
            List of active blocks
        """
        # Clean expired blocks first
        self.conn.execute("""
            DELETE FROM blocks
            WHERE datetime(expires_at) < datetime('now')
        """)

        query = """
            SELECT * FROM blocks
            WHERE datetime(expires_at) > datetime('now')
        """
        params = []

        if hook_event:
            query += " AND hook_event = ?"
            params.append(hook_event)

        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_ready_artifacts(self, run_id: str) -> List[str]:
        """Get artifacts from completed tasks.

        Args:
            run_id: Run identifier

        Returns:
            List of artifact paths
        """
        cursor = self.conn.execute("""
            SELECT DISTINCT json_extract(e.payload, '$.path') as path
            FROM events e
            JOIN tasks t ON e.task_id = t.id
            WHERE e.event_type = 'artifact'
            AND t.state = 'completed'
            AND e.run_id = ?
            AND json_extract(e.payload, '$.path') IS NOT NULL
        """, (run_id,))

        return [row['path'] for row in cursor.fetchall()]

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()
            delattr(self._local, 'conn')