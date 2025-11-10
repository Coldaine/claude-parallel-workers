# Claude Parallel Workers Implementation Plan

## Overview
Implementation of a parallel execution system using Claude Code's native hook functionality to orchestrate multiple worker processes, enabling true parallelism while maintaining a responsive single Claude session.

## Architecture Summary

### Core Components
1. **Hooks** (Shell/Python scripts executed by Claude Code)
   - UserPromptSubmit - Detects parallelizable work, spawns orchestrator
   - PreToolUse - Rewrites tool inputs for merge operations
   - PostToolUse - Injects worker status into context
   - Stop - Gates session termination until workers complete

2. **Orchestrator** (Python process spawned from hooks)
   - Parses prompts to detect parallelizable tasks
   - Creates execution plans (task dependency graphs)
   - Spawns and monitors worker processes
   - Manages shared state via filesystem

3. **Workers** (Detached Python processes)
   - Execute independent subtasks in parallel
   - Write events to append-only log
   - Produce artifacts in isolated directories
   - Report progress and completion status

4. **Shared Store** (Filesystem-based coordination)
   - `.claude/runs/<RUN_ID>/` directory structure
   - `plan.json` - Task dependency graph
   - `events.jsonl` - Append-only event log
   - `workers/W<N>/out/` - Worker artifacts
   - `status.json` - Derived status (optional)

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

#### 1.1 Directory Structure
```
claude-parallel-hooks/
├── README.md
├── IMPLEMENTATION_PLAN.md
├── hooks/
│   ├── user_prompt_submit.py
│   ├── pre_tool_use.py
│   ├── post_tool_use.py
│   └── stop.py
├── orchestrator/
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── task_parser.py
│   ├── plan_generator.py
│   └── worker_manager.py
├── worker/
│   ├── __init__.py
│   ├── worker.py
│   ├── task_executor.py
│   └── event_logger.py
├── shared/
│   ├── __init__.py
│   ├── event_store.py
│   ├── models.py
│   └── utils.py
├── tests/
│   ├── test_hooks.py
│   ├── test_orchestrator.py
│   ├── test_worker.py
│   └── fixtures/
├── examples/
│   ├── parallel_data_processing.md
│   ├── multi_file_analysis.md
│   └── distributed_testing.md
├── settings/
│   ├── example.claude.settings.json
│   └── install.sh
└── requirements.txt
```

#### 1.2 Core Models & Shared Components
- Event types (start, progress, artifact, error, done)
- Task model (id, deps, description, inputs, outputs)
- Plan model (run_id, tasks, workers)
- Event store interface (append, read, query)
- Logging utilities

### Phase 2: Hook Implementation (Week 2)

#### 2.1 UserPromptSubmit Hook
**Purpose**: Detect parallelizable work and spawn orchestrator
**Implementation**:
```python
# Responsibilities:
- Parse incoming prompt from stdin
- Detect parallel patterns (e.g., "process files A, B, C", "run tests on X, Y, Z")
- Generate unique RUN_ID
- Spawn orchestrator process (detached)
- Return initial status to stdout for context injection
```

#### 2.2 PostToolUse Hook
**Purpose**: Inject worker status after each tool use
**Implementation**:
```python
# Responsibilities:
- Read current run_id from environment or state file
- Query events.jsonl for latest worker status
- Generate compact status line
- Return JSON with additionalContext
```

#### 2.3 PreToolUse Hook
**Purpose**: Rewrite merge/combine tool inputs
**Implementation**:
```python
# Responsibilities:
- Detect merge/combine operations
- Check worker completion status
- If ready: rewrite tool inputs with artifact paths
- If not ready: block with appropriate decision
- Return JSON with updatedInput and permissionDecision
```

#### 2.4 Stop Hook
**Purpose**: Prevent premature session termination
**Implementation**:
```python
# Responsibilities:
- Check all worker completion status
- If workers pending: return decision:block with reason
- If all complete: allow termination
```

### Phase 3: Orchestrator Development (Week 3)

#### 3.1 Task Parser
- Pattern recognition for parallelizable tasks
- Dependency extraction
- Resource estimation

#### 3.2 Plan Generator
- Create task dependency DAG
- Assign workers to tasks
- Optimize execution order
- Handle resource constraints

