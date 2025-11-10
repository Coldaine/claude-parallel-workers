# Critical Architecture Understanding

## The Key Insight

**The main Claude Code session (Conductor) has NO IDEA it's orchestrating parallel work.** It proceeds normally through its tool calls while hooks secretly:
1. Spawn workers at the beginning
2. Inject status updates along the way
3. Rewrite tool inputs when merging
4. Block termination until workers complete

The Conductor thinks it's doing sequential work, but the hooks make it parallel!

## Where Workers Can Be Spawned

### Primary Spawn Points:
1. **UserPromptSubmit Hook** - Main spawn point
   - Has access to: User's prompt text (via stdin)
   - Can write to: .claude/runs/<RUN_ID>/ (creates it)
   - Spawns: Orchestrator → Workers (all detached)
   - Returns: Status line injected as context

2. **SessionStart Hook** (optional)
   - Could resume interrupted work
   - Check for orphaned workers from previous sessions
   - Pre-warm worker pools

### What Workers Can Access:

**READ:**
- `.claude/runs/<RUN_ID>/plan.json` - Task assignments and dependencies
- `.claude/runs/<RUN_ID>/events.jsonl` - Event stream from other workers
- `.claude/runs/<RUN_ID>/workers/W<N>/input/` - Their specific inputs
- System files (if given paths in plan)

**WRITE:**
- `.claude/runs/<RUN_ID>/events.jsonl` - Append-only event log
- `.claude/runs/<RUN_ID>/workers/W<N>/out/` - Their artifacts
- `.claude/runs/<RUN_ID>/workers/W<N>/logs/` - Their logs
- `/tmp/` or temp directories for intermediate work

**CANNOT:**
- Directly communicate with Conductor
- Modify other workers' output directories
- Write to plan.json (immutable after creation)

## Five Concrete Workflows

### Workflow 1: Multi-File Analysis
```
User: "Analyze security vulnerabilities in login.py, auth.py, and session.py"

1. UserPromptSubmit Hook:
   - Detects pattern: "analyze ... in [file1, file2, file3]"
   - Creates plan with 3 tasks (A: analyze login.py, B: analyze auth.py, C: analyze session.py)
   - Spawns W1, W2, W3
   - Returns: "Analyzing 3 files in parallel (Run R42)"

2. Conductor responds normally:
   "I'll analyze these files for security vulnerabilities..."
   [Uses Read tool on login.py]

3. PostToolUse Hook (after Read):
   - Reads events.jsonl: W1 50%, W2 30%, W3 45%
   - Injects: "R42: W1 50% scanning; W2 30% parsing; W3 45% analyzing"

4. Conductor continues:
   [Uses Read tool on auth.py]
   [Uses Read tool on session.py]
   [Uses Write tool to create report]

5. PreToolUse Hook (before Write):
   - Detects it's trying to write a report
   - Checks events.jsonl - all workers done!
   - Rewrites input to include actual findings from:
     * .claude/runs/R42/workers/W1/out/vulnerabilities.json
     * .claude/runs/R42/workers/W2/out/vulnerabilities.json
     * .claude/runs/R42/workers/W3/out/vulnerabilities.json

6. Stop Hook:
   - All workers done, allows termination
```

### Workflow 2: Test Suite Execution
```
User: "Run unit tests, integration tests, and e2e tests, then summarize results"

1. UserPromptSubmit Hook:
   - Pattern: "run [test1], [test2], and [test3]"
   - Creates plan with parallel test execution
   - W1: pytest unit/, W2: pytest integration/, W3: playwright e2e/
   - Returns: "Running 3 test suites in parallel (Run R43)"

2. Conductor responds:
   "I'll run all test suites and summarize the results..."
   [Uses Bash tool: "pytest unit/"]

3. PreToolUse Hook (before Bash):
   - Detects pytest command
   - Checks if W1 already running this
   - BLOCKS the tool call, returns mock success output from W1's results

4. PostToolUse Hook:
   - Injects: "R43: W1 ✓ done (85 passed); W2 60% (30/50 tests); W3 40%"

5. Similar interception for integration and e2e test commands

6. When Conductor tries to summarize:
   - PreToolUse rewrites to use actual test outputs from workers
```

### Workflow 3: Data Pipeline Processing
```
User: "Process dataset.csv: clean the data, generate statistics, and create visualizations"

1. UserPromptSubmit Hook:
   - Pattern: "process ... : [task1], [task2], and [task3]"
   - Creates dependency chain: Clean → Stats → Viz
   - W1: Clean (no deps), W2: Stats (depends on W1), W3: Viz (depends on W2)
   - Returns: "Processing pipeline with 3 stages (Run R44)"

2. Conductor proceeds:
   [Uses Read tool on dataset.csv]
   [Uses Write tool to clean data]

3. PreToolUse Hook (before Write for cleaning):
   - Checks W1 status
   - If done: rewrites to use W1's cleaned output
   - If not: allows normal execution while W1 continues

4. Workers coordinate via events:
   - W1 writes: {"t":"done","task":"clean","path":"workers/W1/out/cleaned.csv"}
   - W2 polls events, sees W1 done, starts stats generation
   - W2 writes: {"t":"done","task":"stats","path":"workers/W2/out/stats.json"}
   - W3 polls events, sees W2 done, creates visualizations

5. PostToolUse keeps injecting pipeline status
```

