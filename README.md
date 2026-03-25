# LiLBrain

**Instant codebase knowledge graph MCP server.**

Drop it into any project. It auto-detects languages, indexes every function, class, and call chain, then serves it all through MCP (Model Context Protocol) — so your LLM can navigate code in milliseconds instead of reading thousands of lines.

## Why

Reading 5,000 lines to understand a call chain costs ~50K tokens. One graph query costs ~200 tokens. **That's a 250x cost reduction.**

LiLBrain turns any codebase into a queryable knowledge graph with zero configuration.

## Supported Languages (20+)

Python, Rust, Go, TypeScript, JavaScript, Java, C, C++, C#, Ruby, PHP, Swift, Kotlin, Scala, Zig, Lua, Elixir, Dart, Vortex — plus aliases (.jsx, .tsx, .mjs, .hpp, .cc, .exs).

## Install

```bash
pip install lilbrain
```

Or clone:

```bash
git clone https://github.com/MangoByteLabs/LiLBrain.git
cd LiLBrain
pip install -e .
```

## Quick Start

### As MCP Server (for Claude, etc.)

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "lilbrain": {
      "command": "lilbrain",
      "args": ["/path/to/your/project"]
    }
  }
}
```

Or with Python directly:

```json
{
  "mcpServers": {
    "lilbrain": {
      "command": "python3",
      "args": ["-m", "lilbrain", "/path/to/your/project"]
    }
  }
}
```

### CLI Mode

```bash
# Stats overview
lilbrain /path/to/project --stats

# Quick function lookup
lilbrain /path/to/project --query main

# Dump full graph JSON
lilbrain /path/to/project --dump
```

## What It Indexes

| Feature | Description |
|---------|-------------|
| **Functions** | Name, params, return type, location, docstring, complexity scores |
| **Classes** | Structs, enums, traits, interfaces, modules |
| **Call Graph** | Who calls whom — full caller/callee edges |
| **Subsystems** | Auto-classified from directory structure |
| **Pipelines** | Auto-detected from function naming patterns |
| **Constants** | UPPER_CASE constants, typed consts, finals |
| **Cross-edges** | Cross-subsystem dependency map |
| **Sections** | Code sections marked with `// SECTION` or `# SECTION` |
| **Complexity** | Cyclomatic + cognitive complexity per function |
| **Semantic Index** | TF-IDF vectors for meaning-based search |

## MCP Tools (24)

### Core Graph (12)

| Tool | Description |
|------|-------------|
| `lilbrain_overview` | Project summary: files, functions, languages, subsystems |
| `lilbrain_function` | Look up any function — signature, location, callers, callees |
| `lilbrain_callers` | Full call graph for a function |
| `lilbrain_search` | Search everything: functions, classes, sections, constants |
| `lilbrain_file` | File info: functions, classes, sections, language |
| `lilbrain_read` | Read source code of a function or file region |
| `lilbrain_subsystem` | Deep dive into a subsystem |
| `lilbrain_pipeline` | Trace a pipeline (parse, validate, compile, etc.) |
| `lilbrain_dataflow` | Upstream callers and downstream callees |
| `lilbrain_trace` | Depth-limited call chain trace |
| `lilbrain_hotspots` | Most connected functions (highest fan-in + fan-out) |
| `lilbrain_architecture` | Architecture map: subsystems and cross-dependencies |

### Impact & Quality (4)

| Tool | Description |
|------|-------------|
| `lilbrain_impact` | Blast radius analysis — change a function, see everything affected |
| `lilbrain_deadcode` | Find functions with zero callers + LOC waste estimate |
| `lilbrain_clones` | Detect near-duplicate functions (token Jaccard similarity) |
| `lilbrain_diagram` | Auto-generate Mermaid or D2 architecture diagrams |

### Intelligence (4)

| Tool | Description |
|------|-------------|
| `lilbrain_complexity` | Cyclomatic + cognitive complexity ranking |
| `lilbrain_complexity_velocity` | Track complexity changes over git history |
| `lilbrain_semantic` | Semantic search — find functions by meaning, not name |
| `lilbrain_federation` | Multi-repo federated search across codebases |

### Tier 3 — AI-Native (4)

