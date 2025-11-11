# SwarmSDK Investigation Findings

## Overview
**Repository**: https://github.com/parruda/swarm
**Investigation Date**: 2025-11-10
**Priority**: HIGH ⭐⭐⭐⭐

## Critical Architectural Decision: V1 → V2 Migration

### Why They Abandoned Multi-Process Architecture

| Aspect | V1 (Multi-Process) | V2 (Single-Process) | Reason for Change |
|--------|-------------------|---------------------|-------------------|
| **Architecture** | Multiple Claude Code processes | Single Ruby process with RubyLLM | **IPC overhead too expensive** |
| **Communication** | MCP inter-process protocol | Direct method calls | **10x+ performance improvement** |
| **Dependencies** | Claude CLI + Node.js | RubyLLM only (Ruby-only) | **Simpler deployment** |
| **Concurrency Model** | OS-level processes | In-process agents | **Faster delegation** |
| **Memory Sharing** | Difficult (separate processes) | Easy (shared memory) | **Better context sharing** |

### Key Quote from README:

> "SwarmSDK is a complete redesign of Claude Swarm that provides a better developer experience and is geared towards general-purpose agentic systems."

> "⚡ Single Process Architecture: All agents run in one Ruby process using RubyLLM - no more managing multiple processes"

> "🎯 More Efficient: Direct method calls instead of MCP inter-process communication"

**Implication for Our Architecture:**
- ⚠️ **Warning**: They found multi-process approach too slow for their use case
- ✅ **However**: Their use case (delegation chains) differs from ours (true parallelism)
- 🤔 **Question**: Can we learn from their hooks system while keeping multi-process?

## Architecture Comparison: SwarmSDK vs ClaudeParallel

| | SwarmSDK | ClaudeParallel |
|---|----------|----------------|
| **Goal** | Role specialization & task delegation | True parallel execution |
| **Pattern** | Lead→Frontend→Backend (sequential delegation) | 4 workers executing simultaneously |
| **Concurrency** | Pseudo-concurrency (async delegation) | Real concurrency (OS processes) |
| **Communication** | Direct method calls (in-process) | SQLite + hooks (inter-process) |
| **Isolation** | None (shared memory) | Strong (separate processes) |
| **Performance** | Fast delegation (no IPC) | Slower coordination (IPC overhead) |
| **Use Case** | Specialized agent teams | Parallel task execution |

**Key Insight**: We're solving **different problems**!
- SwarmSDK: "How can agents with different roles collaborate?"
- ClaudeParallel: "How can multiple workers execute tasks concurrently?"

## Hooks System (13 Events, 6 Actions)

### The 13 Hook Events

**Swarm Lifecycle:**
1. `swarm_start` - When Swarm.execute is called (before first message)
2. `swarm_stop` - When execution completes
3. `first_message` - When first user message is sent

**Agent/LLM:**
4. `user_prompt` - Before sending message to LLM
5. `agent_step` - After agent makes intermediate response with tool calls
6. `agent_stop` - After agent completes (no more tool calls)

**Tool Usage:**
7. `pre_tool_use` - Before tool execution (can block)
8. `post_tool_use` - After tool execution

**Delegation:**
9. `pre_delegation` - Before delegating to another agent
10. `post_delegation` - After delegation completes

**Context Management:**
11. `context_warning` - When context usage crosses threshold (80%, 90%)

**Special:**
12-13. (Additional events not documented in the excerpt)

### The 6 Hook Actions

SwarmSDK hooks return `Result` objects that control execution flow:

1. **Continue** (default) - Return nil, execution proceeds
```ruby
hook :pre_tool_use do |ctx|
  puts "Tool: #{ctx.tool_call.name}"
  # Implicit continue
end
```

2. **Halt** - Stop execution with error
```ruby
hook :pre_tool_use do |ctx|
  if ctx.tool_call.parameters[:command].include?("rm -rf")
    SwarmSDK::Hooks::Result.halt("Dangerous command blocked")
  end
end
```

3. **Replace** - Modify tool result
```ruby
hook :post_tool_use do |ctx|
  if ctx.tool_result.content.length > 10000
    SwarmSDK::Hooks::Result.replace("Content truncated")
  end
end
```

4. **Reprompt** - Continue with new prompt (swarm_stop only)
```ruby
hook :swarm_stop do |ctx|
  if ctx.metadata[:result].content.include?("TODO")
    SwarmSDK::Hooks::Result.reprompt("Complete all TODOs")
  end
end
```

5. **Finish Agent** - End current agent's turn
```ruby
hook :agent_step do |ctx|
  if ctx.metadata[:tool_calls].size > 10
    SwarmSDK::Hooks::Result.finish_agent("Too many tool calls")
  end
end
```

6. **Finish Swarm** - End entire execution immediately
```ruby
hook :pre_tool_use do |ctx|
  if emergency_shutdown?
    SwarmSDK::Hooks::Result.finish_swarm("Emergency stop")
  end
end
```

### Hook Context Object

Each hook receives a `ctx` object with metadata:

