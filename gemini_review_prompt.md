# Claude Code Parallel Workers Architecture Review

I'm implementing a parallel execution system for Claude Code using its native hooks. Please review this architecture and help identify potential issues, improvements, and validate the approach.

## Core Architecture

### The System
- **Main Claude Session (Conductor)**: Runs normally, unaware it's orchestrating parallel work
- **Hooks**: Shell scripts executed by Claude Code at lifecycle events (UserPromptSubmit, PreToolUse, PostToolUse, Stop, etc.)
- **Workers**: Detached Python processes spawned from hooks
- **Shared Store**: Filesystem at `.claude/runs/<RUN_ID>/` with events.jsonl (append-only log)

### Key Insight
The Conductor doesn't know it's orchestrating. Hooks transparently:
1. Spawn workers at prompt submission
2. Inject status updates after tool use
3. Rewrite tool inputs for merge operations
4. Block termination until workers complete

### Communication Patterns

#### Filesystem (Async)
- Workers append to `events.jsonl`
- Workers write artifacts to `workers/W<N>/out/`
- Plan.json defines task dependencies

#### Hook Invocation (Sync)
- **Workers CAN invoke Claude Code hooks themselves**
- Exit code 0: Inject information (non-blocking)
- Exit code 2: BLOCK the Conductor (force wait/retry)
- Workers can control Conductor flow through hook invocations

### Example Flow
```
User: "Analyze files A, B, C"
1. UserPromptSubmit hook → spawns W1(A), W2(B), W3(C)
2. Conductor: "I'll analyze..." → tries to read A
3. W1 invokes PreToolUse(exit=2) → "Already processing A"
4. W1 completes → invokes PostToolUse(exit=0) → "W1 done: found 5 issues"
5. Conductor tries to merge → PreToolUse rewrites inputs to use W1,W2,W3 outputs
```

## Critical Questions

1. **Race Conditions**: Multiple workers appending to events.jsonl simultaneously. Is append-only sufficient or do we need explicit locking?

2. **Hook Invocation Overhead**: If workers frequently invoke hooks, will this create performance bottlenecks?

3. **Deadlock Risk**: Can workers invoking hooks with exit=2 create deadlock scenarios?

4. **Process Management**: How do we handle orphaned workers if the Conductor crashes?

5. **Security**: Workers invoking hooks run with user permissions. What are the security implications?

## Specific Design Decisions to Validate

1. **Worker Spawn Method**: Using `subprocess.Popen(start_new_session=True)` for detachment. Is this reliable across platforms?

2. **Coordination via Filesystem**: Using events.jsonl as message bus. Better alternatives?

3. **Bidirectional Communication**: Workers→Hooks via invocation. Is this pattern sound or overcomplicated?

4. **Exit Code Strategy**: Using exit=2 for blocking. Are there edge cases where this breaks?

5. **State Management**: Each worker tracks dependencies by polling events.jsonl. More efficient approach?

## Implementation Concerns

1. Should workers be able to invoke ANY hook or just specific ones?
2. How do we prevent infinite loops (hook→worker→hook→worker)?
3. What's the maximum practical number of workers?
4. How do we handle partial failures gracefully?
5. Should we implement worker pooling or spawn per task?

Please provide:
- Architecture validation
- Potential failure modes
- Suggested improvements
- Alternative approaches
- Critical implementation warnings