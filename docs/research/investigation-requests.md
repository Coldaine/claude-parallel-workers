# Investigation Requests - Parallel Frameworks

## Purpose

This document outlines specific investigation tasks for each framework analyzed. Use this as a checklist when studying these projects to extract maximum value for our implementation.

---

## 1. ruvnet/claude-flow

**Repository**: https://github.com/ruvnet/claude-flow

### Priority: CRITICAL ⭐⭐⭐⭐⭐

### Investigation Tasks

#### A. Hooks System Architecture

**What to Extract**:
- [ ] Complete `.claude/settings.json` structure with all hook configurations
- [ ] Hook script examples for each event type:
  - [ ] `pre-task` initialization scripts
  - [ ] `pre-edit` backup creation
  - [ ] `pre-command` security validation
  - [ ] `post-edit` code formatting/validation
  - [ ] `post-task` metrics storage
  - [ ] `session-start` context restoration
  - [ ] `session-end` state persistence
- [ ] Hook chaining patterns (how multiple hooks compose)
- [ ] Parallel hook execution implementation (up to 4 concurrent)
- [ ] Path-based filtering logic (trigger hooks only for relevant files)

**Questions to Answer**:
1. How do they handle hook failures? (retry, skip, abort)
2. How do hooks communicate with each other? (shared state)
3. How are hook timeouts configured and enforced?
4. What's the performance overhead of hook invocations?

#### B. SQLite Database Schema

**What to Extract**:
- [ ] Complete schema for `memory.db`
- [ ] Table definitions:
  - [ ] Events/logs table
  - [ ] Tasks tracking table
  - [ ] Worker status table
  - [ ] Memory/context storage
  - [ ] Performance metrics table
- [ ] Index definitions for query optimization
- [ ] Migration scripts (how schema evolves)

**Questions to Answer**:
1. How do they handle concurrent writes to SQLite?
2. What locking mechanisms are used?
3. How is the database partitioned (per-run, per-session)?
4. What's the cleanup/archival strategy for old data?

#### C. Parallel Execution

**What to Extract**:
- [ ] Implementation of `swarm --strategy parallel` command
- [ ] Worker spawning mechanism
- [ ] Worker pooling implementation
- [ ] Inter-worker coordination code
- [ ] Isolated memory namespaces implementation

**Questions to Answer**:
1. How many workers run concurrently by default?
2. How is work distributed to workers?
3. How do workers report status to orchestrator?
4. How are results merged from parallel workers?

#### D. Performance Monitoring

**What to Extract**:
- [ ] Task duration tracking implementation
- [ ] Performance threshold configuration
- [ ] Alert/notification mechanism
- [ ] Metrics collection and storage
- [ ] Dashboard/reporting code

**Questions to Answer**:
1. What metrics are tracked?
2. How is performance data visualized?
3. Can thresholds be customized per-task?
4. How are anomalies detected?

#### E. Security & Validation

**What to Extract**:
- [ ] `pre-command` security validation scripts
- [ ] File path blacklist/whitelist patterns
- [ ] Input sanitization code
- [ ] Audit logging implementation

**Questions to Answer**:
1. What security checks are performed?
2. How are violations handled?
3. Is there a security policy configuration file?
4. How detailed is the audit log?

### Code Files to Priority Read

```
claude-flow/
├── .claude/
│   └── settings.json           # Hook configurations
├── hooks/
│   ├── pre-task.sh
│   ├── post-task.sh
│   ├── session-start.sh
│   └── session-end.sh
├── swarm/
│   ├── orchestrator.js         # Parallel execution
│   └── worker-pool.js
├── memory/
│   ├── schema.sql              # Database schema
│   └── store.js                # SQLite wrapper
└── monitoring/
    └── performance.js          # Metrics tracking
```

---

## 2. parruda/swarm (SwarmSDK)

**Repository**: https://github.com/parruda/swarm

### Priority: HIGH ⭐⭐⭐⭐

### Investigation Tasks

#### A. Architectural Migration (v1 → v2)

**What to Extract**:
- [ ] Git history showing the migration
- [ ] Rationale document (if exists)
- [ ] Performance benchmarks comparing v1 vs v2
- [ ] Breaking changes documentation

**Questions to Answer**:
1. What specific problems led to the rewrite?
2. What performance improvements were measured?
3. What features were lost/gained?
4. Would they make the same decision again?

#### B. In-Process Worker Architecture

