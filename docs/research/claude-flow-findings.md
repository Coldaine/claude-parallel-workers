# claude-flow Investigation Findings

## Overview
**Repository**: https://github.com/ruvnet/claude-flow
**Investigation Date**: 2025-11-10
**Priority**: CRITICAL ⭐⭐⭐⭐⭐

## Key Architectural Decisions

### 1. Database Schema (SQLite/PostgreSQL/MySQL)

**File**: `src/api/database-schema.sql`

Claude-flow uses a comprehensive database schema instead of flat files:

#### Core Tables:
```sql
swarms (id, name, topology, max_agents, strategy, status, config)
agents (id, swarm_id, type, name, status, capabilities, config)
tasks (id, swarm_id, description, priority, strategy, status, result)
task_assignments (task_id, agent_id, status, started_at, completed_at)
resources (id, name, type, capacity, status)
resource_allocations (resource_id, agent_id, allocated_at, released_at)
messages (from_agent_id, to_agent_id, message_type, content, status)
performance_metrics (swarm_id, agent_id, metric_type, metric_value, timestamp)
events (swarm_id, agent_id, event_type, event_name, event_data, severity)
sessions (id, session_type, user_id, client_info, status, expires_at)
configuration (category, key_name, key_value, is_encrypted)
memory_store (namespace, key_name, value, ttl, expires_at)
```

#### Key Features:
- **ENUM types** for states (agent: spawning/idle/busy/error/terminated)
- **JSON fields** for flexible metadata
- **Foreign keys** for referential integrity
- **Indexes** on common query patterns
- **Views** for complex queries (active_swarms, swarm_metrics, resource_utilization)
- **Stored procedures** for cleanup (CleanupExpiredSessions, CleanupOldEvents)
- **TTL support** in memory_store for automatic expiry

**Implications for our architecture:**
- ✅ Validates our V2 decision to use SQLite
- ✅ Shows importance of indexes for performance
- ✅ Demonstrates value of views for common queries
- ✅ TTL pattern for automatic cleanup
- 📋 TODO: Add resource allocation tracking
- 📋 TODO: Add inter-worker messaging table

### 2. Hook Configuration Pattern

**File**: `.claude/settings.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "cat | jq -r '.tool_input.command // empty' | tr '\\n' '\\0' | xargs -0 -I {} npx claude-flow@alpha hooks pre-command --command '{}'"
        }]
      },
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [{
          "type": "command",
          "command": "cat | jq -r '.tool_input.file_path // .tool_input.path // empty' | tr '\\n' '\\0' | xargs -0 -I {} npx claude-flow@alpha hooks pre-edit --file '{}'"
        }]
      }
    ],
    "PostToolUse": [...],
    "PreCompact": [...],
    "Stop": [...]
  }
}
```

**Pattern Breakdown:**
1. **Matcher** filters which tools trigger the hook (Bash, Write|Edit|MultiEdit)
2. **JSON Parsing** with `jq` extracts specific fields
3. **xargs** safely passes extracted values to CLI commands
4. **CLI invocation** calls `npx claude-flow@alpha hooks <event>` with parameters

**Tool Input Extraction:**
- `'.tool_input.command // empty'` - Bash command
- `'.tool_input.file_path // .tool_input.path // empty'` - File path (handles both Write and Edit)
- Uses `tr '\\n' '\\0' | xargs -0` for proper null-separated values (handles spaces)

**Implications:**
- ✅ Demonstrates proper JSON parsing in hooks
- ✅ Shows safe argument passing with null-separated xargs
- ✅ CLI-based hook implementation (npx callable)
- 📋 TODO: Implement similar CLI for our hooks
- 📋 TODO: Add matcher-based filtering

### 3. Hook Implementation (bash-hook.sh)

**File**: `hooks/bash-hook.sh` (2987 bytes)

**Capabilities:**
1. **Safety Checks** - Adds `-i` flag to dangerous rm commands
2. **Command Aliases** - Expands ll→ls -lah, la→ls -la, ..→cd ..
3. **Path Correction** - Redirects test files to /tmp
4. **Secret Detection** - Warns about password/token keywords
5. **Dependency Validation** - Checks if commands exist, suggests installation
6. **Output Modification** - Returns modified JSON with updated command

**Implementation Pattern:**
```bash
#!/bin/bash
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Modify command based on rules
MODIFIED_COMMAND="$COMMAND"

# [Apply transformations...]

# Output modified JSON
echo "$INPUT" | jq --arg cmd "$MODIFIED_COMMAND" --arg desc "$DESCRIPTION" \
  '.tool_input.command = $cmd | .tool_input.description = ((.tool_input.description // "") + " " + $desc)'
```

**Key Insight**: Hooks can **modify tool inputs** before execution by returning updated JSON.

**Implications:**
- ✅ Shows how to transform tool inputs dynamically
- ✅ Demonstrates safety injection patterns
- ✅ Proper JSON manipulation with jq
- 📋 TODO: Implement similar safety checks in our hooks
- 📋 TODO: Add command transformation capabilities

