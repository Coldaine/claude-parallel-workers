# Claude Parallel Hooks

An experimental framework exploring parallel execution patterns in Claude Code using the native hooks system. Demonstrates how hooks can coordinate multiple worker processes while maintaining a responsive Claude session.

**Status**: Foundation-stage implementation. Core data models and event storage are functional; hook implementations and orchestrator are not yet implemented.

## 🎯 Purpose

This project explores how Claude Code could:
- Detect parallelizable task patterns from user prompts
- Spawn and coordinate external worker processes
- Synchronize state using hooks and event logs
- Coordinate results back into the Claude session

## 🏗️ Architecture

```
User → Claude Code Session
         ↓
    [Hooks Layer]
         ├── UserPromptSubmit → Detect & Plan → Spawn Orchestrator
         ├── PostToolUse → Read Status → Inject Context
         ├── PreToolUse → Check Dependencies → Rewrite Inputs
         └── Stop → Verify Completion → Gate Termination
              ↓
    [Orchestrator]
         ├── Parse Tasks
         ├── Generate Plan
         └── Spawn Workers → [W1] [W2] [W3] ... [Wn]
                                ↓
                          [Shared Store]
                            ├── plan.json
                            ├── events.jsonl
                            └── artifacts/
```

## 🚀 Installation Status

**Note**: This project is in foundation stage. The architecture and data models are complete and functional, but hook implementations are not yet available. The following instructions document the planned configuration:

1. Clone this repository:
```bash
git clone https://github.com/Coldaine/claude-parallel-workers
cd claude-parallel-workers
```

2. Install dependencies:
```bash
uv sync
```

3. When hook implementations are available, they would be configured in `~/.claude/settings.json`:
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

## 📖 Planned Architecture

The framework is designed to work through four hook points in the Claude Code lifecycle:

### 1. Task Detection (UserPromptSubmit)
When user submits a prompt like "Process files A, B, and C", this hook would:
- Detect the parallel task pattern
- Create an execution plan
- Spawn worker processes
- Provide initial context about the operation

### 2. Status Updates (PostToolUse)
After each tool execution, this hook would:
- Read worker progress from the event store
- Generate a status line: `"R42 — W1 80% processing; W2 ✓ done; W3 waiting"`
- Inject status as additional context

### 3. Merge Coordination (PreToolUse)
When Claude attempts merge operations, this hook would:
- Check if all dependencies are satisfied
- Rewrite tool inputs with actual artifact paths
- Block execution if workers are still running

### 4. Completion Gating (Stop)
Before session termination, this hook would:
- Verify all workers have completed
- Block termination if work is pending
- Ensure no orphaned processes

## 📁 Project Structure

**Implemented**:
```
shared/
├── models.py           # Data models (Event, Task, Plan, Worker, Status)
├── event_store.py      # JSONL-based event logging
├── event_store_v2.py   # SQLite-based event storage
├── utils.py            # Hook utilities and helpers
└── __init__.py
```

**Planned (not yet implemented)**:
```
hooks/                  # Hook implementations
├── user_prompt_submit.py
├── pre_tool_use.py
├── post_tool_use.py
└── stop.py
orchestrator/          # Task planning and worker management
├── orchestrator.py
├── task_parser.py
└── worker_manager.py
worker/               # Worker process implementation
├── worker.py
└── task_executor.py
examples/           # Usage examples and patterns
tests/              # Test suite
```

## 🔧 Data Model

### Event Types

The system defines the following event types for worker coordination:
- `start` - Task execution begins
- `progress` - Progress updates (with percentage)
- `artifact` - Output file created
- `error` - Failure occurred
- `done` - Task completed successfully
- `merge_ready` - Results ready for merging

### State Models

The framework provides models for:
- **Event**: Individual state change in the system
- **Task**: Work unit with dependencies and inputs/outputs
- **Worker**: Process with ID, task assignment, and state tracking
- **Plan**: Execution graph with all tasks and worker assignments
- **Status**: Current snapshot of all workers and blocking state

## 📊 Data Model Example

```python
from shared.models import Event, EventType, Task, Plan, Worker, WorkerState
from shared.event_store import EventStore

# Create a task
task = Task(
    id="task_1",
    description="Analyze sales.csv",
    deps=[],  # No dependencies
    inputs={"file": "sales.csv"},
    outputs={"report": "analysis_report.json"}
)

# Create a worker assignment
worker = Worker(
    id="W1",
    task="task_1",
    cmd=["python", "worker.py", "--task", "task_1"],
    state=WorkerState.INIT
)

# Log an event
store = EventStore(".claude/runs/R42/")
event = Event(
    t=EventType.DONE,
    ts="2025-11-13T12:00:00Z",
    w="W1",
    task="task_1",
    path="results/analysis_report.json"
)
store.append_event(event)
```

**When hooks are implemented**, the system would handle user prompts like:
- "Analyze these three datasets: sales.csv, customers.csv, inventory.csv"
- "Run tests on modules X, Y, and Z"
- "Process files A, B, and C in parallel"

## 🧪 Testing

Test suite is planned but not yet implemented. To verify the current data models work:
```bash
python3 -c "from shared.models import Event, EventType; print('Models import successful')"
python3 -c "from shared.event_store import EventStore; print('EventStore import successful')"
python3 -c "from shared.event_store_v2 import EventStoreV2; print('EventStoreV2 import successful')"
```

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🔗 References

- [Claude Code Hooks Documentation](https://code.claude.com/docs/en/hooks)
- [Claude Code Interactive Mode](https://code.claude.com/docs/en/interactive-mode)
- [Original Architecture Visualization](https://github.com/Coldaine/Claudeparallel)

## ⚠️ Security Note

Hooks execute with your user permissions. Always:
- Validate inputs carefully
- Sanitize file paths
- Review hook code before installation
- Use appropriate timeouts
- Monitor resource usage

## 🎨 Architecture Diagrams

See the original [Figma visualization](https://www.figma.com/design/bb2nmcxHAgSiPeyLysiEYH/Diagram-Ready-Spec-for-Claude) for detailed architecture diagrams including:
- Component architecture
- Sequence flows
- State machines
- Hook activity charts
- Data models
- Execution timelines