**What to Extract**:
- [ ] Worker implementation (how they run in-process)
- [ ] Concurrency control mechanisms
- [ ] Thread-safety patterns
- [ ] Memory isolation techniques
- [ ] Resource sharing code

**Questions to Answer**:
1. How do they achieve parallelism without OS processes?
2. How is memory partitioned between workers?
3. What happens if a worker crashes?
4. How do workers avoid interfering with each other?

#### C. Hooks System (V2)

**What to Extract**:
- [ ] YAML-based hook configuration examples
- [ ] Hook event definitions (12 events)
- [ ] Inline hook implementation
- [ ] Hook execution engine code

**Examples to Study**:
```yaml
on_post_tool:
  append_git_diff:
    command: "git diff"
    append_to_context: true

on_pre_response:
  ensure_tests_pass:
    command: "pytest"
    stop_on_error: true
```

**Questions to Answer**:
1. Why YAML instead of JSON for hooks?
2. How are inline hooks scoped to agents?
3. Can hooks modify agent behavior dynamically?
4. What's the performance overhead?

#### D. SwarmMemory (Semantic Memory)

**What to Extract**:
- [ ] FAISS integration code
- [ ] Vector embedding generation
- [ ] Semantic search implementation
- [ ] Memory persistence mechanism
- [ ] Cache invalidation logic

**Questions to Answer**:
1. How is semantic similarity computed?
2. What embedding model is used?
3. How large can the memory grow?
4. How is memory queried during execution?

#### E. Performance Optimizations

**What to Extract**:
- [ ] Benchmarking code
- [ ] Performance comparison data
- [ ] Optimization techniques used
- [ ] Bottleneck identification process

**Questions to Answer**:
1. What was the biggest performance gain?
2. Where are the remaining bottlenecks?
3. How does it scale with worker count?
4. What's the memory footprint?

### Code Files to Priority Read

```
swarm/
├── config/
│   └── agent-example.yml       # Hook configurations
├── lib/
│   ├── orchestrator.rb         # In-process coordination
│   ├── worker.rb               # Worker implementation
│   └── memory.rb               # SwarmMemory + FAISS
├── benchmarks/
│   └── v1_vs_v2.rb             # Performance comparisons
└── MIGRATION.md                # v1 → v2 guide
```

---

## 3. namastexlabs/automagik-forge

**Repository**: https://github.com/namastexlabs/automagik-forge

### Priority: MEDIUM ⭐⭐⭐

### Investigation Tasks

#### A. Git Worktree Management

**What to Extract**:
- [ ] Worktree creation scripts
- [ ] Worktree cleanup/removal scripts
- [ ] Directory naming conventions
- [ ] Concurrent worktree handling
- [ ] Disk space management

**Questions to Answer**:
1. How do they prevent worktree conflicts?
2. What's the cleanup strategy for abandoned worktrees?
3. How much disk space does each worktree consume?
4. Can worktrees share build artifacts/node_modules?

#### B. MCP Server Implementation

**What to Extract**:
- [ ] MCP server source code
- [ ] Tool definitions (create_task, update_task, etc.)
- [ ] Server startup/lifecycle management
- [ ] Authentication/authorization code
- [ ] Error handling patterns

**Questions to Answer**:
1. How is the MCP server started/stopped?
2. How do agents authenticate to the server?
3. Can multiple agents connect simultaneously?
4. How is task state synchronized?

#### C. Multi-Model Integration

**What to Extract**:
- [ ] Adapter code for different AI CLIs
- [ ] Claude Code integration
- [ ] Gemini CLI integration
- [ ] Cursor integration
- [ ] Common interface abstraction

**Questions to Answer**:
1. How do they handle CLI differences?
2. Is there a plugin system?
3. How are results normalized across models?
4. What's the overhead of vendor neutrality?

#### D. Kanban Task Management

**What to Extract**:
- [ ] Task board backend implementation
- [ ] Task state machine
- [ ] Task assignment logic
- [ ] Progress tracking
- [ ] UI/frontend (if any)

**Questions to Answer**:
1. How is task priority determined?
2. Can tasks depend on other tasks?
3. How are completed tasks archived?
4. Is there a visualization component?

### Code Files to Priority Read

```
automagik-forge/
├── scripts/
│   ├── worktree-create.sh
│   ├── worktree-cleanup.sh
│   └── parallel-run.sh
├── mcp-server/
│   ├── server.ts
│   ├── tools/
│   │   ├── create-task.ts
│   │   └── update-task.ts
│   └── auth.ts
└── adapters/
    ├── claude-code.ts
    └── gemini-cli.ts
```