### 4. Concurrent Execution Philosophy

**File**: `CLAUDE.md`

**GOLDEN RULE**: "1 MESSAGE = ALL RELATED OPERATIONS"

**Mandatory Patterns:**
- **TodoWrite**: Batch ALL todos in ONE call (5-10+ minimum)
- **Task tool**: Spawn ALL agents in ONE message
- **File operations**: Batch ALL reads/writes/edits
- **Bash commands**: Batch ALL terminal operations

**Agent Coordination Protocol:**
```bash
# Before work
npx claude-flow@alpha hooks pre-task --description "[task]"
npx claude-flow@alpha hooks session-restore --session-id "swarm-[id]"

# During work
npx claude-flow@alpha hooks post-edit --file "[file]" --memory-key "swarm/[agent]/[step]"
npx claude-flow@alpha hooks notify --message "[what was done]"

# After work
npx claude-flow@alpha hooks post-task --task-id "[task]"
npx claude-flow@alpha hooks session-end --export-metrics true
```

**Implications:**
- ✅ Validates importance of batching operations
- ✅ Shows structured agent coordination protocol
- ✅ Memory-based context sharing pattern
- 📋 TODO: Define our coordination protocol
- 📋 TODO: Implement session restoration

### 5. File Organization

**Never save to root folder:**
- `/src` - Source code
- `/tests` - Test files
- `/docs` - Documentation
- `/config` - Configuration
- `/scripts` - Utility scripts
- `/examples` - Examples

**Implications:**
- ✅ Clean project structure
- 📋 TODO: Enforce similar structure in our project

## Critical Patterns to Extract

### 1. CLI-Based Hook System

**Current Implementation:**
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "npx claude-flow@alpha hooks pre-command --command '{extracted_value}'"
      }]
    }]
  }
}
```

**For Our Architecture:**
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "python -m hooks.pre_tool_use"
      }]
    }]
  }
}
```

### 2. Tool Input Modification

**Pattern:**
```bash
INPUT=$(cat)
MODIFIED=$(transform "$INPUT")
echo "$MODIFIED"
exit 0  # Allow with modifications
```

**Applications:**
- Inject worker context into commands
- Add safety flags to dangerous operations
- Redirect paths for isolation
- Validate arguments

### 3. Database Views for Efficiency

**Instead of:**
```python
# Compute status by reading all events
events = store.read_events()
status = compute_status(events)
```

**Use:**
```sql
CREATE VIEW swarm_metrics AS
SELECT
    swarm_id,
    COUNT(DISTINCT CASE WHEN status = 'completed' THEN id END) as completed_tasks,
    AVG(TIMESTAMPDIFF(SECOND, started_at, completed_at)) as avg_duration
FROM tasks
GROUP BY swarm_id;
```

### 4. Memory Store with TTL

**Schema:**
```sql
CREATE TABLE memory_store (
    namespace VARCHAR(255),
    key_name VARCHAR(255),
    value JSON,
    ttl INTEGER,  -- seconds
    expires_at TIMESTAMP
);
```

**Usage:**
```python
# Worker stores checkpoint
store.set_memory(
    namespace="swarm/worker-1",
    key="checkpoint-phase2",
    value={"status": "ready", "output": "results.json"},
    ttl=3600  # 1 hour
)

# Other workers read
checkpoint = store.get_memory(
    namespace="swarm/worker-1",
    key="checkpoint-phase2"
)
```

## Recommendations for Our Architecture

### Immediate Adoption (Must Have):
1. ✅ **SQLite with comprehensive schema** - Already in V2
2. 📋 **Add database views** for common queries
3. 📋 **Implement CLI-based hooks** (python -m hooks.pre_tool_use)
4. 📋 **Tool input modification** pattern
5. 📋 **Memory store with TTL** for worker coordination

### Consider Adding (Nice to Have):
1. 📋 **Resource allocation tracking** table
2. 📋 **Inter-worker messaging** table
3. 📋 **Cleanup stored procedures**
4. 📋 **Performance metrics** table
5. 📋 **Session management** table

### Validation Points:
- ✅ SQLite is the right choice (claude-flow uses it too)
- ✅ JSON payloads for extensibility
- ✅ Indexes for performance
- ✅ ACID guarantees from transactions
- ✅ Concurrent execution philosophy aligns

## Next Steps

1. Read remaining hook scripts (file-hook.sh, git-commit-hook.sh)
2. Examine orchestrator code (src/core/orchestrator.js, src/swarm/advanced-orchestrator.js)
3. Review worker implementation (src/swarm/workers/)
4. Document performance monitoring patterns
5. Extract MCP server integration patterns

## Files to Examine Next

Priority order:
1. `hooks/file-hook.sh` - File operation hooks
2. `hooks/git-commit-hook.sh` - Git integration
3. `src/core/orchestrator.js` - Core orchestration logic
4. `src/swarm/advanced-orchestrator.js` - Advanced patterns
5. `src/swarm/workers/` - Worker implementation
