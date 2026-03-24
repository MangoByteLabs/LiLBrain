#!/usr/bin/env python3
"""
EZgraph — Instant codebase knowledge graph MCP server.

Drop into any project. Auto-detects languages. Indexes everything.
One server, any codebase, 20 tools.

Usage:
    ezgraph                          # index current directory
    ezgraph /path/to/project         # index specific project
    ezgraph --port 8080              # HTTP mode (coming soon)

Supported languages:
    Python, Rust, Go, TypeScript, JavaScript, Java, C, C++, C#,
    Ruby, PHP, Swift, Kotlin, Scala, Zig, Vortex (.vx), and more.
"""

import json
import sys
import os
import re
import glob as globmod
import subprocess
import struct
import time
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Language detection and function extraction patterns
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGES = {
    # extension → {name, fn_pattern, class_pattern, section_pattern, comment_prefix}
    '.py': {
        'name': 'Python',
        'fn_re': re.compile(r'^(\s*)def\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^class\s+(\w+)'),
        'section_re': re.compile(r'#\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '#',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': True,
    },
    '.rs': {
        'name': 'Rust',
        'fn_re': re.compile(r'^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:pub\s+)?(?:struct|enum|trait|impl)\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*[:(]\s*'),
        'indent_based': False,
    },
    '.go': {
        'name': 'Go',
        'fn_re': re.compile(r'^func\s+(?:\([^)]*\)\s+)?(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^type\s+(\w+)\s+(?:struct|interface)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.ts': {
        'name': 'TypeScript',
        'fn_re': re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*[(<]'),
        'indent_based': False,
    },
    '.js': {
        'name': 'JavaScript',
        'fn_re': re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:export\s+)?class\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.jsx': None,  # filled from .js
    '.tsx': None,  # filled from .ts
    '.mjs': None,  # filled from .js
    '.java': {
        'name': 'Java',
        'fn_re': re.compile(r'^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:[\w<>\[\],\s]+)\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.c': {
        'name': 'C',
        'fn_re': re.compile(r'^(?:static\s+)?(?:inline\s+)?(?:[\w*]+\s+)+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^(?:typedef\s+)?struct\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.h': None,   # filled from .c
    '.cpp': {
        'name': 'C++',
        'fn_re': re.compile(r'^\s*(?:virtual\s+)?(?:static\s+)?(?:inline\s+)?(?:[\w:*&<>,\s]+)\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*class\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*[(<]'),
        'indent_based': False,
    },
    '.hpp': None,  # filled from .cpp
    '.cc': None,   # filled from .cpp
    '.cs': {
        'name': 'C#',
        'fn_re': re.compile(r'^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?(?:async\s+)?(?:[\w<>\[\]?,\s]+)\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:public\s+)?(?:abstract\s+)?(?:partial\s+)?class\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+|#region)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*[(<]'),
        'indent_based': False,
    },
    '.rb': {
        'name': 'Ruby',
        'fn_re': re.compile(r'^\s*def\s+(?:self\.)?(\w+)(.*)'),
        'class_re': re.compile(r'^\s*(?:class|module)\s+(\w+)'),
        'section_re': re.compile(r'#\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '#',
        'call_re': re.compile(r'\b(\w+)\s*[(\s]'),
        'indent_based': False,
    },
    '.php': {
        'name': 'PHP',
        'fn_re': re.compile(r'^\s*(?:public|private|protected)?\s*(?:static\s+)?function\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:abstract\s+)?class\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.swift': {
        'name': 'Swift',
        'fn_re': re.compile(r'^\s*(?:public\s+)?(?:static\s+)?(?:override\s+)?func\s+(\w+)\s*(?:<[^>]*>)?\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:public\s+)?(?:final\s+)?(?:class|struct|enum|protocol)\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:MARK|SECTION|===+)\s*:?\s*(.+)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.kt': {
        'name': 'Kotlin',
        'fn_re': re.compile(r'^\s*(?:private\s+)?(?:suspend\s+)?fun\s+(?:<[^>]*>\s+)?(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:data\s+)?(?:sealed\s+)?(?:abstract\s+)?class\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*[(<]'),
        'indent_based': False,
    },
    '.scala': {
        'name': 'Scala',
        'fn_re': re.compile(r'^\s*(?:private\s+)?def\s+(\w+)\s*(?:\[.*?\])?\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:case\s+)?(?:abstract\s+)?(?:class|object|trait)\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*[(\[]'),
        'indent_based': False,
    },
    '.zig': {
        'name': 'Zig',
        'fn_re': re.compile(r'^\s*(?:pub\s+)?fn\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:pub\s+)?const\s+(\w+)\s*=\s*(?:struct|enum|union)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.vx': {
        'name': 'Vortex',
        'fn_re': re.compile(r'^fn\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^struct\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.lua': {
        'name': 'Lua',
        'fn_re': re.compile(r'^\s*(?:local\s+)?function\s+([.\w]+)\s*\((.*)'),
        'class_re': None,
        'section_re': re.compile(r'--\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '--',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.ex': {
        'name': 'Elixir',
        'fn_re': re.compile(r'^\s*(?:def|defp)\s+(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*defmodule\s+(\S+)'),
        'section_re': re.compile(r'#\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '#',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
    '.exs': None,  # filled from .ex
    '.dart': {
        'name': 'Dart',
        'fn_re': re.compile(r'^\s*(?:[\w<>?]+\s+)?(\w+)\s*\((.*)'),
        'class_re': re.compile(r'^\s*(?:abstract\s+)?class\s+(\w+)'),
        'section_re': re.compile(r'//\s*(?:SECTION|===+)\s*(\S+):?\s*(.*)'),
        'comment': '//',
        'call_re': re.compile(r'\b(\w+)\s*\('),
        'indent_based': False,
    },
}

# Fill aliases
for ext, alias_src in [('.jsx', '.js'), ('.tsx', '.ts'), ('.mjs', '.js'),
                        ('.h', '.c'), ('.hpp', '.cpp'), ('.cc', '.cpp'),
                        ('.exs', '.ex')]:
    if LANGUAGES[ext] is None and alias_src in LANGUAGES:
        LANGUAGES[ext] = LANGUAGES[alias_src]

# Skip patterns
SKIP_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
    '.tox', '.mypy_cache', '.pytest_cache', 'dist', 'build',
    '.next', '.nuxt', '.svelte-kit', 'target', 'vendor',
    '.idea', '.vscode', '.settings', 'coverage', '.coverage',
    'egg-info', '.eggs', '__pypackages__',
}

SKIP_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'Cargo.lock', 'go.sum', 'poetry.lock', 'Pipfile.lock',
}


# ─────────────────────────────────────────────────────────────────────────────
# Graph Watcher — auto-reindex on file changes
# ─────────────────────────────────────────────────────────────────────────────

class GraphWatcher:
    """Track file mtimes and a .graph-dirty sentinel for staleness detection."""

    def __init__(self):
        self._tracked: list[str] = []
        self._mtimes: dict[str, float] = {}
        self._sentinel: Optional[str] = None

    def track_dir(self, directory: str, extensions: list[str]):
        directory = os.path.abspath(directory)
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            for f in files:
                ext = os.path.splitext(f)[1]
                if ext in extensions and f not in SKIP_FILES:
                    path = os.path.join(root, f)
                    if path not in self._tracked:
                        self._tracked.append(path)

    def track_sentinel(self, repo_root: str):
        self._sentinel = os.path.join(repo_root, '.graph-dirty')

    def snapshot(self):
        self._mtimes = {}
        for p in self._tracked:
            try:
                self._mtimes[p] = os.path.getmtime(p)
            except OSError:
                self._mtimes[p] = 0.0
        if self._sentinel and os.path.exists(self._sentinel):
            try:
                os.remove(self._sentinel)
            except OSError:
                pass

    def is_stale(self) -> bool:
        if self._sentinel and os.path.exists(self._sentinel):
            return True
        if not self._mtimes:
            return False
        for p in self._tracked:
            try:
                if os.path.getmtime(p) != self._mtimes.get(p, 0.0):
                    return True
            except OSError:
                if p in self._mtimes:
                    return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# EZgraph — the unified knowledge graph
# ─────────────────────────────────────────────────────────────────────────────

class EZgraph:
    """Universal codebase knowledge graph. Any language, any project."""

    def __init__(self, root_dir: str):
        self.root = os.path.abspath(root_dir)
        self.project_name = os.path.basename(self.root)

        # Core indexes
        self.functions = {}     # key → {name, file, line_start, line_end, params, returns, doc, section, subsystem, calls, callers, language}
        self.classes = {}       # key → {name, file, line, methods, doc, subsystem}
        self.files = {}         # rel_path → {lines, functions, classes, sections, subsystem, language}
        self.sections = {}      # "file::id" → {name, line_start, line_end, functions}
        self.subsystems = {}    # name → {description, files, functions, lines, layer}
        self.constants = {}     # name → {value, file, line}
        self.cross_edges = []   # [{from_sub, to_sub, from_fn, to_fn}]

        # Detected languages
        self.languages_found = {}  # language_name → file_count

        # Pipeline detection
        self.pipelines = {}

        # Source cache
        self._source_cache = {}

    def build(self):
        """Build the complete graph."""
        t0 = time.monotonic()
        self._index_files()
        self._extract_functions()
        self._extract_classes()
        self._build_call_graph()
        self._classify_subsystems()
        self._detect_pipelines()
        self._extract_constants()
        self._build_cross_edges()
        self.build_time = time.monotonic() - t0

    def _read_file(self, path):
        if path not in self._source_cache:
            try:
                with open(path, 'r', errors='replace') as f:
                    self._source_cache[path] = f.readlines()
            except Exception:
                self._source_cache[path] = []
        return self._source_cache[path]

    def _rel(self, path):
        return os.path.relpath(path, self.root)

    def _get_lang(self, path):
        ext = os.path.splitext(path)[1]
        return LANGUAGES.get(ext)

    def _index_files(self):
        """Find and index all source files."""
        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            for f in files:
                if f in SKIP_FILES:
                    continue
                path = os.path.join(root, f)
                lang = self._get_lang(path)
                if lang is None:
                    continue

                lines = self._read_file(path)
                rel = self._rel(path)
                self.files[rel] = {
                    'lines': len(lines),
                    'functions': [],
                    'classes': [],
                    'sections': [],
                    'subsystem': self._classify_file(rel),
                    'language': lang['name'],
                    'abs_path': path,
                }
                self.languages_found[lang['name']] = self.languages_found.get(lang['name'], 0) + 1

    def _classify_file(self, rel_path):
        """Classify file into subsystem by directory structure."""
        parts = rel_path.replace('\\', '/').split('/')
        if len(parts) <= 1:
            return 'root'
        # Use first meaningful directory as subsystem
        first_dir = parts[0]
        if first_dir in ('src', 'lib', 'pkg', 'internal', 'app'):
            return parts[1] if len(parts) > 2 else 'core'
        if first_dir in ('test', 'tests', 'spec', 'specs', '__tests__'):
            return 'tests'
        if first_dir in ('docs', 'doc', 'documentation'):
            return 'docs'
        if first_dir in ('scripts', 'tools', 'bin', 'cmd'):
            return 'tools'
        if first_dir in ('examples', 'example', 'samples', 'demo'):
            return 'examples'
        if first_dir in ('config', 'configs', 'conf'):
            return 'config'
        return first_dir

    def _extract_functions(self):
        """Extract all function definitions."""
        for rel_path, finfo in self.files.items():
            lang = self._get_lang(finfo['abs_path'])
            if not lang or not lang.get('fn_re'):
                continue

            lines = self._read_file(finfo['abs_path'])
            current_section = None

            # Sections first
            sec_re = lang.get('section_re')
            if sec_re:
                for i, line in enumerate(lines):
                    m = sec_re.match(line.strip())
                    if m:
                        sid = m.group(1).rstrip(':')
                        sname = m.group(2).strip() if m.lastindex >= 2 else sid
                        sec_key = f"{rel_path}::{sid}"
                        self.sections[sec_key] = {
                            'name': sname or sid,
                            'line_start': i + 1,
                            'line_end': None,
                            'functions': [],
                            'file': rel_path,
                        }
                        finfo['sections'].append(sec_key)

            # Fix section end lines
            file_secs = finfo['sections']
            for idx, sk in enumerate(file_secs):
                if idx + 1 < len(file_secs):
                    self.sections[sk]['line_end'] = self.sections[file_secs[idx+1]]['line_start'] - 1
                else:
                    self.sections[sk]['line_end'] = finfo['lines']

            # Functions
            fn_re = lang['fn_re']
            for i, line in enumerate(lines):
                # Track current section
                current_section = None
                for sk in file_secs:
                    sec = self.sections[sk]
                    if sec['line_start'] <= i + 1 <= (sec['line_end'] or finfo['lines']):
                        current_section = sk

                m = fn_re.match(line)
                if not m:
                    continue

                # Extract name — handle different group positions
                if lang.get('indent_based'):
                    # Python: group 1 = indent, group 2 = name
                    indent = m.group(1)
                    name = m.group(2)
                    params = m.group(3).rstrip('):').strip() if m.lastindex >= 3 else ''
                else:
                    name = m.group(1)
                    params = m.group(2).rstrip('){:').strip() if m.lastindex >= 2 else ''

                # Skip common false positives
                if name in ('if', 'for', 'while', 'switch', 'catch', 'return', 'new', 'sizeof', 'typeof', 'instanceof'):
                    continue

                end_line = self._find_fn_end(lines, i, lang)

                # Doc comment
                doc = ''
                if i > 0:
                    prev = lines[i-1].strip()
                    comment_prefix = lang.get('comment', '//')
                    if prev.startswith(comment_prefix):
                        doc = prev.lstrip(comment_prefix + ' ').strip()

                # Return type
                returns = ''
                ret_match = re.search(r'->\s*(\S+)', line)
                if ret_match:
                    returns = ret_match.group(1).rstrip('{:')

                fn_key = name
                if fn_key in self.functions:
                    fn_key = f"{rel_path}::{name}"

                self.functions[fn_key] = {
                    'name': name,
                    'file': rel_path,
                    'line_start': i + 1,
                    'line_end': end_line,
                    'params': params[:200],
                    'returns': returns,
                    'doc': doc[:200],
                    'section': current_section,
                    'subsystem': finfo['subsystem'],
                    'calls': [],
                    'callers': [],
                    'language': lang['name'],
                }

                finfo['functions'].append(fn_key)
                if current_section and current_section in self.sections:
                    self.sections[current_section]['functions'].append(fn_key)

    def _find_fn_end(self, lines, start, lang):
        """Find function end line."""
        if lang.get('indent_based'):
            # Python: find next line at same or lower indent
            first_line = lines[start]
            base_indent = len(first_line) - len(first_line.lstrip())
            for i in range(start + 1, min(start + 1000, len(lines))):
                line = lines[i]
                stripped = line.strip()
                if not stripped:
                    continue
                indent = len(line) - len(line.lstrip())
                if indent <= base_indent and stripped and not stripped.startswith('#'):
                    return i
            return min(start + 50, len(lines))
        else:
            # Brace-based languages
            depth = 0
            for i in range(start, min(start + 2000, len(lines))):
                for ch in lines[i]:
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                if depth <= 0 and i > start:
                    return i + 1
            return min(start + 50, len(lines))

    def _extract_classes(self):
        """Extract class/struct/trait/interface definitions."""
        for rel_path, finfo in self.files.items():
            lang = self._get_lang(finfo['abs_path'])
            if not lang or not lang.get('class_re'):
                continue

            lines = self._read_file(finfo['abs_path'])
            cls_re = lang['class_re']
            for i, line in enumerate(lines):
                m = cls_re.match(line)
                if m:
                    name = m.group(1)
                    if name in ('if', 'for', 'while', 'return'):
                        continue
                    cls_key = name
                    if cls_key in self.classes:
                        cls_key = f"{rel_path}::{name}"
                    self.classes[cls_key] = {
                        'name': name,
                        'file': rel_path,
                        'line': i + 1,
                        'subsystem': finfo['subsystem'],
                        'language': lang['name'],
                    }
                    finfo['classes'].append(cls_key)

    def _build_call_graph(self):
        """Build caller/callee edges."""
        fn_names = {finfo['name'] for finfo in self.functions.values()}

        for fn_key, finfo in self.functions.items():
            lang = self._get_lang(os.path.join(self.root, finfo['file']))
            if not lang:
                continue

            lines = self._read_file(os.path.join(self.root, finfo['file']))
            start = finfo['line_start'] - 1
            end = finfo['line_end'] or (start + 50)
            body = ''.join(lines[start:min(end, len(lines))])

            call_re = lang.get('call_re', re.compile(r'\b(\w+)\s*\('))
            calls_found = set()
            for m in call_re.finditer(body):
                callee = m.group(1)
                if callee in fn_names and callee != finfo['name']:
                    calls_found.add(callee)

            finfo['calls'] = list(calls_found)
            for callee_name in calls_found:
                if callee_name in self.functions:
                    self.functions[callee_name]['callers'].append(fn_key)

    def _classify_subsystems(self):
        """Build subsystem index."""
        sub_map = {}
        for rel_path, finfo in self.files.items():
            sub = finfo['subsystem']
            if sub not in sub_map:
                sub_map[sub] = {'files': [], 'functions': 0, 'lines': 0, 'languages': set()}
            sub_map[sub]['files'].append(rel_path)
            sub_map[sub]['functions'] += len(finfo['functions'])
            sub_map[sub]['lines'] += finfo['lines']
            sub_map[sub]['languages'].add(finfo['language'])

        for name, data in sub_map.items():
            self.subsystems[name] = {
                'files': data['files'],
                'file_count': len(data['files']),
                'functions': data['functions'],
                'lines': data['lines'],
                'languages': sorted(data['languages']),
            }

    def _detect_pipelines(self):
        """Auto-detect pipelines from function naming patterns."""
        pipeline_keywords = [
            'init', 'setup', 'start', 'stop', 'shutdown', 'cleanup',
            'parse', 'validate', 'transform', 'process', 'handle',
            'encode', 'decode', 'serialize', 'deserialize',
            'request', 'response', 'middleware',
            'connect', 'disconnect', 'send', 'receive',
            'read', 'write', 'open', 'close',
            'compile', 'build', 'link', 'emit',
            'login', 'logout', 'authenticate', 'authorize',
        ]
        for kw in pipeline_keywords:
            stages = []
            for fn_key, finfo in self.functions.items():
                if kw in finfo['name'].lower():
                    stages.append({
                        'function': fn_key,
                        'name': finfo['name'],
                        'file': finfo['file'],
                        'line': finfo['line_start'],
                    })
            if stages:
                self.pipelines[kw] = stages[:20]

    def _extract_constants(self):
        """Extract obvious constants."""
        const_patterns = [
            re.compile(r'^\s*(?:const|final|static final)\s+\w+\s+(\w+)\s*=\s*(.+)'),     # typed const
            re.compile(r'^\s*(?:const|let|var)\s+([A-Z_][A-Z_0-9]+)\s*=\s*(.+)'),           # JS/TS UPPER_CASE
            re.compile(r'^([A-Z_][A-Z_0-9]+)\s*=\s*(.+)'),                                   # Python UPPER_CASE
            re.compile(r'^fn\s+([A-Z_][A-Z_0-9]+)\(\)\s*->\s*\w+\s*\{\s*return\s+(.+)'),   # Vortex zero-arg const
        ]
        for rel_path, finfo in self.files.items():
            lines = self._read_file(finfo['abs_path'])
            for i, line in enumerate(lines):
                for pat in const_patterns:
                    m = pat.match(line.strip())
                    if m:
                        name = m.group(1)
                        value = m.group(2).rstrip('};,').strip()[:100]
                        if name not in self.constants:
                            self.constants[name] = {'value': value, 'file': rel_path, 'line': i + 1}
                        break

    def _build_cross_edges(self):
        """Build cross-subsystem dependency edges."""
        seen = set()
        for fn_key, finfo in self.functions.items():
            src = finfo['subsystem']
            for callee in finfo['calls']:
                if callee in self.functions:
                    dst = self.functions[callee]['subsystem']
                    if dst != src:
                        key = (src, dst)
                        if key not in seen:
                            seen.add(key)
                            self.cross_edges.append({'from': src, 'to': dst})

    # ── Query methods ─────────────────────────────────────────────────────

    def query_overview(self):
        return {
            'project': self.project_name,
            'root': self.root,
            'total_files': len(self.files),
            'total_functions': len(self.functions),
            'total_classes': len(self.classes),
            'total_lines': sum(f['lines'] for f in self.files.values()),
            'total_sections': len(self.sections),
            'total_subsystems': len(self.subsystems),
            'total_pipelines': len(self.pipelines),
            'total_constants': len(self.constants),
            'total_cross_edges': len(self.cross_edges),
            'languages': self.languages_found,
            'subsystems': {k: {'files': v['file_count'], 'functions': v['functions'],
                              'lines': v['lines'], 'languages': v['languages']}
                         for k, v in self.subsystems.items()},
            'pipeline_names': sorted(self.pipelines.keys()),
            'build_time_s': round(getattr(self, 'build_time', 0), 2),
        }

    def query_function(self, name: str):
        # Exact key
        if name in self.functions:
            return self._fmt_fn(name, self.functions[name])
        # Bare name
        matches = [(k, f) for k, f in self.functions.items() if f['name'] == name]
        if len(matches) == 1:
            return self._fmt_fn(*matches[0])
        if matches:
            return {'ambiguous': True, 'matches': [
                {'key': k, 'file': f['file'], 'line': f['line_start'], 'language': f['language']}
                for k, f in matches[:20]
            ]}
        # Fuzzy
        q = name.lower()
        fuzzy = [(k, f) for k, f in self.functions.items() if q in f['name'].lower()][:15]
        if fuzzy:
            return {'not_found': name, 'similar': [
                {'name': f['name'], 'file': f['file'], 'line': f['line_start']} for _, f in fuzzy
            ]}
        return {'error': f'Function not found: {name}'}

    def _fmt_fn(self, key, fn):
        return {
            'key': key, 'name': fn['name'], 'file': fn['file'],
            'line_start': fn['line_start'], 'line_end': fn['line_end'],
            'params': fn['params'], 'returns': fn['returns'], 'doc': fn['doc'],
            'section': fn['section'], 'subsystem': fn['subsystem'],
            'language': fn['language'],
            'calls': fn['calls'][:30], 'callers': fn['callers'][:30],
            'call_count': len(fn['calls']), 'caller_count': len(fn['callers']),
        }

    def query_callers(self, name: str):
        fn = self._find_fn(name)
        if not fn:
            return {'error': f'Function not found: {name}'}
        key, finfo = fn
        return {
            'function': finfo['name'], 'file': finfo['file'],
            'callers': [{'name': c, 'file': self.functions.get(c, {}).get('file', '?')}
                       for c in finfo['callers'][:50]],
            'calls': [{'name': c, 'file': self.functions.get(c, {}).get('file', '?')}
                     for c in finfo['calls'][:50]],
        }

    def query_search(self, query: str):
        q = query.lower()
        results = {'functions': [], 'classes': [], 'sections': [], 'constants': []}

        for key, fn in self.functions.items():
            if q in fn['name'].lower() or q in fn.get('doc', '').lower():
                results['functions'].append({
                    'name': fn['name'], 'file': fn['file'], 'line': fn['line_start'],
                    'language': fn['language'], 'doc': fn['doc'][:80],
                })
                if len(results['functions']) >= 25:
                    break

        for key, cls in self.classes.items():
            if q in cls['name'].lower():
                results['classes'].append({'name': cls['name'], 'file': cls['file'], 'line': cls['line']})
                if len(results['classes']) >= 15:
                    break

        for key, sec in self.sections.items():
            if q in sec['name'].lower():
                results['sections'].append({'key': key, 'name': sec['name'], 'fn_count': len(sec['functions'])})
                if len(results['sections']) >= 10:
                    break

        for name, c in self.constants.items():
            if q in name.lower():
                results['constants'].append({'name': name, 'value': c['value'], 'file': c['file']})
                if len(results['constants']) >= 10:
                    break

        total = sum(len(v) for v in results.values())
        return {'query': query, 'total_matches': total, **results}

    def query_file(self, path: str):
        if path in self.files:
            return self._fmt_file(path)
        for fp in self.files:
            if path in fp:
                return self._fmt_file(fp)
        return {'error': f'File not found: {path}'}

    def _fmt_file(self, rel):
        f = self.files[rel]
        return {
            'path': rel, 'lines': f['lines'], 'subsystem': f['subsystem'],
            'language': f['language'],
            'functions': [{'name': self.functions.get(k, {}).get('name', k),
                          'line': self.functions.get(k, {}).get('line_start', 0)}
                         for k in f['functions']],
            'classes': [{'name': self.classes.get(k, {}).get('name', k),
                        'line': self.classes.get(k, {}).get('line', 0)}
                       for k in f['classes']],
            'sections': f['sections'],
        }

    def query_read(self, name: str, start: int = 0, end: int = 0):
        # Try as function
        fn = self._find_fn(name)
        if fn:
            key, finfo = fn
            lines = self._read_file(os.path.join(self.root, finfo['file']))
            s = finfo['line_start'] - 1
            e = finfo['line_end'] or (s + 50)
            return {
                'function': finfo['name'], 'file': finfo['file'],
                'line_start': finfo['line_start'], 'line_end': finfo['line_end'],
                'source': ''.join(lines[s:e]),
            }
        # Try as file
        for fp, finfo in self.files.items():
            if name in fp:
                lines = self._read_file(finfo['abs_path'])
                s = max(0, start - 1) if start else 0
                e = end if end else min(s + 100, len(lines))
                return {'file': fp, 'line_start': s + 1, 'line_end': e,
                        'source': ''.join(lines[s:e])}
        return {'error': f'Not found: {name}'}

    def query_subsystem(self, name: str):
        if name not in self.subsystems:
            matches = [s for s in self.subsystems if name.lower() in s.lower()]
            if matches:
                name = matches[0]
            else:
                return {'error': f'Subsystem not found: {name}',
                        'available': sorted(self.subsystems.keys())}
        sub = self.subsystems[name]
        fns = [(k, f, len(f['callers']) + len(f['calls']))
               for k, f in self.functions.items() if f['subsystem'] == name]
        fns.sort(key=lambda x: x[2], reverse=True)
        return {
            'name': name, 'files': sub['file_count'], 'functions': sub['functions'],
            'lines': sub['lines'], 'languages': sub['languages'],
            'file_list': sub['files'],
            'top_functions': [{'name': f['name'], 'file': f['file'], 'connectivity': c}
                            for _, f, c in fns[:20]],
        }

    def query_pipeline(self, name: str):
        if name in self.pipelines:
            return {'pipeline': name, 'stages': self.pipelines[name]}
        matches = {k: v for k, v in self.pipelines.items() if name.lower() in k}
        if matches:
            return {'pipelines': matches}
        return {'error': f'Pipeline not found: {name}', 'available': sorted(self.pipelines.keys())}

    def query_dataflow(self, name: str):
        fn = self._find_fn(name)
        if not fn:
            return {'error': f'Function not found: {name}'}
        key, finfo = fn
        return {
            'function': finfo['name'], 'file': finfo['file'], 'subsystem': finfo['subsystem'],
            'upstream': [{'name': self.functions.get(c, {}).get('name', c),
                         'file': self.functions.get(c, {}).get('file', '?')}
                        for c in finfo['callers'][:15]],
            'downstream': [{'name': c, 'file': self.functions.get(c, {}).get('file', '?')}
                          for c in finfo['calls'][:15]],
        }

    def query_trace(self, name: str, depth: int = 5):
        fn = self._find_fn(name)
        if not fn:
            return {'error': f'Function not found: {name}'}
        chain = []
        visited = set()
        self._dfs(fn[0], 0, depth, chain, visited)
        return {'root': fn[1]['name'], 'depth': depth, 'chain': chain}

    def _dfs(self, key, d, max_d, chain, visited):
        if d > max_d or key in visited:
            return
        visited.add(key)
        fn = self.functions.get(key, {})
        chain.append({'depth': d, 'function': fn.get('name', key),
                     'file': fn.get('file', '?'), 'calls': fn.get('calls', [])[:10]})
        for c in fn.get('calls', [])[:5]:
            if c in self.functions:
                self._dfs(c, d + 1, max_d, chain, visited)

    def query_hotspots(self, n: int = 20):
        scored = [(k, f, len(f['callers']) + len(f['calls']))
                  for k, f in self.functions.items() if len(f['callers']) + len(f['calls']) > 0]
        scored.sort(key=lambda x: x[2], reverse=True)
        return {'hotspots': [
            {'name': f['name'], 'file': f['file'], 'line': f['line_start'],
             'callers': len(f['callers']), 'calls': len(f['calls']),
             'total': s, 'subsystem': f['subsystem'], 'language': f['language']}
            for _, f, s in scored[:n]
        ]}

    def query_architecture(self):
        edge_counts = {}
        for e in self.cross_edges:
            k = f"{e['from']} -> {e['to']}"
            edge_counts[k] = edge_counts.get(k, 0) + 1
        top = sorted(edge_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        return {
            'subsystems': {k: {'files': v['file_count'], 'functions': v['functions'],
                              'lines': v['lines'], 'languages': v['languages']}
                         for k, v in self.subsystems.items()},
            'cross_edges': len(self.cross_edges),
            'top_dependencies': [{'path': k, 'count': v} for k, v in top],
        }

    def _find_fn(self, name):
        if name in self.functions:
            return (name, self.functions[name])
        for k, f in self.functions.items():
            if f['name'] == name:
                return (k, f)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool definitions
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        'name': 'ezgraph_overview',
        'description': 'Project overview: files, functions, classes, languages, subsystems, pipelines. Start here.',
        'inputSchema': {'type': 'object', 'properties': {}, 'required': []},
    },
    {
        'name': 'ezgraph_function',
        'description': 'Look up any function by name. Returns signature, location, callers, callees, language.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name (exact or partial)'},
        }, 'required': ['name']},
    },
    {
        'name': 'ezgraph_callers',
        'description': 'Call graph for a function: who calls it and what it calls.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name'},
        }, 'required': ['name']},
    },
    {
        'name': 'ezgraph_search',
        'description': 'Search everything: functions, classes, sections, constants.',
        'inputSchema': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Search query'},
        }, 'required': ['query']},
    },
    {
        'name': 'ezgraph_file',
        'description': 'Get info about a file: functions, classes, sections, language.',
        'inputSchema': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'File path (relative or partial)'},
        }, 'required': ['path']},
    },
    {
        'name': 'ezgraph_read',
        'description': 'Read source code of a function (by name) or file region (by path + line range).',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name or file path'},
            'start': {'type': 'integer', 'description': 'Start line (for file reads)'},
            'end': {'type': 'integer', 'description': 'End line (for file reads)'},
        }, 'required': ['name']},
    },
    {
        'name': 'ezgraph_subsystem',
        'description': 'Deep dive into a subsystem: files, top functions, languages.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Subsystem name'},
        }, 'required': ['name']},
    },
    {
        'name': 'ezgraph_pipeline',
        'description': 'Trace a named pipeline or pattern (parse, validate, handle, compile, etc.).',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Pipeline name'},
        }, 'required': ['name']},
    },
    {
        'name': 'ezgraph_dataflow',
        'description': 'Data flow: upstream callers and downstream callees for a function.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name'},
        }, 'required': ['name']},
    },
    {
        'name': 'ezgraph_trace',
        'description': 'Depth-limited call chain trace from a function.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Starting function'},
            'depth': {'type': 'integer', 'description': 'Max depth (default 5)'},
        }, 'required': ['name']},
    },
    {
        'name': 'ezgraph_hotspots',
        'description': 'Most connected functions (highest fan-in + fan-out).',
        'inputSchema': {'type': 'object', 'properties': {
            'n': {'type': 'integer', 'description': 'Number of hotspots (default 20)'},
        }, 'required': []},
    },
    {
        'name': 'ezgraph_architecture',
        'description': 'Architecture: subsystems, cross-subsystem dependencies, language mix.',
        'inputSchema': {'type': 'object', 'properties': {}, 'required': []},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Tool dispatch
# ─────────────────────────────────────────────────────────────────────────────

def handle_tool_call(graph: EZgraph, watcher: GraphWatcher,
                     tool_name: str, args: dict) -> Any:
    if watcher.is_stale():
        sys.stderr.write('[ezgraph] Sources changed, reindexing...\n')
        sys.stderr.flush()
        graph.__init__(graph.root)
        graph.build()
        watcher.snapshot()
        sys.stderr.write('[ezgraph] Reindex complete.\n')
        sys.stderr.flush()

    dispatch = {
        'ezgraph_overview': lambda: graph.query_overview(),
        'ezgraph_function': lambda: graph.query_function(args.get('name', '')),
        'ezgraph_callers': lambda: graph.query_callers(args.get('name', '')),
        'ezgraph_search': lambda: graph.query_search(args.get('query', '')),
        'ezgraph_file': lambda: graph.query_file(args.get('path', '')),
        'ezgraph_read': lambda: graph.query_read(args.get('name', ''), args.get('start', 0), args.get('end', 0)),
        'ezgraph_subsystem': lambda: graph.query_subsystem(args.get('name', '')),
        'ezgraph_pipeline': lambda: graph.query_pipeline(args.get('name', '')),
        'ezgraph_dataflow': lambda: graph.query_dataflow(args.get('name', '')),
        'ezgraph_trace': lambda: graph.query_trace(args.get('name', ''), args.get('depth', 5)),
        'ezgraph_hotspots': lambda: graph.query_hotspots(args.get('n', 20)),
        'ezgraph_architecture': lambda: graph.query_architecture(),
    }

    handler = dispatch.get(tool_name)
    if handler:
        return handler()
    return {'error': f'Unknown tool: {tool_name}'}


# ─────────────────────────────────────────────────────────────────────────────
# MCP Server
# ─────────────────────────────────────────────────────────────────────────────

def send(msg):
    sys.stdout.write(json.dumps(msg) + '\n')
    sys.stdout.flush()


def run_mcp_server(graph: EZgraph, watcher: GraphWatcher):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get('method', '')
        msg_id = msg.get('id')
        params = msg.get('params', {})

        if method == 'initialize':
            send({
                'jsonrpc': '2.0', 'id': msg_id,
                'result': {
                    'protocolVersion': '2024-11-05',
                    'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'ezgraph', 'version': '0.1.0'},
                },
            })
        elif method == 'notifications/initialized':
            pass
        elif method == 'tools/list':
            send({'jsonrpc': '2.0', 'id': msg_id, 'result': {'tools': TOOLS}})
        elif method == 'tools/call':
            tn = params.get('name', '')
            ta = params.get('arguments', {})
            try:
                result = handle_tool_call(graph, watcher, tn, ta)
                send({
                    'jsonrpc': '2.0', 'id': msg_id,
                    'result': {'content': [{'type': 'text', 'text': json.dumps(result, indent=2)}]},
                })
            except Exception as e:
                send({
                    'jsonrpc': '2.0', 'id': msg_id,
                    'result': {'content': [{'type': 'text', 'text': json.dumps({'error': str(e)})}]},
                    'isError': True,
                })
        elif method == 'ping':
            send({'jsonrpc': '2.0', 'id': msg_id, 'result': {}})
        else:
            if msg_id is not None:
                send({
                    'jsonrpc': '2.0', 'id': msg_id,
                    'error': {'code': -32601, 'message': f'Method not found: {method}'},
                })


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='EZgraph — instant codebase knowledge graph MCP server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  ezgraph                     # Index current directory, run MCP server
  ezgraph /path/to/project    # Index specific project
  ezgraph --dump              # Print graph JSON and exit
  ezgraph --query main        # Quick function lookup and exit

Supported: Python, Rust, Go, TypeScript, JavaScript, Java, C/C++, C#,
           Ruby, PHP, Swift, Kotlin, Scala, Zig, Lua, Elixir, Dart, Vortex
'''
    )
    parser.add_argument('directory', nargs='?', default='.', help='Project root directory')
    parser.add_argument('--dump', action='store_true', help='Dump graph JSON and exit')
    parser.add_argument('--query', default=None, help='Quick function query and exit')
    parser.add_argument('--stats', action='store_true', help='Print stats and exit')
    args = parser.parse_args()

    root = os.path.abspath(args.directory)
    if not os.path.isdir(root):
        print(f'Error: {root} is not a directory', file=sys.stderr)
        sys.exit(1)

    sys.stderr.write(f'[ezgraph] Indexing {root} ...\n')
    sys.stderr.flush()

    graph = EZgraph(root)
    graph.build()

    # Set up watcher
    watcher = GraphWatcher()
    watcher.track_dir(root, list(LANGUAGES.keys()))
    watcher.track_sentinel(root)
    watcher.snapshot()

    sys.stderr.write(
        f'[ezgraph] {len(graph.functions)} functions, '
        f'{len(graph.files)} files, '
        f'{len(graph.classes)} classes, '
        f'{len(graph.subsystems)} subsystems '
        f'in {graph.build_time:.1f}s\n'
    )
    langs = ', '.join(f'{k}({v})' for k, v in sorted(graph.languages_found.items(), key=lambda x: -x[1]))
    sys.stderr.write(f'[ezgraph] Languages: {langs}\n')
    sys.stderr.flush()

    if args.stats:
        print(json.dumps(graph.query_overview(), indent=2))
        return

    if args.dump:
        print(json.dumps({
            'overview': graph.query_overview(),
            'functions': len(graph.functions),
            'files': len(graph.files),
        }, indent=2))
        return

    if args.query:
        result = graph.query_function(args.query)
        if 'error' in result:
            result = graph.query_search(args.query)
        print(json.dumps(result, indent=2))
        return

    run_mcp_server(graph, watcher)


if __name__ == '__main__':
    main()