| Tool | Description |
|------|-------------|
| `lilbrain_ask` | Natural language questions — auto-routes to the right analysis |
| `lilbrain_diff` | Git-aware graph diff: changed functions, blast radius, risk |
| `lilbrain_pr_review` | Auto-generate PR review context with risk assessment |
| `lilbrain_runtime` | Correlate OpenTelemetry traces with static call graph |

## Features

### Impact Analysis

Change a function? LiLBrain tells you exactly what breaks:

```
lilbrain_impact("parse_request")
→ 47 functions affected across 5 subsystems
→ Risk: HIGH
→ Subsystems: api, auth, middleware, handlers, tests
```

### Auto Architecture Diagrams

Generate always-accurate Mermaid diagrams from live code:

```
lilbrain_diagram("architecture")
→ graph TD
      api["api\n120 fns | 3400 LOC"]
      auth["auth\n45 fns | 1200 LOC"]
      api -->|12| auth
```

### Dead Code & Clone Detection

```
lilbrain_deadcode()
→ 847/3200 functions unreachable (26.5%)
→ 12,400 LOC wasted

lilbrain_clones()
→ adam_step <-> adamw_step (88.5% similar)
→ tcp_recv <-> udp_recv (83.3% similar)
```

### Semantic Search

Find functions by what they do, not what they're named:

```
lilbrain_semantic("handle user authentication")
→ verify_token (auth/jwt.py:45) score=14.2
→ check_session (middleware/session.rs:120) score=11.8
→ validate_credentials (api/login.go:33) score=9.4
```

### Natural Language Queries

```
lilbrain_ask("what is the most complex code?")
→ eval_stmt: cyclomatic=189, cognitive=198
→ lex: cyclomatic=171, cognitive=182

lilbrain_ask("show me dead code")
→ 847 functions with zero callers...

lilbrain_ask("who calls parse_request?")
→ handle_http, route_api, middleware_chain...
```

### Git Time-Travel & PR Review

```
lilbrain_diff("main", "feature-branch")
→ 12 files changed, 34 functions modified
→ Blast radius: 156 functions affected
→ Risk: HIGH
→ New cross-subsystem edge: api -> payments (didn't exist before!)

lilbrain_pr_review()
→ **8 files changed**, **23 functions modified**
→ **Blast radius**: 89 functions potentially affected
→ **Risk**: MEDIUM
→ **New cross-subsystem edges**: auth -> billing
→ **Complexity in changed code**: 45
```

### Multi-Repo Federation

Search across all your repos at once:

```
lilbrain_federation(query="authenticate", repos=["/app/api", "/app/auth", "/app/gateway"])
→ api: 3 matches
→ auth: 12 matches
→ gateway: 5 matches
```

### Runtime Correlation

Connect static analysis to production reality:

```
lilbrain_runtime(trace_dir="traces/")
→ Hot paths: handle_request (45,000 calls, avg 2.3ms)
→ Cold code: legacy_handler (0 invocations — truly dead)
```

## Auto-Reindex

LiLBrain watches for file changes and a `.graph-dirty` sentinel file. Touch `.graph-dirty` in your project root (e.g., from a git post-commit hook) and the graph rebuilds automatically on the next query.

```bash
# Add to .git/hooks/post-commit:
touch .graph-dirty
```

## Performance

| Project Size | Files | Functions | Index Time |
|-------------|-------|-----------|------------|
| Small (1K LOC) | ~10 | ~40 | <0.1s |
| Medium (50K LOC) | ~200 | ~2,000 | ~0.5s |
| Large (360K LOC) | ~550 | ~16,800 | ~2.2s |

Zero dependencies. Pure Python 3.10+. Works everywhere.

## How It Works

1. **Walk** — recursively finds all source files, skipping `node_modules`, `.git`, `__pycache__`, etc.
2. **Detect** — identifies language from file extension, loads the right regex patterns
3. **Extract** — pulls out functions, classes, sections, constants from each file
4. **Connect** — builds a call graph by scanning function bodies for known function names
5. **Analyze** — computes complexity scores, builds TF-IDF semantic index
6. **Classify** — auto-groups files into subsystems based on directory structure
7. **Serve** — exposes everything through 24 MCP tools over JSON-RPC stdin/stdout

## License

MIT
