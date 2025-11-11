# Research Synthesis & Architecture Recommendations

## Investigation Summary

We investigated two production-ready Claude orchestration frameworks to extract proven patterns for our ClaudeParallel architecture:

1. **ruvnet/claude-flow** (⭐⭐⭐⭐⭐) - Hook-based coordination with SQLite
2. **parruda/swarm** (⭐⭐⭐⭐) - Multi-agent delegation (v2: single-process, v1: multi-process)

## Critical Discoveries

### 1. SwarmSDK Abandoned Multi-Process Architecture

**SwarmSDK migrated from v1 (multi-process) to v2 (single-process) citing:**
- IPC overhead was too expensive
- Direct method calls 10x+ faster than MCP inter-process communication
- Simpler deployment and state management

**However - their use case differs from ours:**

| | SwarmSDK | ClaudeParallel |
|---|----------|----------------|
| **Goal** | Role specialization | True parallelism |
| **Pattern** | Sequential delegation (lead→frontend→backend) | Concurrent execution (4 workers simultaneously) |
| **Communication** | Frequent (every delegation) | Infrequent (coordination checkpoints) |

**Conclusion:** SwarmSDK's IPC overhead came from **high-frequency delegation chains**. Our architecture has **low-frequency coordination** (workers mostly work independently), so multi-process is still viable.

**Action:** ✅ Keep multi-process architecture but minimize IPC frequency

### 2. SQLite is Production-Ready (Validation)

Both frameworks use databases for state management:

**claude-flow:**
- Comprehensive 12-table schema (swarms, agents, tasks, resources, messages, metrics, events, etc.)
- ENUM types for states
- JSON fields for flexibility
- Views for efficient queries
- Stored procedures for cleanup
- Supports PostgreSQL, MySQL, and SQLite

**Our Architecture V2:**
- Already uses SQLite ✅
- Has events, workers, tasks, blocks, plans tables ✅
- Uses JSON payloads ✅
- Has indexes ✅

**Gaps to Fill:**
- ❌ No database views for common queries
- ❌ No cleanup procedures
- ❌ No resource allocation tracking
- ❌ No inter-worker messaging table

**Action:** 📋 Add views, cleanup procedures, resource tracking

### 3. Hook Actions System (Critical Pattern)

**SwarmSDK has 6 hook actions** that control execution flow by returning structured results:

1. **Continue** - Proceed normally (default)
2. **Halt** - Stop with error
3. **Replace** - Modify tool result
4. **Reprompt** - Continue with new prompt
5. **Finish Agent** - End current agent's turn
6. **Finish Swarm** - Terminate entire execution

**Current Architecture:**
- Exit code 0 = allow
- Exit code 2 = block
- No way to modify results
- No way to inject new prompts
- No early termination mechanism

**Action:** ⭐⭐⭐⭐⭐ Implement Hook Actions system

### 4. Hook Context Object (Critical Pattern)

**SwarmSDK provides rich context to hooks:**

```ruby
ctx.agent_name          # Current agent
ctx.tool_call.name      # Tool being called
ctx.tool_call.parameters # Tool arguments
ctx.tool_result.content  # Tool output
ctx.metadata[:prompt]    # User prompt
ctx.metadata[:cost]      # Execution cost
```

**Current Architecture:**
- Hooks receive JSON via stdin ✅
- But no structured context object
- Tool results not accessible in pre-hooks
- Limited metadata

**Action:** ⭐⭐⭐⭐⭐ Create HookContext dataclass

### 5. Additional Hook Events

**SwarmSDK has 13 hook events** vs our 9:

| Our Events | SwarmSDK Additional | Benefit |
|------------|---------------------|---------|
| UserPromptSubmit | first_message | Distinguish first vs subsequent |
| - | agent_step | After each LLM response (mid-execution) |
| - | agent_stop | When agent completes turn |
| - | context_warning | Token usage alerts (80%, 90%) |
| - | pre_delegation, post_delegation | Before/after handoffs |

**Action:** 📋 Add agent_step, agent_stop, context_warning events

### 6. Matcher-Based Hook Filtering

**Both frameworks use matchers:**

claude-flow:
```json
{
  "matcher": "Write|Edit|MultiEdit",
  "hooks": [...]
}
```

SwarmSDK:
```ruby
hook :pre_tool_use, matcher: "Bash" do |ctx|
  # Only fires for Bash tool
end
```

**Current Architecture:**
- Hooks always fire ❌
- No filtering by tool type

**Action:** ⭐⭐⭐⭐ Implement matcher-based filtering

### 7. Git Worktree Management

**SwarmSDK v1 had sophisticated worktree management:**
- External directory: `~/.claude-swarm/worktrees/[session]/[repo]/[name]`
- Automatic creation and cleanup
- Per-instance configuration
- Session tracking for restoration

