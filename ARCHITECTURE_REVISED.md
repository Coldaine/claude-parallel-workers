# REVISED Architecture: Workers Can Invoke Hooks!

## The Critical Insight We Missed

**Workers CAN talk to the Conductor directly by invoking Claude Code hooks themselves!** This changes everything:

1. Workers are independent processes that can call hooks
2. Workers can use exit code 2 to BLOCK the Conductor
3. Workers can inject information directly into context
4. Workers can coordinate synchronization points

## How Workers Communicate with Conductor

### Direct Communication Methods:

1. **Worker invokes a hook with exit code 0**
   - Injects information into Conductor's context
   - Non-blocking - Conductor continues

2. **Worker invokes a hook with exit code 2**
   - BLOCKS the Conductor at that hook point
   - Forces Conductor to wait/retry
   - Can provide error feedback via stderr

3. **Worker triggers custom hook events**
   - Could trigger PostToolUse to inject status
   - Could trigger PreToolUse to modify upcoming operations
   - Could trigger Stop to prevent premature termination

### Example: Worker Blocking Pattern

```python
# Worker detects Conductor is moving too fast
def worker_block_conductor():
    # Worker can invoke a hook that will fire in Conductor's context
    subprocess.run([
        "claude-code-hook",  # Hypothetical hook invocation
        "--event", "PostToolUse",
        "--exit-code", "2",  # BLOCK!
        "--stderr", "Worker W1 still processing, please wait..."
    ])
```

## Revised Workflow Examples

### Workflow 1: Worker-Driven Synchronization
```
User: "Process these large files: data1.csv, data2.csv, data3.csv"

1. UserPromptSubmit Hook:
   - Spawns W1, W2, W3 for parallel processing
   - Each worker monitors Conductor's progress

2. Conductor starts: "I'll process these files..."
   [Tries to Read data1.csv]

3. W1 intercepts via PreToolUse invocation:
   - W1 detects Conductor trying to read its file
   - W1 invokes: exit(2) with "W1 has already loaded data1.csv into memory"
   - Conductor is blocked from redundant read

4. W1 completes processing:
   - W1 invokes PostToolUse with exit(0)
   - Injects: "W1 complete: data1.csv processed, 10M rows analyzed"
   - Writes results to workers/W1/out/

5. When Conductor tries to merge:
   - All workers invoke PreToolUse to ensure readiness
   - Last worker to finish rewrites the merge inputs
```

### Workflow 2: Worker-Controlled Pacing
```
User: "Run performance benchmarks on all modules"

1. UserPromptSubmit spawns benchmark workers

2. Workers actively control pacing:
   - W1 invokes PreToolUse(exit=2) when Conductor moves too fast
   - "Benchmark still running, 60% complete, ETA 30s"
   - Conductor forced to wait and retry

3. Workers inject results directly:
   - W1 invokes PostToolUse(exit=0): "Module A: 1.2s avg, 0.1s stddev"
   - W2 invokes PostToolUse(exit=0): "Module B: 0.8s avg, 0.05s stddev"
```

### Workflow 3: Worker Error Escalation
```
User: "Deploy to staging, testing, and production"

1. Workers W1(staging), W2(testing), W3(production) spawned

2. W1 encounters error:
   - W1 invokes Stop hook with exit(2)
   - "CRITICAL: Staging deployment failed, blocking all deployments"
   - Conductor cannot terminate, must address issue

3. W3 implements safety check:
   - W3 waits for W1 and W2 success events
   - If either fails, W3 invokes Stop(exit=2)
   - "Production deployment blocked: prerequisite environments failed"
```

## Revised Communication Patterns

### Pattern 1: Worker Checkpoint Synchronization
```python
# Worker reaches checkpoint
def worker_checkpoint(checkpoint_name, data):
    # Invoke hook to inject checkpoint status
    result = invoke_hook(
        event="PostToolUse",
        json_output={
            "hookSpecificOutput": {
                "additionalContext": f"Worker {worker_id} reached {checkpoint_name}",
                "data": data
            }
        },
        exit_code=0  # Non-blocking
    )
```

### Pattern 2: Worker Blocks Until Ready
```python
# Worker prevents premature conductor action
def worker_guard_merge():
    if not all_workers_ready():
        invoke_hook(
            event="PreToolUse",
            stderr="Workers still processing: W1(80%), W2(done), W3(45%)",
            exit_code=2  # BLOCK!
        )
```

