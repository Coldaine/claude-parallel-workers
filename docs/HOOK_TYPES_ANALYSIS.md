# Claude Code Hooks Analysis - Comprehensive Report

## I. The 4 Hooks Implemented in Claude Parallel Workers

### 1. **UserPromptSubmit**
**Location**: Called when user submits a prompt to Claude Code
**Responsibilities**:
- Detect parallelizable task patterns from user input
- Create execution plan with task dependencies
- Spawn orchestrator process (detached)
- Generate and set unique run ID
- Return initial status to stdout for context injection

**Example Use Case**: 
```
User: "Analyze security vulnerabilities in login.py, auth.py, and session.py"
→ Hook detects 3-file analysis pattern
→ Spawns W1, W2, W3 workers
→ Returns: "Analyzing 3 files in parallel (Run R42)"
```

### 2. **PostToolUse**
**Location**: Called after each tool execution (Read, Write, Bash, etc.)
**Responsibilities**:
- Read worker progress from events.jsonl
- Compute current status snapshot
- Generate compact status line
- Inject status as additional context to conductor

**Example Status Injection**:
```
R42 — W1 80% processing; W2 ✓ done; W3 45% analyzing
```

### 3. **PreToolUse**
**Location**: Called before each tool use (Read, Write, Bash, etc.)
**Responsibilities**:
- Detect merge/combine operations
- Check if all dependencies are satisfied
- Rewrite tool inputs with actual artifact paths
- Block execution if workers aren't ready (exit code 2)

**Example Rewrite Pattern**:
```
Original input: merge_reports(report_a, report_b, report_c)
↓ (PreToolUse rewrites to)
merge_reports(
  workers/W1/out/vulnerabilities.json,
  workers/W2/out/vulnerabilities.json,
  workers/W3/out/vulnerabilities.json
)
```

### 4. **Stop**
**Location**: Called when conductor attempts to end the session
**Responsibilities**:
- Check all worker completion status
- Block termination if workers are pending (exit code 2)
- Allow graceful termination when all workers complete
- Ensure no orphaned processes

---

## II. Alternative & Additional Hook Types Mentioned in Research

### Available but NOT implemented:

| Hook Type | Source | Purpose | Status |
|-----------|--------|---------|--------|
| **SessionStart** | ARCHITECTURE_UNDERSTANDING.md | Resume interrupted work, check for orphaned workers, pre-warm worker pools | Optional |
| **SessionEnd** | Research docs | Session cleanup, save state, generate summaries | Covered by Stop |
| **PreCompact** | claude-flow findings | Run before context compaction | Not needed for parallel exec |
| **WorkerStep** | synthesis-and-recommendations.md | After each Claude response mid-execution | Future enhancement |
| **WorkerStop** | synthesis-and-recommendations.md | When worker completes | Future enhancement |
| **ContextWarning** | synthesis-and-recommendations.md | Token usage alerts (80%, 90%) | Future enhancement |

### In Other Frameworks (Reference Only):

**SwarmSDK (13 hook events)**:
- on_pre_tool, on_post_tool, on_user_message, on_pre_response
- Additional 9 more specific events

**claude-flow (10+ hook events)**:
- pre-task, post-task, pre-edit, post-edit, pre-command, post-command
- session-start, session-end, beforeCommit, afterDeploy

**Community "Beast Mode" (3 hooks)**:
- PreToolUse (redirect to session index)
- PostToolUse (add to session index)
- Stop (create branch from session index)

---

## III. Why ONLY 4 Hooks Were Chosen

### Design Principle: Minimal Viable Implementation

The 4-hook design represents a **minimal viable set** that solves the core parallel execution problem:

```
UserPromptSubmit  →  [Spawn workers + detect tasks]
    ↓
   [Conductor proceeds with normal tool usage]
    ↓
PostToolUse       →  [Inject status updates] (on EVERY tool use)
    ↓
PreToolUse        →  [Rewrite merge operations] (before certain tools)
    ↓
Stop              →  [Verify completion] (at session end)
```

### Criteria for Hook Selection:

1. **Covers All Critical Lifecycle Points**:
   - ✅ Task detection & spawning (UserPromptSubmit)
   - ✅ Parallel execution feedback (PostToolUse)
   - ✅ Merge coordination (PreToolUse)
   - ✅ Completion verification (Stop)

2. **Minimal Overhead**:
   - Fewer hooks = fewer subprocess invocations
   - Each hook must return quickly (<1 second ideal)
   - 4 hooks provide necessary functionality without bloat

3. **No Redundancy**:
   - SessionStart: Not needed (parallel spawned at UserPromptSubmit)
   - SessionEnd: Covered by Stop hook
   - ContextWarning: Future enhancement, not core to parallelism
   - WorkerStep: Too granular, adds overhead

4. **Sufficient Control Flow**:
   - Exit code 0: Allow/continue
   - Exit code 2: Block/retry
   - JSON output: Modify inputs (PreToolUse)
   - Covers: { allow, block, modify } operations

### Evidence from Documentation:

**From IMPLEMENTATION_PLAN.md**:
```
### Phase 2: Hook Implementation (Week 2)

2.1 UserPromptSubmit Hook - "Main spawn point"
2.2 PostToolUse Hook     - "Inject worker status"
2.3 PreToolUse Hook      - "Rewrite merge/combine tool inputs"
2.4 Stop Hook            - "Prevent premature session termination"
```