```ruby
ctx.agent_name          # Current agent name
ctx.tool_call           # ToolCall object (pre_tool_use)
ctx.tool_call.name      # Tool name (e.g., "Read")
ctx.tool_call.parameters # Tool parameters (e.g., {file_path: "..."}  )
ctx.tool_result         # ToolResult object (post_tool_use)
ctx.tool_result.content # Tool output
ctx.metadata[:prompt]   # User prompt (swarm_start, user_prompt)
ctx.metadata[:result]   # Final result (swarm_stop)
ctx.metadata[:total_cost] # Execution cost (swarm_stop)
```

### Hook Scopes

**Swarm-level hooks** (apply to all agents):
```ruby
SwarmSDK.build do
  hook :swarm_start do |ctx|
    puts "Starting: #{ctx.metadata[:prompt]}"
  end

  agent :dev do
    # ...
  end
end
```

**All-agents hooks**:
```ruby
SwarmSDK.build do
  all_agents do
    hook :pre_tool_use, matcher: "Write|Edit" do |ctx|
      puts "[#{ctx.agent_name}] Modifying: #{ctx.tool_call.parameters[:file_path]}"
    end
  end

  agent :dev do
    # ...
  end
end
```

**Agent-specific hooks**:
```ruby
agent :dev do
  description "Developer"

  hook :user_prompt do |ctx|
    puts "Dev agent received prompt"
  end

  hook :pre_tool_use, matcher: "Bash" do |ctx|
    puts "About to run: #{ctx.tool_call.parameters[:command]}"
  end
end
```

## SwarmMemory (Semantic Memory with FAISS)

### Architecture

**Storage Backend:**
- Hierarchical knowledge organization (concept, fact, skill, experience)
- FAISS-based vector similarity search
- Local ONNX embeddings (no external API calls)
- Persistent storage across sessions

**9 Memory Tools:**
1. `MemoryWrite` - Store new knowledge
2. `MemoryRead` - Retrieve specific memories by key
3. `MemorySearch` - Semantic search across all knowledge
4. `MemoryUpdate` - Update existing memories
5. `MemoryDelete` - Remove memories
6. `MemoryList` - List all memories in namespace
7. `LoadSkill` - Dynamically load specialized skills (tool swapping!)
8. `UnloadSkill` - Remove loaded skills
9. `ListSkills` - Show available skills

### Configuration Example

```yaml
version: 2
agents:
  researcher:
    model: claude-3-5-sonnet-20241022
    role: "Research assistant with long-term memory"
    tools: [Read, Write]
    plugins:
      - swarm_memory:
          storage_dir: ./memories
```

**Once enabled, agent automatically gets all 9 memory tools**

### Key Innovation: LoadSkill

**Dynamic Tool Swapping:**
```ruby
# Agent doesn't have Bash tool initially
agent :dev do
  tools :Read, :Write  # No Bash
  plugins: [swarm_memory]
end

# Agent can dynamically load "bash_expert" skill via semantic search
# This adds Bash tool + expert knowledge
agent.use_tool("LoadSkill", {skill_name: "bash_expert"})
```

**Implications:**
- Tools are not fixed at initialization
- Agents can acquire new capabilities at runtime
- Skills include both tools AND contextual knowledge
- Semantic search finds relevant skills automatically

### Storage Structure

```
./memories/
├── concepts/     # High-level concepts and principles
├── facts/        # Specific facts and data
├── skills/       # Executable skills (tools + knowledge)
└── experiences/  # Past execution results
```

Each memory entry includes:
- Content (text)
- Vector embedding (for semantic search)
- Metadata (tags, namespace, timestamp)
- TTL (optional expiration)

## Git Worktree Support (V1 Feature, Deprecated in V2)

**V1 Pattern:**
```bash
claude-swarm --worktree feature-branch
```

**Per-Instance Configuration:**
```yaml
instances:
  main:
    worktree: true         # Use shared worktree
  testing:
    worktree: false        # Don't use worktree
  feature:
    worktree: "feature-x"  # Specific worktree name
```

**Worktree Management:**
- External directory: `~/.claude-swarm/worktrees/[session_id]/[repo-hash]/[worktree_name]`
- Automatic cleanup on exit
- Reuse existing worktrees with same name
- Session metadata tracks worktree info

**Why This Matters:**
- Filesystem isolation without multiple repos
- Each worker can have isolated workspace
- No conflicts with bundler/package managers

**Implication for Our Architecture:**
- ✅ Validates git worktree approach for isolation
- 📋 TODO: Implement similar worktree management
- 📋 TODO: Add cleanup on session end

## Configuration Formats: YAML vs Ruby DSL

### YAML (Declarative)

```yaml
version: 2
agents:
  lead:
    model: claude-3-5-sonnet-20241022
    role: "Lead developer"
    tools: [Read, Write, Edit]
    delegates_to: [frontend, backend]
    hooks:
      on_pre_tool:
        - run: "git diff"
          append_output_to_context: true
```

**Pros:**
- Easy to read
- Simple syntax
- Good for shell-based hooks
- Config file can be generated

**Cons:**
- Limited dynamic behavior
- No IDE autocomplete
- Hard to test

### Ruby DSL (Programmatic)