---

## 4. Community "Beast Mode" Workflow

**Sources**:
- https://blog.gitbutler.com/automate-your-ai-workflows-with-claude-code-hooks
- https://dev.to/kevinz103/git-worktree-claude-code-my-secret-to-10x-developer-productivity-520b

### Priority: HIGH (for hook techniques) ⭐⭐⭐

### Investigation Tasks

#### A. Hook Script Implementation

**What to Extract**:
- [ ] Complete `PreToolUse` hook script
- [ ] Complete `PostToolUse` hook script
- [ ] Complete `Stop` hook script
- [ ] Session ID generation code
- [ ] Configuration file structure

**Critical Code Sections**:
```bash
# PreToolUse: Detect file modification
if [[ "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "Write" ]]; then
  # Redirect to session-specific index
  export GIT_INDEX_FILE=".git/indexes/session-$SESSION_ID"
fi
```

**Questions to Answer**:
1. How is the session ID generated and persisted?
2. How do hooks access session state?
3. What happens if hook script crashes?
4. How are hook outputs logged?

#### B. Git Index Manipulation

**What to Extract**:
- [ ] GIT_INDEX_FILE environment variable usage
- [ ] Index creation commands
- [ ] Index merging strategies
- [ ] Conflict resolution approaches

**Commands to Document**:
```bash
# Create session-specific index
git read-tree --index-output=.git/indexes/session-$ID HEAD

# Add to session index
GIT_INDEX_FILE=.git/indexes/session-$ID git add file.txt

# Commit from session index
GIT_INDEX_FILE=.git/indexes/session-$ID git commit -m "..."
```

**Questions to Answer**:
1. How are indexes initialized?
2. Can indexes be merged?
3. What's the cleanup process?
4. How are conflicts detected?

#### C. Session Management

**What to Extract**:
- [ ] Session tracking mechanism
- [ ] Session metadata storage
- [ ] Session cleanup procedures
- [ ] Multi-session coordination

**Questions to Answer**:
1. Where is session state stored?
2. How do sessions discover each other?
3. Can sessions communicate?
4. What's the maximum concurrent sessions?

#### D. Branch Management

**What to Extract**:
- [ ] Branch naming conventions
- [ ] Branch creation from indexes
- [ ] Branch cleanup strategies
- [ ] Branch merging workflows

**Questions to Answer**:
1. How are session branches named?
2. Are branches automatically cleaned up?
3. How are conflicts between branches resolved?
4. Is there a review process before merging?

### Scripts to Extract

```bash
hooks/
├── pre-tool-use.sh             # Session isolation
├── post-tool-use.sh            # Index management
├── stop.sh                     # Branch creation
└── lib/
    ├── session-manager.sh      # Session utilities
    └── index-manager.sh        # Git index utilities
```

---

## 5. rahulvrane/awesome-claude-agents

**Repository**: https://github.com/vijaythecoder/awesome-clauge-agents

### Priority: LOW (but useful for agent design) ⭐⭐

### Investigation Tasks

#### A. Agent Role Definitions

**What to Extract**:
- [ ] Complete agent role list
- [ ] Agent specialization descriptions
- [ ] Agent system prompts/instructions
- [ ] Agent capability definitions

**Agents to Study**:
- [ ] `@agent-tech-lead-orchestrator`
- [ ] `@agent-frontend-developer`
- [ ] `@agent-backend-developer`
- [ ] `@agent-code-reviewer`
- [ ] `@agent-api-architect`
- [ ] `@agent-database-designer`
- [ ] `@agent-security-auditor`

**Questions to Answer**:
1. How detailed are agent instructions?
2. Do agents have memory/context?
3. Can agents learn/improve over time?
4. How are agent conflicts resolved?

#### B. Orchestrator Patterns

**What to Extract**:
- [ ] Task delegation logic
- [ ] Work breakdown strategies
- [ ] Result aggregation patterns
- [ ] Conflict resolution approaches

**Questions to Answer**:
1. How does orchestrator decide task assignment?
2. Can agents reject tasks?
3. How are dependencies handled?
4. What happens if an agent fails?

#### C. Context Management

**What to Extract**:
- [ ] Context window optimization techniques
- [ ] Information compression strategies
- [ ] Token budget management
- [ ] Context handoff patterns

**Questions to Answer**:
1. How do they avoid context overflow?
2. What information is preserved vs. discarded?
3. Can context be checkpointed?
4. How is context shared between agents?