**From README.md (architecture diagram)**:
```
[Hooks Layer]
├── UserPromptSubmit → Detect & Plan → Spawn Orchestrator
├── PostToolUse → Read Status → Inject Context
├── PreToolUse → Check Dependencies → Rewrite Inputs
└── Stop → Verify Completion → Gate Termination
```

---

## IV. Gap Analysis: What's Missing

### From Research Recommendations (synthesis-and-recommendations.md):

**Priority 1 - Critical Additions Needed** (⭐⭐⭐⭐⭐):
1. Hook Actions system (6 actions: continue, halt, replace, reprompt, finish_worker, finish_run)
   - Current: Only exit codes 0 & 2
   - Proposed: Rich action system from SwarmSDK

2. Hook Context object (structured input)
   - Current: JSON via stdin (minimal structure)
   - Proposed: Rich context with tool_call, tool_result, metadata

3. Tool input modification
   - Current: PreToolUse can block or inject context
   - Proposed: Can modify tool parameters directly

**Priority 2 - Important Enhancements** (⭐⭐⭐⭐):
1. Matcher-based filtering (only fire hooks for specific tools)
2. Database views for efficient queries
3. Cleanup procedures for expired blocks

**Priority 3 - Optional Enhancements** (⭐⭐⭐):
1. SessionStart hook (for resuming interrupted work)
2. WorkerStep, WorkerStop, ContextWarning events
3. Git worktree management

---

## V. Hook Configuration Example (Current Implementation)

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python $CLAUDE_PROJECT_DIR/hooks/user_prompt_submit.py"
      }]
    }],
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python $CLAUDE_PROJECT_DIR/hooks/post_tool_use.py"
      }]
    }],
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python $CLAUDE_PROJECT_DIR/hooks/pre_tool_use.py"
      }]
    }],
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "python $CLAUDE_PROJECT_DIR/hooks/stop.py"
      }]
    }]
  }
}
```

---

## VI. Comparison: Our 4 Hooks vs Other Frameworks

| Framework | Hook Count | Hook Types | Philosophy |
|-----------|-----------|-----------|-----------|
| **Claude Parallel** | 4 | UserPromptSubmit, PreToolUse, PostToolUse, Stop | Minimal viable for parallel execution |
| **Community "Beast Mode"** | 3 | PreToolUse, PostToolUse, Stop | Git-centric isolation (no spawn) |
| **SwarmSDK** | 13 | on_pre_tool, on_post_tool, on_user_message, on_pre_response, ... | Comprehensive in-process orchestration |
| **claude-flow** | 10+ | pre-task, post-task, pre-edit, post-edit, session-start, ... | Comprehensive rules-based automation |

---

## VII. Design Decisions Summary

### ✅ Reasons the 4-Hook Choice is Sound:

1. **Solves the Core Problem**: Parallel task spawning, status tracking, merge coordination, completion verification
2. **Minimal Dependencies**: Uses only Python stdlib, no external packages required
3. **Fast Execution**: Each hook invocation must be quick (<1s); 4 hooks is manageable
4. **Clear Separation of Concerns**:
   - Spawn/detect → UserPromptSubmit
   - Read status → PostToolUse
   - Coordinate merge → PreToolUse
   - Verify done → Stop
5. **Extensible**: Can add SessionStart later if needed for resumption
6. **Matches Community Patterns**: Beast Mode uses just 3 hooks

### ⚠️ Limitations Acknowledged:

1. **No tool-specific filtering**: All PreToolUse/PostToolUse invocations fire (matcher support is future work)
2. **Simple control flow**: Only allow/block/inject-context (no replace, reprompt actions)
3. **No context warning**: Can't alert on token budget warnings
4. **No mid-execution hooks**: WorkerStep not implemented (could cause overhead anyway)
5. **Limited action types**: Only exit codes 0 & 2 (not 6+ actions like SwarmSDK)

---

## VIII. Hook Lifecycle Diagram

```
Session Start
    ↓
User submits prompt
    ↓
[UserPromptSubmit Hook] ← SPAWN WORKERS + DETECT TASKS
    ↓
Conductor responds & uses tools
    ├─→ Tool execution begins
    │   ↓
    │   [PreToolUse Hook] ← CHECK DEPENDENCIES + REWRITE INPUTS
    │   ↓
    │   Tool executes
    │   ↓
    │   [PostToolUse Hook] ← INJECT STATUS UPDATE
    │   ↓
    │   Context updated with status
    │   ↓
    └─→ Conductor continues with next tool
    ↓
(repeat tool loop until user asks to terminate)
    ↓
User ends session
    ↓
[Stop Hook] ← VERIFY ALL WORKERS COMPLETE + GATE TERMINATION
    ↓
Session ends
```

---

## IX. Referenced Configuration Locations

**From README.md (lines 59-87)**:
```
~/.claude/settings.json

or

./settings/install.sh (project-level installation)
```

**Hooks are loaded with priority**:
1. Global: `~/.claude/settings.json`
2. Project: `./.claude/settings.json`
3. Session: Runtime overrides (environment variables)

---

## X. Key Implementation Files

```
/home/user/claude-parallel-workers/
├── hooks/
│   ├── user_prompt_submit.py  ← Spawn point
│   ├── post_tool_use.py       ← Status injection
│   ├── pre_tool_use.py        ← Merge coordination
│   └── stop.py                ← Completion gating
├── shared/
│   ├── models.py              ← EventType, WorkerState, Plan
│   ├── utils.py               ← Hook utilities
│   └── event_store_v2.py      ← SQLite coordination
└── orchestrator/
    └── orchestrator.py        ← Spawned by UserPromptSubmit
```