```ruby
SwarmSDK.build do
  agent :lead do
    model "claude-3-5-sonnet-20241022"
    role "Lead developer"
    tools :Read, :Write, :Edit
    delegates_to :frontend, :backend

    hook :pre_tool_use do |ctx|
      # Full Ruby power!
      if ctx.tool_call.name == "Write"
        validate_write(ctx.tool_call.parameters)
      end
    end
  end
end
```

**Pros:**
- Full Ruby power
- IDE autocomplete
- Unit testable
- Dynamic configuration

**Cons:**
- More verbose
- Requires Ruby knowledge

**Recommendation for Our Architecture:**
- ✅ Support both formats (YAML for simplicity, Python DSL for power)
- ✅ YAML for hook commands (like claude-flow)
- ✅ Python DSL for complex logic

## Node Workflows (Pipeline Pattern)

### Multi-Stage Processing

```yaml
version: 2
nodes:
  analyzer:
    agent: code_analyst
    prompt: "Analyze code and identify issues"

  fixer:
    agent: code_fixer
    prompt: "Fix issues: {{ analyzer.output }}"
    depends_on: [analyzer]

  reviewer:
    agent: code_reviewer
    prompt: "Review fixes: {{ fixer.output }}"
    depends_on: [fixer]
```

**Features:**
- Dependency graph (DAG)
- Variable interpolation (`{{ node.output }}`)
- Parallel execution (nodes without dependencies)
- Sequential when needed (with `depends_on`)

**Implications for Our Architecture:**
- 📋 TODO: Consider adding task dependency graph
- 📋 TODO: Support output passing between tasks
- ✅ Similar to our Task dependencies concept

## Key Learnings for ClaudeParallel

### What to Adopt

1. **Hook Actions System** ⭐⭐⭐⭐⭐
   - Return values that control execution flow
   - Replace (modify tool results)
   - Halt (block with error)
   - Finish (early termination)

2. **Hook Context Object** ⭐⭐⭐⭐⭐
   - Structured metadata access
   - Tool call parameters
   - Tool results
   - Agent information

3. **Hook Scopes** ⭐⭐⭐⭐
   - Swarm-level (all workers)
   - Worker-specific
   - Matcher-based filtering

4. **Additional Hook Events** ⭐⭐⭐⭐
   - agent_step (after each LLM response)
   - agent_stop (when agent completes)
   - context_warning (threshold alerts)

5. **Git Worktree Management** ⭐⭐⭐
   - Automatic creation/cleanup
   - Session tracking
   - Per-worker configuration

### What to Avoid

1. ❌ **Single-Process Architecture** - We need true parallelism
2. ❌ **Delegation Pattern** - We need concurrent execution, not sequential delegation
3. ❌ **In-Memory State** - We need persistent coordination (SQLite)

### What's Complementary (Different Use Cases)

- **SwarmMemory** - Could be useful for sharing context between workers
- **LoadSkill** - Dynamic tool loading is interesting but not critical
- **Node Workflows** - Similar to our task dependencies

## Recommendations

### Immediate Adoption (Must Have)

1. ✅ **Hook Action System**
   ```python
   # hooks/pre_tool_use.py
   class HookResult:
       @staticmethod
       def halt(reason: str):
           return {"action": "halt", "reason": reason}

       @staticmethod
       def replace(new_content: str):
           return {"action": "replace", "content": new_content}
   ```

2. ✅ **Hook Context Object**
   ```python
   @dataclass
   class HookContext:
       tool_call: ToolCall
       tool_result: Optional[ToolResult]
       worker_id: str
       run_id: str
       metadata: Dict[str, Any]
   ```

3. ✅ **Additional Hook Events**
   - Add worker_step (after each Claude response)
   - Add worker_stop (when worker completes)
   - Add context_warning (token usage alerts)

4. ✅ **Matcher-Based Hooks**
   ```json
   {
     "hooks": {
       "PreToolUse": [{
         "matcher": "Write|Edit",
         "command": "python -m hooks.validate_file"
       }]
     }
   }
   ```

### Consider Adding (Nice to Have)

1. 📋 **Worktree Management** - Per-worker isolated filesystems
2. 📋 **Memory Store** - Shared knowledge between workers
3. 📋 **Node Workflows** - Task dependency graphs
4. 📋 **Both YAML and Python DSL** - Configuration flexibility

### Architecture Validation

- ✅ **SQLite is correct choice** - SwarmSDK moved away from multi-process, but we need it
- ✅ **Hooks are critical** - SwarmSDK has sophisticated hook system
- ✅ **Isolation matters** - Git worktrees show importance of filesystem isolation
- ⚠️ **IPC overhead is real** - SwarmSDK found it expensive, we must optimize

## Next Steps

1. Extract hook implementation patterns
2. Design our Hook Action system
3. Create Hook Context dataclass
4. Add matcher-based hook filtering
5. Implement worktree management (optional)
6. Document SwarmMemory patterns for future reference

## Files to Examine Next (Lower Priority)

- `examples/v2/hooks/` - More hook examples
- `lib/swarm_sdk/hooks/` - Hook implementation
- `lib/swarm_memory/` - Memory system implementation
- Node workflow examples