**Benefit for our architecture:**
- Filesystem isolation without multiple repos
- Each worker can have isolated workspace
- No conflicts with package managers

**Action:** 📋 Consider implementing worktree management

### 8. Tool Input Modification (Critical Pattern)

**claude-flow bash-hook.sh shows:**
- Read JSON from stdin
- Modify command (add safety flags, expand aliases)
- Return modified JSON
- Claude uses modified input

**Pattern:**
```bash
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')
MODIFIED_COMMAND="$COMMAND -i"  # Add safety flag
echo "$INPUT" | jq --arg cmd "$MODIFIED_COMMAND" '.tool_input.command = $cmd'
exit 0
```

**Current Architecture:**
- Exit code 2 can block
- But cannot modify inputs ❌

**Action:** ⭐⭐⭐⭐⭐ Support tool input modification

## Proposed Architecture Improvements

### Priority 1: Critical (Implement Immediately)

#### 1.1 Hook Actions System

**Implementation:**

```python
# shared/hook_actions.py
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum

class HookAction(Enum):
    CONTINUE = "continue"
    HALT = "halt"
    REPLACE = "replace"
    REPROMPT = "reprompt"
    FINISH_WORKER = "finish_worker"
    FINISH_RUN = "finish_run"

@dataclass
class HookResult:
    action: HookAction
    data: Optional[Dict[str, Any]] = None

    @staticmethod
    def continue_execution():
        return HookResult(HookAction.CONTINUE)

    @staticmethod
    def halt(reason: str):
        return HookResult(HookAction.HALT, {"reason": reason})

    @staticmethod
    def replace(new_content: str):
        return HookResult(HookAction.REPLACE, {"content": new_content})

    @staticmethod
    def reprompt(new_prompt: str):
        return HookResult(HookAction.REPROMPT, {"prompt": new_prompt})

    @staticmethod
    def finish_worker(reason: str):
        return HookResult(HookAction.FINISH_WORKER, {"reason": reason})

    @staticmethod
    def finish_run(reason: str):
        return HookResult(HookAction.FINISH_RUN, {"reason": reason})

# Hook returns JSON with action
# Exit code 0 + stdout JSON = action
# Exit code 2 = halt (backward compatible)
```

**Hook Output Format:**

```json
{
  "action": "replace",
  "data": {
    "content": "Modified tool result"
  }
}
```

**Backward Compatibility:**
- Exit code 0 + no stdout = CONTINUE
- Exit code 0 + JSON stdout = parse action
- Exit code 2 = HALT (legacy behavior)

#### 1.2 Hook Context Object

**Implementation:**

```python
# shared/hook_context.py
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import json

@dataclass
class ToolCall:
    name: str
    parameters: Dict[str, Any]

@dataclass
class ToolResult:
    content: str
    exit_code: Optional[int] = None
    stderr: Optional[str] = None

@dataclass
class HookContext:
    worker_id: str
    run_id: str
    event_type: str
    tool_call: Optional[ToolCall] = None
    tool_result: Optional[ToolResult] = None
    metadata: Dict[str, Any] = None

    def to_json(self) -> str:
        """Serialize to JSON for stdin"""
        return json.dumps(asdict(self), default=str)

    @staticmethod
    def from_json(json_str: str) -> 'HookContext':
        """Deserialize from JSON"""
        data = json.loads(json_str)
        if data.get('tool_call'):
            data['tool_call'] = ToolCall(**data['tool_call'])
        if data.get('tool_result'):
            data['tool_result'] = ToolResult(**data['tool_result'])
        return HookContext(**data)

# Usage in hook:
# INPUT=$(cat)  # Receives structured JSON
# python -c "import json; ctx = json.loads(input()); print(ctx['tool_call']['name'])"
```

**Hook stdin receives:**

```json
{
  "worker_id": "worker-1",
  "run_id": "R42a3",
  "event_type": "pre_tool_use",
  "tool_call": {
    "name": "Bash",
    "parameters": {
      "command": "rm important.txt"
    }
  },
  "metadata": {
    "timestamp": "2025-11-10T15:30:00Z",
    "progress": 45
  }
}
```

#### 1.3 Matcher-Based Filtering

**Configuration:**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "command": "python -m hooks.bash_validator"
      },
      {
        "matcher": "Write|Edit",
        "command": "python -m hooks.file_validator"
      }
    ]
  }
}
```

**Implementation:**

```python
# hooks/hook_executor.py
import re

def should_execute_hook(hook_config: dict, context: HookContext) -> bool:
    """Check if hook should execute based on matcher."""
    if 'matcher' not in hook_config:
        return True  # No matcher = always execute

    matcher = hook_config['matcher']
    tool_name = context.tool_call.name if context.tool_call else ""

    # Support regex patterns
    return bool(re.match(matcher, tool_name))