#### 3.3 Worker Manager
- Spawn worker processes (detached)
- Monitor worker health via events
- Implement retry logic
- Handle worker failures

### Phase 4: Worker Implementation (Week 4)

#### 4.1 Worker Core
- Task execution framework
- Event emission (progress, artifacts, errors)
- Dependency waiting logic
- State machine implementation

#### 4.2 Task Executors
- File processing executor
- Command execution executor
- API call executor
- Custom executor interface

#### 4.3 Artifact Management
- Output file handling
- Result aggregation
- Cleanup procedures

### Phase 5: Testing & Examples (Week 5)

#### 5.1 Unit Tests
- Hook behavior tests
- Orchestrator logic tests
- Worker state machine tests
- Event store concurrency tests

#### 5.2 Integration Tests
- End-to-end parallel execution
- Failure recovery scenarios
- Dependency handling
- Merge coordination

#### 5.3 Example Scenarios
- Parallel file processing
- Distributed testing
- Multi-stage data pipeline
- Concurrent API operations

## Technical Specifications

### Event Schema
```json
{
  "t": "start|progress|artifact|error|done",
  "ts": "ISO-8601 timestamp",
  "w": "worker_id",
  "task": "task_id",
  "msg": "optional message",
  "path": "artifact path (for artifact events)",
  "pct": "progress percentage (0-100)",
  "error": "error details (for error events)"
}
```

### Plan Schema
```json
{
  "run_id": "unique identifier",
  "created_at": "ISO-8601 timestamp",
  "prompt": "original user prompt",
  "tasks": [
    {
      "id": "task identifier",
      "description": "human-readable description",
      "deps": ["dependency task ids"],
      "inputs": {},
      "outputs": {},
      "worker_hint": "preferred worker type"
    }
  ],
  "workers": [
    {
      "id": "W1",
      "task": "task_id",
      "cmd": ["python", "worker.py", "--task", "task_id"]
    }
  ]
}
```

### Hook Configuration (settings.json)
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python $CLAUDE_PROJECT_DIR/hooks/user_prompt_submit.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python $CLAUDE_PROJECT_DIR/hooks/post_tool_use.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python $CLAUDE_PROJECT_DIR/hooks/pre_tool_use.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python $CLAUDE_PROJECT_DIR/hooks/stop.py"
          }
        ]
      }
    ]
  }
}
```

## Key Implementation Considerations

### 1. Non-Blocking Hooks
- Hooks must return quickly (<1 second ideal, <5 seconds max)
- Use process detachment for long-running operations
- Implement timeouts in hook configuration

### 2. Concurrency Safety
- Use append-only writes for events.jsonl
- Implement file locking for status.json updates
- Handle race conditions in artifact creation

### 3. Error Recovery
- Graceful worker failure handling
- Retry mechanisms with exponential backoff
- Partial result aggregation
- Cleanup of orphaned processes

### 4. Performance Optimization
- Efficient event log querying
- Cached status derivation
- Minimal context injection
- Resource pooling for workers

### 5. Security
- Validate all hook inputs
- Sanitize paths to prevent traversal
- Limit worker process permissions
- Audit event logging

## Success Metrics

1. **Functionality**
   - Successfully parallelize 3+ tasks
   - Handle task dependencies correctly
   - Recover from worker failures
   - Complete merge operations

2. **Performance**
   - Hook response time <1 second
   - Worker spawn time <2 seconds
   - Status injection overhead <100ms
   - Support 10+ concurrent workers

3. **Reliability**
   - No orphaned processes
   - Clean session termination
   - Consistent state after crashes
   - Idempotent operations

4. **Usability**
   - Clear status reporting
   - Intuitive prompt patterns
   - Helpful error messages
   - Simple installation process

## Next Steps

1. Set up project structure
2. Implement shared components and models
3. Create minimal UserPromptSubmit hook
4. Build basic orchestrator with worker spawning
5. Implement event logging
6. Add status injection via PostToolUse
7. Implement merge coordination in PreToolUse
8. Add Stop hook for completion gating
9. Test end-to-end flow
10. Document and create examples

## Resources

- [Claude Code Hooks Documentation](https://code.claude.com/docs/en/hooks)
- [Interactive Mode Documentation](https://code.claude.com/docs/en/interactive-mode)
- Python subprocess documentation
- JSON Lines specification