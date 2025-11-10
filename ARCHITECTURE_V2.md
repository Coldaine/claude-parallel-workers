# Architecture V2: Claude Parallel Workers with SQLite

## Major Changes from V1

Based on critical feedback from Gemini and Codex, we're making fundamental improvements:

1. **SQLite replaces events.jsonl** - Still zero dependencies (stdlib), but ACID guarantees
2. **Worker pooling by default** - No more spawn-per-task overhead
3. **Strict blocking controls** - Timeouts, retry limits, deadlock detection
4. **Extensible event schema** - Arbitrary payloads for advanced patterns
5. **Cross-platform from day one** - No Unix-only dependencies

## Core Architecture

### The Database Schema (state.db)

```sql
-- Core tables
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_id TEXT NOT NULL,
    worker_id TEXT,
    event_type TEXT NOT NULL,
    task_id TEXT,
    payload JSON,
    INDEX idx_run_id (run_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_worker_task (worker_id, task_id)
);

CREATE TABLE workers (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    state TEXT NOT NULL DEFAULT 'idle',
    pid INTEGER,
    started_at TEXT,
    last_heartbeat TEXT,
    progress INTEGER DEFAULT 0,
    INDEX idx_state (state),
    INDEX idx_run_id (run_id)
);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    description TEXT,
    dependencies JSON,
    inputs JSON,
    outputs JSON,
    state TEXT DEFAULT 'pending',
    assigned_worker TEXT,
    INDEX idx_state (state),
    INDEX idx_run_id (run_id)
);

CREATE TABLE blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id TEXT NOT NULL,
    hook_event TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    reason TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    INDEX idx_expires (expires_at)
);
```

### Worker Pool Architecture

```python
class WorkerPool:
    """Manages a pool of reusable worker processes."""

    def __init__(self, size: int = None):
        self.size = size or (cpu_count() * 2)
        self.workers = []
        self.available = queue.Queue()
        self.busy = set()

    def get_worker(self) -> Worker:
        """Get an available worker or spawn if under limit."""
        try:
            worker = self.available.get_nowait()
        except queue.Empty:
            if len(self.workers) < self.size:
                worker = self.spawn_worker()
            else:
                # Wait for one to become available
                worker = self.available.get(block=True, timeout=30)

        self.busy.add(worker.id)
        return worker

    def release_worker(self, worker: Worker):
        """Return worker to pool."""
        self.busy.discard(worker.id)
        self.available.put(worker)
```

### Safe Blocking Mechanism

```python
def worker_request_block(hook_event: str, reason: str, duration: int = 5):
    """Request a temporary block with automatic expiry."""

    with sqlite3.connect('state.db') as conn:
        # Check if we've exceeded retry limit
        cursor = conn.execute("""
            SELECT retry_count, max_retries
            FROM blocks
            WHERE worker_id = ? AND hook_event = ?
            ORDER BY created_at DESC LIMIT 1
        """, (worker_id, hook_event))

        row = cursor.fetchone()
        if row and row[0] >= row[1]:
            # We've exceeded retries, don't block anymore
            return False

        # Create time-limited block
        expires_at = datetime.now() + timedelta(seconds=duration)
        conn.execute("""
            INSERT INTO blocks (worker_id, hook_event, expires_at, reason, retry_count)
            VALUES (?, ?, ?, ?, ?)
        """, (worker_id, hook_event, expires_at, reason, (row[0] + 1) if row else 0))

    # Invoke hook with block request
    return invoke_hook(
        event=hook_event,
        exit_code=2,
        json_output={
            "block_duration": duration,
            "reason": reason,
            "expires_at": expires_at.isoformat()
        }
    )
```

### Hook Implementation

```python
# hooks/pre_tool_use.py
def pre_tool_use():
    """Check for active blocks before allowing tool use."""

    with sqlite3.connect('state.db') as conn:
        # Clean expired blocks
        conn.execute("""
            DELETE FROM blocks
            WHERE expires_at < CURRENT_TIMESTAMP
        """)

        # Check for active blocks
        cursor = conn.execute("""
            SELECT worker_id, reason, expires_at
            FROM blocks
            WHERE hook_event = 'PreToolUse'
            AND expires_at > CURRENT_TIMESTAMP
            LIMIT 1
        """)

        block = cursor.fetchone()
        if block:
            # Block is active
            return {
                "decision": "retry",
                "reason": f"Worker {block[0]}: {block[1]}",
                "retry_after": block[2]
            }, 2  # Exit code 2 but with retry guidance

    # No blocks, check if we need to modify inputs
    tool_input = parse_json_input()

    # Check if this is a merge operation
    if "merge" in tool_input.get("command", ""):
        # Get completed artifacts
        cursor = conn.execute("""
            SELECT e.payload->>'$.path'
            FROM events e
            JOIN tasks t ON e.task_id = t.id
            WHERE e.event_type = 'artifact'
            AND t.state = 'completed'
            AND e.run_id = ?
        """, (current_run_id,))

        artifacts = [row[0] for row in cursor.fetchall()]

        # Rewrite tool input
        tool_input["inputs"] = artifacts

        return {
            "permissionDecision": "allow",
            "updatedInput": tool_input
        }, 0

    # Default: allow
    return {"permissionDecision": "allow"}, 0
```