# Usage:
for hook in hooks_config['PreToolUse']:
    if should_execute_hook(hook, context):
        result = execute_hook(hook['command'], context)
```

#### 1.4 Tool Input Modification

**PreToolUse Hook Pattern:**

```python
# hooks/pre_tool_use.py
import sys
import json
from shared.hook_context import HookContext
from shared.hook_actions import HookResult

# Read context
context = HookContext.from_json(sys.stdin.read())

# Modify tool input
if context.tool_call.name == "Bash":
    command = context.tool_call.parameters['command']

    # Add safety flag to rm
    if command.startswith("rm ") and "-i" not in command:
        modified = command.replace("rm ", "rm -i ")
        context.tool_call.parameters['command'] = modified

# Return modified context
print(context.to_json())
sys.exit(0)
```

**Hook Executor:**

```python
# Invoke hook
result = subprocess.run(
    hook_command,
    input=context.to_json(),
    capture_output=True,
    text=True
)

if result.returncode == 0 and result.stdout:
    # Parse modified context
    modified_context = HookContext.from_json(result.stdout)

    # Update tool input
    if modified_context.tool_call:
        tool_input = modified_context.tool_call.parameters
```

### Priority 2: Important (Next Phase)

#### 2.1 Database Views

**Add to schema:**

```sql
-- Efficient worker status view
CREATE VIEW worker_status AS
SELECT
    w.id,
    w.state,
    w.progress,
    w.last_heartbeat,
    COUNT(DISTINCT t.id) as assigned_tasks,
    COUNT(DISTINCT CASE WHEN t.state = 'completed' THEN t.id END) as completed_tasks
FROM workers w
LEFT JOIN tasks t ON w.id = t.assigned_worker
GROUP BY w.id;

-- Ready artifacts view (already in V2 query)
CREATE VIEW ready_artifacts AS
SELECT DISTINCT json_extract(e.payload, '$.path') as path
FROM events e
JOIN tasks t ON e.task_id = t.id
WHERE e.event_type = 'artifact'
AND t.state = 'completed'
AND json_extract(e.payload, '$.path') IS NOT NULL;

-- Run summary view
CREATE VIEW run_summary AS
SELECT
    run_id,
    COUNT(DISTINCT worker_id) as total_workers,
    COUNT(DISTINCT task_id) as total_tasks,
    MIN(timestamp) as started_at,
    MAX(timestamp) as last_activity
FROM events
GROUP BY run_id;
```

#### 2.2 Cleanup Procedures

**Add to schema:**

```python
# shared/event_store_v2.py

def cleanup_old_events(self, days: int = 30):
    """Remove events older than N days."""
    cutoff = datetime.now() - timedelta(days=days)
    with self.transaction() as conn:
        conn.execute("""
            DELETE FROM events
            WHERE datetime(timestamp) < datetime(?)
        """, (cutoff.isoformat(),))

def cleanup_expired_blocks(self):
    """Remove expired blocks (already implemented in get_active_blocks)."""
    with self.transaction() as conn:
        conn.execute("""
            DELETE FROM blocks
            WHERE datetime(expires_at) < datetime('now')
        """)

def cleanup_dead_workers(self, timeout_seconds: int = 300):
    """Mark workers as dead if no heartbeat."""
    with self.transaction() as conn:
        conn.execute("""
            UPDATE workers
            SET state = 'dead'
            WHERE state IN ('busy', 'blocked')
            AND datetime(last_heartbeat) < datetime('now', ? || ' seconds')
        """, (f'-{timeout_seconds}',))
```

#### 2.3 Additional Hook Events

**Extend EventType:**

```python
# shared/models.py
class EventType(Enum):
    # Existing
    START = "start"
    PROGRESS = "progress"
    ARTIFACT = "artifact"
    ERROR = "error"
    DONE = "done"
    MERGE_READY = "merge_ready"
    HEARTBEAT = "heartbeat"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"

    # New
    WORKER_STEP = "worker_step"      # After each Claude response
    WORKER_STOP = "worker_stop"      # When worker completes
    CONTEXT_WARNING = "context_warning"  # Token usage alerts
```

**Hook Events:**

```json
{
  "hooks": {
    "WorkerStep": [{
      "hooks": [{
        "type": "command",
        "command": "python -m hooks.on_worker_step"
      }]
    }],
    "ContextWarning": [{
      "hooks": [{
        "type": "command",
        "command": "python -m hooks.on_context_warning"
      }]
    }]
  }
}
```

### Priority 3: Optional Enhancements

#### 3.1 Git Worktree Management

**Implementation:**

```python
# shared/worktree_manager.py
from pathlib import Path
import subprocess
import hashlib