### Pattern 3: Worker Failure Escalation
```python
# Worker encounters critical error
def worker_critical_error(error):
    invoke_hook(
        event="Stop",
        json_output={
            "decision": "block",
            "reason": f"Worker {worker_id} critical failure: {error}"
        },
        exit_code=2  # Force conductor to address
    )
```

## Exit Code Strategy

### Exit Code 0 - Information/Success
- Workers inject status updates
- Workers provide completed results
- Workers signal phase completion
- Non-blocking, Conductor continues

### Exit Code 2 - Blocking/Control
- Workers prevent premature operations
- Workers force synchronization points
- Workers escalate critical errors
- Conductor must wait/retry/handle

### Other Exit Codes - Warnings
- Workers signal non-critical issues
- Workers provide debug information
- Logged but don't block Conductor

## Revised Architecture Rules

### What Workers CAN Do:
1. **Invoke hooks to communicate with Conductor**
2. **Block Conductor operations via exit code 2**
3. **Inject context via hook responses**
4. **Read/write anywhere they have permissions** (though they shouldn't write to other workers' dirs by convention)
5. **Coordinate complex synchronization patterns**
6. **Escalate errors that require Conductor attention**

### What Workers SHOULD Do:
1. **Use filesystem for async communication** (events.jsonl)
2. **Invoke hooks for sync points** (checkpoints, completion)
3. **Block via PreToolUse when Conductor shouldn't proceed**
4. **Inject status via PostToolUse for visibility**
5. **Use Stop hook to prevent premature termination**

### What Workers SHOULDN'T Do:
1. **Invoke hooks too frequently** (performance impact)
2. **Write to other workers' directories** (convention, not restriction)
3. **Modify plan.json** (immutable contract)
4. **Block unnecessarily** (degrades user experience)

## Powerful New Patterns

### Pattern: Worker-Managed Pipeline
```python
# Worker N completes and triggers Worker N+1
def worker_pipeline_handoff():
    # Write completion event
    append_event(Event(t="done", task=my_task))

    # Invoke hook to signal next worker
    invoke_hook(
        event="PostToolUse",
        json_output={
            "hookSpecificOutput": {
                "additionalContext": f"Pipeline: {my_task} → {next_task} ready"
            }
        }
    )

    # Next worker polls events and sees it can start
```

### Pattern: Worker Voting/Consensus
```python
# Workers coordinate to make group decision
def worker_consensus():
    # Each worker writes vote
    append_event(Event(t="vote", worker=worker_id, decision="proceed"))

    # Last worker tallies votes and decides
    votes = read_votes_from_events()
    if len(votes) >= required_quorum:
        if votes.count("proceed") > votes.count("abort"):
            invoke_hook(event="PostToolUse",
                       msg="Consensus: proceed",
                       exit_code=0)
        else:
            invoke_hook(event="Stop",
                       msg="Consensus: abort",
                       exit_code=2)
```

### Pattern: Worker Resource Management
```python
# Workers coordinate resource usage
def worker_acquire_resource(resource):
    # Check if resource available
    if resource_in_use():
        # Block conductor from conflicting operation
        invoke_hook(
            event="PreToolUse",
            stderr=f"Resource {resource} in use by {current_holder}",
            exit_code=2
        )
    else:
        # Claim resource
        append_event(Event(t="acquire", resource=resource, worker=worker_id))
```

## The Complete Picture

The system is now MUCH more powerful:

1. **Conductor** proceeds through normal tool usage
2. **Hooks** detect patterns and spawn workers
3. **Workers** execute in parallel AND can invoke hooks
4. **Filesystem** provides async communication (events.jsonl)
5. **Hook invocations** provide sync communication
6. **Exit codes** provide control flow (block/allow)

This creates a system where:
- Workers aren't just passive executors
- Workers actively participate in orchestration
- Workers can ensure correctness through blocking
- Workers can provide real-time feedback
- The Conductor becomes a true orchestrator, guided by worker feedback

## Implementation Priority

1. **Basic worker → filesystem communication** (events.jsonl)
2. **Worker → hook invocation mechanism**
3. **Exit code handling in workers**
4. **Synchronization patterns**
5. **Error escalation paths**
6. **Resource coordination**

This bidirectional communication makes the system incredibly flexible - workers aren't just executing tasks, they're active participants in the orchestration!