### Workflow 4: API Endpoint Testing
```
User: "Test these API endpoints: GET /users, POST /auth/login, DELETE /sessions"

1. UserPromptSubmit Hook:
   - Pattern: "test ... endpoints: [endpoint1], [endpoint2], [endpoint3]"
   - Each worker gets different endpoint to test
   - W1: Load test GET /users
   - W2: Security test POST /auth/login
   - W3: Functionality test DELETE /sessions
   - Returns: "Testing 3 endpoints in parallel (Run R45)"

2. Conductor thinks it's testing sequentially:
   [Uses Bash: "curl http://api/users"]

3. PreToolUse Hook:
   - Intercepts curl commands
   - Returns results from workers' actual load testing

4. Workers write comprehensive test results:
   - Performance metrics
   - Error rates
   - Response time distributions
   - Security findings

5. Merge happens when Conductor creates test report
```

### Workflow 5: Multi-Model Comparison
```
User: "Compare responses from GPT-4, Claude, and Gemini for this prompt: 'Explain quantum computing'"

1. UserPromptSubmit Hook:
   - Pattern: "compare ... from [model1], [model2], and [model3]"
   - W1: Query GPT-4 API
   - W2: Query Claude API
   - W3: Query Gemini API
   - Returns: "Querying 3 models in parallel (Run R46)"

2. Conductor proceeds normally:
   "I'll compare responses from these three models..."
   [Might try to use curl or fetch APIs]

3. PreToolUse Hook:
   - Intercepts API calls
   - Checks if workers have results
   - Rewrites tool inputs to use cached responses

4. Workers handle:
   - API authentication
   - Rate limiting/retries
   - Response parsing
   - Error handling

5. All responses aggregated for comparison
```

## Critical Implementation Details

### Worker Spawn Mechanism (from UserPromptSubmit)
```python
def spawn_worker(worker_id, task_id, run_dir):
    cmd = [
        sys.executable,  # python
        "worker/worker.py",
        "--run-dir", run_dir,
        "--worker-id", worker_id,
        "--task-id", task_id
    ]

    # CRITICAL: Detached spawn so hook can return immediately
    if platform.system() == "Windows":
        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=open(f"{run_dir}/workers/{worker_id}/stdout.log", "w"),
            stderr=open(f"{run_dir}/workers/{worker_id}/stderr.log", "w")
        )
    else:
        subprocess.Popen(
            cmd,
            start_new_session=True,  # Detach from parent
            stdout=open(f"{run_dir}/workers/{worker_id}/stdout.log", "w"),
            stderr=open(f"{run_dir}/workers/{worker_id}/stderr.log", "w")
        )
```

### Worker Coordination Pattern
```python
# Worker polls for dependencies
while not dependencies_satisfied:
    events = read_events()
    done_tasks = [e.task for e in events if e.t == "done"]
    if all(dep in done_tasks for dep in my_dependencies):
        dependencies_satisfied = True
    else:
        append_event(Event(t="progress", msg="Waiting for dependencies"))
        time.sleep(2)

# Worker proceeds with task
append_event(Event(t="start", task=my_task))
result = execute_task()
write_artifact(result)
append_event(Event(t="done", task=my_task, path=artifact_path))
```

### Hook Context Injection
```python
# PostToolUse injects status
def post_tool_use():
    status = compute_status()  # From events.jsonl
    status_line = status.to_compact_string()

    return {
        "hookSpecificOutput": {
            "additionalContext": status_line
        }
    }
```

## The Magic: Conductor's Perspective vs Reality

### What Conductor Thinks:
1. User asks to analyze 3 files
2. I'll read each file sequentially
3. I'll analyze each one
4. I'll write a combined report
5. Done!

### What Actually Happens:
1. UserPromptSubmit spawns 3 workers analyzing in parallel
2. Conductor reads files (but workers already processing)
3. PostToolUse injects "W1 ✓ done, W2 ✓ done, W3 ✓ done"
4. PreToolUse rewrites report generation to use worker artifacts
5. Stop hook ensures all workers complete before termination

The Conductor never knows it orchestrated parallel work - it just sees helpful status updates in its context and mysteriously has access to pre-computed results when it needs them!

## Key Constraints

1. **Hooks must return fast** (<1 second ideal)
   - Spawn and return, don't wait
   - Read status quickly from events.jsonl

2. **Workers are fire-and-forget**
   - No direct communication back to hooks
   - Only communicate via filesystem

3. **Conductor continues regardless**
   - Hooks can influence but not stop the main flow
   - Must handle cases where Conductor moves faster than workers

4. **Filesystem is the message bus**
   - Append-only events.jsonl for coordination
   - Separate directories prevent conflicts
   - Plan.json is immutable contract

This architecture is brilliant because it adds parallelism to a fundamentally sequential system without the main system even knowing!