class WorktreeManager:
    def __init__(self, base_dir: Path = Path.home() / ".claudeparallel" / "worktrees"):
        self.base_dir = base_dir

    def create_worktree(self, run_id: str, worker_id: str, branch: str = None) -> Path:
        """Create isolated worktree for worker."""
        # Hash repo path to avoid collisions
        repo_path = Path.cwd()
        repo_hash = hashlib.md5(str(repo_path).encode()).hexdigest()[:8]

        # Worktree path: ~/.claudeparallel/worktrees/{run_id}/{repo_hash}/{worker_id}
        worktree_path = self.base_dir / run_id / f"{repo_path.name}-{repo_hash}" / worker_id
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Create Git worktree
        branch_name = branch or f"worker-{worker_id}"
        subprocess.run([
            "git", "worktree", "add",
            str(worktree_path),
            "-b", branch_name
        ], check=True)

        return worktree_path

    def cleanup_worktree(self, worktree_path: Path):
        """Remove worktree."""
        subprocess.run([
            "git", "worktree", "remove",
            str(worktree_path),
            "--force"
        ], check=True)

    def cleanup_run(self, run_id: str):
        """Remove all worktrees for a run."""
        run_dir = self.base_dir / run_id
        if run_dir.exists():
            for worktree in run_dir.glob("*/*"):
                if worktree.is_dir():
                    self.cleanup_worktree(worktree)
            run_dir.rmdir()
```

#### 3.2 Inter-Worker Messaging

**Schema:**

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_worker TEXT NOT NULL,
    to_worker TEXT NOT NULL,
    message_type TEXT NOT NULL,
    content JSON NOT NULL,
    status TEXT DEFAULT 'sent',  -- sent, delivered, failed
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    delivered_at TEXT
);

CREATE INDEX idx_messages_to ON messages(to_worker, status);
```

**API:**

```python
def send_message(self, from_worker: str, to_worker: str, message_type: str, content: dict):
    """Send message between workers."""
    with self.transaction() as conn:
        conn.execute("""
            INSERT INTO messages (from_worker, to_worker, message_type, content)
            VALUES (?, ?, ?, json(?))
        """, (from_worker, to_worker, message_type, json.dumps(content)))

def receive_messages(self, worker_id: str, mark_delivered: bool = True) -> List[Dict]:
    """Retrieve messages for worker."""
    with self.transaction() as conn:
        cursor = conn.execute("""
            SELECT * FROM messages
            WHERE to_worker = ? AND status = 'sent'
            ORDER BY created_at
        """, (worker_id,))

        messages = [dict(row) for row in cursor.fetchall()]

        if mark_delivered:
            conn.execute("""
                UPDATE messages
                SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP
                WHERE to_worker = ? AND status = 'sent'
            """, (worker_id,))

        return messages
```

## Implementation Roadmap

### Week 1: Hook Actions & Context
- [ ] Implement HookResult class with 6 actions
- [ ] Implement HookContext dataclass
- [ ] Update hook executor to parse actions from stdout
- [ ] Add backward compatibility (exit code 2 = halt)
- [ ] Update documentation

### Week 2: Matchers & Input Modification
- [ ] Implement matcher-based filtering
- [ ] Support tool input modification in PreToolUse
- [ ] Update hook examples
- [ ] Add safety validation hook (bash, file operations)

### Week 3: Database Improvements
- [ ] Add database views (worker_status, ready_artifacts, run_summary)
- [ ] Implement cleanup procedures
- [ ] Add performance metrics tracking
- [ ] Optimize queries with views

### Week 4: Additional Events & Testing
- [ ] Add worker_step, worker_stop, context_warning events
- [ ] Write comprehensive tests for all hook actions
- [ ] Test tool input modification
- [ ] Performance benchmarking

### Future: Optional Enhancements
- [ ] Git worktree management
- [ ] Inter-worker messaging
- [ ] SwarmMemory-style knowledge store

## Conclusion

Our investigation of claude-flow and SwarmSDK validates our core architectural decisions while revealing critical patterns we must adopt:

**Validated Decisions:**
- ✅ SQLite for state management
- ✅ Hooks for coordination
- ✅ Multi-process for true parallelism (despite SwarmSDK's pivot)

**Critical Additions Needed:**
- ⭐⭐⭐⭐⭐ Hook Actions system (6 actions)
- ⭐⭐⭐⭐⭐ Hook Context object
- ⭐⭐⭐⭐⭐ Tool input modification
- ⭐⭐⭐⭐ Matcher-based filtering
- ⭐⭐⭐ Database views for performance

**Lessons Learned:**
- IPC overhead is real but manageable with low-frequency coordination
- Hooks are more powerful than we initially designed (6 actions vs 2 exit codes)
- Tool input modification is a critical capability
- Database views dramatically improve query performance
- Git worktrees provide filesystem isolation without repo duplication

The next phase is to implement Priority 1 improvements to bring our architecture to production-ready status.
