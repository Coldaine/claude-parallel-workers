# Claude Parallel Hooks

A parallel execution framework for Claude Code that enables true concurrency through the native hooks system. Spawn and coordinate multiple worker processes while maintaining a single, responsive Claude session.

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
uv sync
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

Run tests:
```bash
pytest tests/
```

Run integration tests:
```bash
python tests/integration_test.py
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