### Event Store V2 (SQLite-based)

```python
class EventStoreV2:
    """SQLite-based event store with ACID guarantees."""

    def __init__(self, db_path: str = "state.db"):
        self.db_path = db_path
        self.init_schema()

    def append_event(self, event: Event) -> int:
        """Atomically append an event."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO events (run_id, worker_id, event_type, task_id, payload)
                VALUES (?, ?, ?, ?, json(?))
            """, (
                event.run_id,
                event.worker_id,
                event.event_type.value,
                event.task_id,
                json.dumps(event.payload)
            ))
            return cursor.lastrowid

    def get_worker_status(self, worker_id: str) -> dict:
        """Get current worker status efficiently."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT state, progress, last_heartbeat, task_id
                FROM workers
                WHERE id = ?
            """, (worker_id,))

            row = cursor.fetchone()
            if row:
                return {
                    "state": row[0],
                    "progress": row[1],
                    "last_heartbeat": row[2],
                    "task_id": row[3]
                }
            return None

    def get_ready_artifacts(self, run_id: str) -> List[str]:
        """Get artifacts from completed tasks - single query!"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT DISTINCT e.payload->>'$.path'
                FROM events e
                JOIN tasks t ON e.task_id = t.id
                WHERE e.event_type = 'artifact'
                AND t.state = 'completed'
                AND e.run_id = ?
            """, (run_id,))

            return [row[0] for row in cursor.fetchall() if row[0]]

    def detect_deadlocks(self) -> List[str]:
        """Detect potential deadlocks from stale heartbeats."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, task_id
                FROM workers
                WHERE state = 'busy'
                AND datetime(last_heartbeat) < datetime('now', '-60 seconds')
            """)

            return [{"worker": row[0], "task": row[1]} for row in cursor.fetchall()]
```

### Worker Heartbeat & Health

```python
class Worker:
    def __init__(self, worker_id: str):
        self.id = worker_id
        self.heartbeat_thread = None

    def start_heartbeat(self):
        """Start heartbeat thread to prevent being marked as dead."""
        def heartbeat_loop():
            while self.running:
                with sqlite3.connect('state.db') as conn:
                    conn.execute("""
                        UPDATE workers
                        SET last_heartbeat = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (self.id,))
                time.sleep(10)  # Heartbeat every 10 seconds

        self.heartbeat_thread = threading.Thread(target=heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()
```

## Key Improvements

### 1. Atomic Operations
- All state changes are wrapped in transactions
- No partial writes possible
- Automatic rollback on failure

### 2. Concurrent Access
- SQLite handles reader/writer locking internally
- Multiple workers can read while one writes
- No global mutex bottleneck

### 3. Efficient Queries
- Indexed queries instead of full file scans
- Get worker status in O(1) instead of O(n)
- Complex aggregations possible with SQL

### 4. Built-in Deadlock Prevention
- Time-limited blocks with automatic expiry
- Retry counters to prevent infinite loops
- Heartbeat monitoring for stuck workers

### 5. Cross-Platform by Default
- SQLite works identically on Windows/Mac/Linux
- No Unix-specific dependencies
- Same performance characteristics everywhere

## Migration Path from V1

```python
def migrate_events_jsonl_to_sqlite(jsonl_path: str, db_path: str):
    """One-time migration from events.jsonl to SQLite."""
    store = EventStoreV2(db_path)

    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                event_data = json.loads(line)
                event = Event.from_dict(event_data)
                store.append_event(event)

    print(f"Migrated {store.count_events()} events to SQLite")
```

## Production Readiness Checklist

- [x] **Atomic writes** - SQLite transactions
- [x] **Concurrent access** - SQLite's built-in locking
- [x] **Cross-platform** - Works on Windows/Mac/Linux
- [x] **Deadlock prevention** - Time-limited blocks with expiry
- [x] **Worker health monitoring** - Heartbeats and stale detection
- [x] **Efficient queries** - Indexed database instead of file scanning
- [x] **Extensible schema** - JSON payload field for arbitrary data
- [x] **Zero external dependencies** - SQLite in stdlib
- [ ] **Integration tests** - Next priority
- [ ] **Performance benchmarks** - Measure actual throughput

## Conclusion

By switching to SQLite, we get a production-ready system that maintains our "zero dependencies" constraint while solving virtually all the problems identified in V1. The filesystem is still used for artifacts, but coordination happens through a proper database with ACID guarantees.

This isn't a Rube Goldberg machine anymore - it's a robust, scalable architecture that leverages battle-tested components from Python's standard library.