#### D. Prompt Engineering

**What to Extract**:
- [ ] Agent personality prompts
- [ ] Expertise domain prompts
- [ ] Communication style prompts
- [ ] Collaboration protocol prompts

**Questions to Answer**:
1. How are agents made distinct?
2. Do agents have consistent personalities?
3. How are prompts versioned?
4. Can users customize agents?

### Files to Extract

```
awesome-claude-agents/
├── agents/
│   ├── orchestrator.md
│   ├── frontend-dev.md
│   ├── backend-dev.md
│   ├── code-reviewer.md
│   └── security-auditor.md
├── workflows/
│   ├── feature-development.md
│   └── bug-fix.md
└── prompts/
    └── templates/
```

---

## Investigation Workflow

### Phase 1: Repository Cloning

```bash
# Clone repositories
cd ~/research/claude-parallel/

git clone https://github.com/ruvnet/claude-flow.git
git clone https://github.com/parruda/swarm.git
git clone https://github.com/namastexlabs/automagik-forge.git
git clone https://github.com/vijaythecoder/awesome-clauge-agents.git

# Archive old claude-swarm v1 for reference
git clone --branch v0.1.16 https://github.com/parruda/claude-swarm.git claude-swarm-v1
```

### Phase 2: Code Analysis

For each repository:

1. **Read Documentation First**
   - README.md
   - ARCHITECTURE.md
   - CONTRIBUTING.md
   - Wiki pages

2. **Identify Key Files**
   - Look for hook configurations
   - Find orchestrator code
   - Locate state management
   - Review examples

3. **Extract Patterns**
   - Copy relevant code snippets
   - Document design decisions
   - Note gotchas/pitfalls
   - Measure complexity

4. **Ask Questions**
   - Open issues if clarification needed
   - Check existing discussions
   - Search for related blog posts
   - Find conference talks

### Phase 3: Experimentation

For critical discoveries:

1. **Create Minimal Reproduction**
   - Isolate the pattern
   - Strip to essentials
   - Test independently

2. **Benchmark Performance**
   - Measure execution time
   - Profile memory usage
   - Test concurrency limits
   - Identify bottlenecks

3. **Document Findings**
   - Write up results
   - Include code samples
   - Note prerequisites
   - List trade-offs

### Phase 4: Integration Planning

After all investigations:

1. **Synthesize Learnings**
   - Compare approaches
   - Identify best patterns
   - Note incompatibilities
   - Plan hybrid solution

2. **Update Architecture**
   - Revise design docs
   - Update code structure
   - Modify implementation plan
   - Adjust timelines

3. **Prototype Proof-of-Concept**
   - Implement critical path
   - Test hybrid approach
   - Validate assumptions
   - Measure performance

---

## Success Metrics

### What Constitutes "Complete" Investigation

For each framework, investigation is complete when we can answer:

1. **Core Architecture**: How does it fundamentally work?
2. **Key Innovation**: What's the unique insight?
3. **Implementation Details**: How would we rebuild it?
4. **Performance Characteristics**: How fast/slow/scalable?
5. **Trade-offs**: What did they sacrifice for what gain?
6. **Applicability**: Should we adopt/adapt/reject?

### Documentation Outputs

Each investigation should produce:

- [ ] Architecture summary (1-2 pages)
- [ ] Code snippets collection
- [ ] Performance data (if available)
- [ ] Integration recommendation
- [ ] Implementation checklist

---

## Timeline

### Week 1: claude-flow
- Deep dive into hooks system
- Extract SQLite schema
- Study parallel execution
- Document findings

### Week 2: SwarmSDK
- Analyze architectural migration
- Study in-process workers
- Examine semantic memory
- Compare v1 vs v2

### Week 3: automagik-forge + Beast Mode
- Git worktree patterns
- MCP server implementation
- Advanced hook techniques
- Session isolation

### Week 4: Synthesis
- Compare all approaches
- Design hybrid architecture
- Build proof-of-concept
- Validate decisions

---

## Contact/Support

If you encounter issues or need clarification:

1. **Check Existing Docs**: Most answers in official docs
2. **Search Issues**: Others may have asked
3. **Community Forums**: Discord/Slack channels
4. **Direct Contact**: Open issue (be respectful)

## Notes

- Prioritize `claude-flow` and `SwarmSDK` - most relevant
- Beast Mode hooks are pure gold - extract completely
- awesome-agents is reference material only
- Document everything - future you will thank present you