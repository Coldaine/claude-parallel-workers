# Claude Parallel Hooks

A parallel execution framework for Claude Code that enables true concurrency through the native hooks system. Spawn and coordinate multiple worker processes while maintaining a single, responsive Claude session.

## 📊 Implementation Status

**✅ IMPLEMENTED (Working Code):**
- SQLite event store with ACID guarantees (`shared/event_store_v2.py`)
- Data models and event types (`shared/models.py`)
- Orchestrator with asyncio-based parallel execution (`orchestrator/orchestrator.py`)
- Worker process implementation (`worker/worker.py`)
- All 4 hooks: UserPromptSubmit, PostToolUse, PreToolUse, Stop
- YAML task definitions with dependency resolution
- Integration tests and examples

**🚧 PARTIAL:**
- Hook integration (hooks are implemented but need testing with Claude Code)
- Pattern detection (basic implementation, can be enhanced)

**Architecture Pattern:** Combines ZO's asyncio.gather parallelism with SQLite state management for robustness.

## 🎯 Purpose

Enable Claude Code to:
- **Detect parallelizable tasks** automatically from user prompts
- **Spawn external workers** for true concurrent execution
- **Synchronize state** using hooks and a lightweight event log
- **Maintain responsiveness** without blocking on long-running operations

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

## 🚀 Quick Start

### Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/claude-parallel-hooks
cd claude-parallel-hooks
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install hooks in Claude Code settings:
```bash
./settings/install.sh
```

Or manually add to `~/.claude/settings.json`:
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

## 📖 How It Works

### 1. Task Detection (UserPromptSubmit)
When you submit a prompt like "Process files A, B, and C", the hook:
- Detects the parallel pattern
- Creates an execution plan
- Spawns worker processes
- Injects status into Claude's context

### 2. Status Updates (PostToolUse)
After each tool use, the hook:
- Reads worker progress from `events.jsonl`
- Generates a status line: `"R42 — W1 80% processing; W2 ✓ done; W3 waiting"`
- Injects it as additional context

### 3. Merge Coordination (PreToolUse)
When Claude attempts to merge results, the hook:
- Checks if all dependencies are satisfied
- Rewrites tool inputs with actual artifact paths
- Or blocks execution if workers aren't ready

### 4. Completion Gating (Stop)
Before Claude ends the session, the hook:
- Verifies all workers have completed
- Blocks termination if work is pending
- Ensures no orphaned processes

## 📁 Project Structure

```
claude-parallel-hooks/
├── hooks/                  # Hook implementations
│   ├── user_prompt_submit.py
│   ├── pre_tool_use.py
│   ├── post_tool_use.py
│   └── stop.py
├── orchestrator/          # Task planning and worker management
│   ├── orchestrator.py
│   ├── task_parser.py
│   └── worker_manager.py
├── worker/               # Worker process implementation
│   ├── worker.py
│   └── task_executor.py
├── shared/              # Shared components and models
│   ├── event_store.py
│   └── models.py
└── examples/           # Usage examples and patterns
```

## ⚙️ How Parallel Coordination Works

The implementation uses a **two-level parallelism pattern**:

### Level 1: Batch Sequencing (Sequential)
Tasks are organized into batches based on dependencies. Batch N+1 waits for Batch N to complete.

### Level 2: Within-Batch Parallelism (Concurrent)
Tasks within a batch have no inter-dependencies and execute simultaneously using `asyncio.gather()`.

**Example:**
```yaml
tasks:
  - name: "A"           # Batch 1 (parallel)
  - name: "B"           # Batch 1 (parallel)
  - name: "C"           # Batch 1 (parallel)
    dependencies: []

  - name: "D"           # Batch 2 (parallel, waits for Batch 1)
    dependencies: ["A"]
  - name: "E"           # Batch 2 (parallel, waits for Batch 1)
    dependencies: ["B"]

  - name: "F"           # Batch 3 (waits for Batch 2)
    dependencies: ["D", "E"]
```

**Coordination Mechanisms:**
1. **SQLite Event Store** - ACID-compliant state tracking
2. **Worker State Machine** - idle → busy → done/error
3. **Heartbeats** - Detect dead workers (stale heartbeat = deadlock)
4. **Time-limited Blocks** - Hooks can block operations with automatic expiry
5. **Artifact Tracking** - Workers report output files for downstream tasks

## 🔧 Configuration

### Supported Patterns

The system automatically detects parallelizable patterns like:
- "Process files A, B, and C"
- "Run tests on modules X, Y, and Z"
- "Analyze documents 1 through 10"
- "Generate reports for Q1, Q2, Q3, Q4"

### Event Types

Workers emit events to coordinate execution:
- `start` - Task execution begins
- `progress` - Progress updates (with percentage)
- `artifact` - Output file created
- `error` - Failure occurred
- `done` - Task completed successfully

## 📊 Example Usage

```python
# User prompt: "Analyze these three datasets: sales.csv, customers.csv, inventory.csv"

# System automatically:
# 1. Detects three parallel tasks
# 2. Creates execution plan
# 3. Spawns three workers
# 4. Each worker processes one file
# 5. Injects status updates
# 6. Merges results when complete
```

## 🧪 Testing

Run the integration test:
```bash
python examples/test_orchestrator.py
```

This will execute the example tasks in `examples/tasks.yaml`, demonstrating:
- Dependency resolution (topological sort)
- Parallel execution within batches
- Sequential execution across batches
- SQLite event tracking
- Worker state management

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