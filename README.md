# EZgraph

**Instant codebase knowledge graph MCP server.**

Drop it into any project. It auto-detects languages, indexes every function, class, and call chain, then serves it all through MCP (Model Context Protocol) — so your LLM can navigate code in milliseconds instead of reading thousands of lines.

## Why

Reading 5,000 lines to understand a call chain costs ~50K tokens. One graph query costs ~200 tokens. **That's a 250x cost reduction.**

EZgraph turns any codebase into a queryable knowledge graph with zero configuration.

## Supported Languages (20+)

Python, Rust, Go, TypeScript, JavaScript, Java, C, C++, C#, Ruby, PHP, Swift, Kotlin, Scala, Zig, Lua, Elixir, Dart, Vortex — plus aliases (.jsx, .tsx, .mjs, .hpp, .cc, .exs).

## Install

```bash
pip install ezgraph
```

Or clone:

```bash
git clone https://github.com/MangoByteLabs/EZgraph.git
cd EZgraph
pip install -e .
```

## Quick Start

### As MCP Server (for Claude, etc.)

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "ezgraph": {
      "command": "ezgraph",
      "args": ["/path/to/your/project"]
    }
  }
}
```

Or with Python directly:

```json
{
  "mcpServers": {
    "ezgraph": {
      "command": "python3",
      "args": ["-m", "ezgraph", "/path/to/your/project"]
    }
  }
}
```

### CLI Mode

```bash
# Stats overview
ezgraph /path/to/project --stats

# Quick function lookup
ezgraph /path/to/project --query main

# Dump full graph JSON
ezgraph /path/to/project --dump
```

## What It Indexes

| Feature | Description |
|---------|-------------|
| **Functions** | Name, params, return type, location, docstring |
| **Classes** | Structs, enums, traits, interfaces, modules |
| **Call Graph** | Who calls whom — full caller/callee edges |
| **Subsystems** | Auto-classified from directory structure |
| **Pipelines** | Auto-detected from function naming patterns |
| **Constants** | UPPER_CASE constants, typed consts, finals |
| **Cross-edges** | Cross-subsystem dependency map |
| **Sections** | Code sections marked with `// SECTION` or `# SECTION` |

## MCP Tools (12)

| Tool | Description |
|------|-------------|
| `ezgraph_overview` | Project summary: files, functions, languages, subsystems |
| `ezgraph_function` | Look up any function — signature, location, callers, callees |
| `ezgraph_callers` | Full call graph for a function |
| `ezgraph_search` | Search everything: functions, classes, sections, constants |
| `ezgraph_file` | File info: functions, classes, sections, language |
| `ezgraph_read` | Read source code of a function or file region |
| `ezgraph_subsystem` | Deep dive into a subsystem |
| `ezgraph_pipeline` | Trace a pipeline (parse, validate, compile, etc.) |
| `ezgraph_dataflow` | Upstream callers and downstream callees |
| `ezgraph_trace` | Depth-limited call chain trace |
| `ezgraph_hotspots` | Most connected functions (highest fan-in + fan-out) |
| `ezgraph_architecture` | Architecture map: subsystems and cross-dependencies |

## Auto-Reindex

EZgraph watches for file changes and a `.graph-dirty` sentinel file. Touch `.graph-dirty` in your project root (e.g., from a git post-commit hook) and the graph rebuilds automatically on the next query.

```bash
# Add to .git/hooks/post-commit:
touch .graph-dirty
```

## Performance

| Project Size | Files | Functions | Index Time |
|-------------|-------|-----------|------------|
| Small (1K LOC) | ~10 | ~40 | <0.1s |
| Medium (50K LOC) | ~200 | ~2,000 | ~0.5s |
| Large (360K LOC) | ~550 | ~16,000 | ~2s |

Zero dependencies. Pure Python. Works everywhere Python 3.10+ runs.

## How It Works

1. **Walk** — recursively finds all source files, skipping `node_modules`, `.git`, `__pycache__`, etc.
2. **Detect** — identifies language from file extension, loads the right regex patterns
3. **Extract** — pulls out functions, classes, sections, constants from each file
4. **Connect** — builds a call graph by scanning function bodies for known function names
5. **Classify** — auto-groups files into subsystems based on directory structure
6. **Serve** — exposes everything through 12 MCP tools over JSON-RPC stdin/stdout

## License

MIT
