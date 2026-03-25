#!/usr/bin/env python3
"""
LiLBrain — Instant codebase knowledge graph MCP server.

Drop into any project. Auto-detects languages. Indexes everything.
One server, any codebase, 20 tools.

Usage:
    lilbrain                          # index current directory
    lilbrain /path/to/project         # index specific project
    lilbrain --port 8080              # HTTP mode (coming soon)

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
import math
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
# LiLBrain — the unified knowledge graph
# ─────────────────────────────────────────────────────────────────────────────

class LiLBrain:
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
        self._compute_complexity()
        self._build_semantic_index()
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

    def _group_by(self, items, field):
        groups = {}
        for item in items:
            k = item.get(field, '?')
            groups[k] = groups.get(k, 0) + 1
        return dict(sorted(groups.items(), key=lambda x: -x[1]))

    # ── Complexity analysis ──────────────────────────────────────────

    _BRANCH_RE = re.compile(
        r'\b(if|elif|else\s+if|for|while|case|catch|except|match|guard)\b|&&|\|\||\?\s*\S')

    def _compute_complexity(self):
        """Compute cyclomatic + cognitive complexity for every function."""
        for key, fn in self.functions.items():
            lines = self._read_file(os.path.join(self.root, fn['file']))
            s = fn['line_start'] - 1
            e = fn['line_end'] or (s + 50)
            body = '\n'.join(lines[s:min(e, len(lines))])
            branches = len(self._BRANCH_RE.findall(body))
            nesting = self._max_nesting(lines[s:min(e, len(lines))])
            fn['complexity'] = branches + 1
            fn['cognitive_complexity'] = branches + nesting
            fn['lines_of_code'] = min(e, len(lines)) - s

    def _max_nesting(self, lines):
        max_depth = 0
        base = None
        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                continue
            indent = len(stripped) - len(stripped.lstrip())
            if base is None:
                base = indent
            depth = max(0, (indent - base) // 4)
            max_depth = max(max_depth, depth)
        return max_depth

    # ── Semantic search index (TF-IDF, zero deps) ───────────────────

    _CAMEL_RE = re.compile(r'[a-z]+|[A-Z][a-z]*|[A-Z]+(?=[A-Z]|$)|[0-9]+')

    def _build_semantic_index(self):
        """Build TF-IDF index for semantic search."""
        self._semantic_docs = {}
        df = {}
        N = max(len(self.functions), 1)

        for key, fn in self.functions.items():
            tokens = self._tokenize_fn(fn)
            self._semantic_docs[key] = tokens
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1

        self._idf = {t: math.log(N / (1 + c)) for t, c in df.items()}

    def _tokenize_fn(self, fn):
        parts = self._CAMEL_RE.findall(fn['name'])
        parts += fn['name'].split('_')
        parts += re.findall(r'\w+', fn.get('params', ''))
        parts += re.findall(r'\w+', fn.get('doc', ''))
        return [t.lower() for t in parts if len(t) > 1]

    # ── Tier 1: Impact analysis ──────────────────────────────────────

    def query_impact(self, name, depth=5):
        """BFS through reverse call graph to assess blast radius."""
        fn = self._find_fn(name)
        if not fn:
            return {'error': f'Function not found: {name}'}
        key, finfo = fn

        visited = set()
        queue = [(key, 0)]
        impacts = []
        subs_affected = set()

        while queue:
            k, d = queue.pop(0)
            if k in visited or d > depth:
                continue
            visited.add(k)
            f = self.functions.get(k)
            if not f:
                continue
            subs_affected.add(f['subsystem'])
            impacts.append({
                'function': f['name'], 'file': f['file'],
                'line': f['line_start'], 'depth': d,
                'subsystem': f['subsystem'], 'language': f['language'],
            })
            for caller in f.get('callers', []):
                if caller not in visited:
                    queue.append((caller, d + 1))

        n = len(impacts)
        risk = 'LOW' if n < 5 else 'MEDIUM' if n < 20 else 'HIGH' if n < 50 else 'CRITICAL'
        return {
            'root': finfo['name'], 'total_affected': n,
            'subsystems_affected': sorted(subs_affected),
            'risk': risk,
            'depth_reached': max((i['depth'] for i in impacts), default=0),
            'impacts': impacts[:100],
        }

    # ── Tier 1: Auto architecture diagrams ───────────────────────────

    def query_diagram(self, target='architecture', fmt='mermaid'):
        """Generate Mermaid or D2 diagram from graph data."""
        if fmt == 'd2':
            return self._diagram_d2(target)
        return self._diagram_mermaid(target)

    def _diagram_mermaid(self, target):
        if target == 'architecture':
            lines = ['graph TD']
            for name, sub in self.subsystems.items():
                safe = name.replace('"', "'")
                label = f"{safe}\\n{sub['functions']} fns | {sub['lines']} LOC"
                lines.append(f'    {name}["{label}"]')
            edge_counts = {}
            for e in self.cross_edges:
                k = (e['from'], e['to'])
                edge_counts[k] = edge_counts.get(k, 0) + 1
            for (src, dst), count in sorted(edge_counts.items(), key=lambda x: -x[1])[:40]:
                lines.append(f'    {src} -->|{count}| {dst}')
            return {'format': 'mermaid', 'target': 'architecture', 'diagram': '\n'.join(lines)}

        if target in self.subsystems:
            lines = ['graph TD']
            fns = [(k, f) for k, f in self.functions.items() if f['subsystem'] == target]
            fns.sort(key=lambda x: len(x[1].get('callers', [])), reverse=True)
            shown = set()
            for key, fn in fns[:40]:
                safe = fn['name'].replace('"', "'")
                lines.append(f'    {fn["name"]}["{safe}"]')
                shown.add(fn['name'])
            for key, fn in fns[:40]:
                for callee in fn.get('calls', [])[:5]:
                    if callee in shown:
                        lines.append(f'    {fn["name"]} --> {callee}')
            return {'format': 'mermaid', 'target': target, 'diagram': '\n'.join(lines)}

        fn = self._find_fn(target)
        if fn:
            key, finfo = fn
            name = finfo['name']
            lines = ['graph LR', f'    {name}["{name}"]:::root']
            for caller in finfo.get('callers', [])[:15]:
                cn = self.functions.get(caller, {}).get('name', caller)
                lines.append(f'    {cn} --> {name}')
            for callee in finfo.get('calls', [])[:15]:
                lines.append(f'    {name} --> {callee}')
            lines.append('    classDef root fill:#f96,stroke:#333')
            return {'format': 'mermaid', 'target': target, 'diagram': '\n'.join(lines)}

        return {'error': f'Target not found: {target}. Use "architecture", a subsystem name, or a function name.'}

    def _diagram_d2(self, target):
        if target == 'architecture':
            lines = []
            for name, sub in self.subsystems.items():
                lines.append(f'{name}: "{name} ({sub["functions"]} fns, {sub["lines"]} LOC)"')
            edge_counts = {}
            for e in self.cross_edges:
                k = (e['from'], e['to'])
                edge_counts[k] = edge_counts.get(k, 0) + 1
            for (src, dst), count in sorted(edge_counts.items(), key=lambda x: -x[1])[:40]:
                lines.append(f'{src} -> {dst}: {count}')
            return {'format': 'd2', 'target': 'architecture', 'diagram': '\n'.join(lines)}

        fn = self._find_fn(target)
        if fn:
            key, finfo = fn
            lines = [f'{finfo["name"]}.style.fill: "#f96"']
            for caller in finfo.get('callers', [])[:15]:
                cn = self.functions.get(caller, {}).get('name', caller)
                lines.append(f'{cn} -> {finfo["name"]}')
            for callee in finfo.get('calls', [])[:15]:
                lines.append(f'{finfo["name"]} -> {callee}')
            return {'format': 'd2', 'target': target, 'diagram': '\n'.join(lines)}

        return {'error': f'Target not found: {target}'}

    # ── Tier 1: Dead code detection ──────────────────────────────────

    def query_deadcode(self):
        """Find functions with zero callers (potential dead code)."""
        entry_names = {'main', '__init__', '__main__', 'setup', 'teardown',
                       'run', 'start', 'app', 'create_app', 'configure'}
        entry_prefixes = ('test_', 'Test', 'handle_', 'on_', '__', 'route_',
                          'api_', 'cmd_', 'do_', 'get_', 'set_', 'is_')

        dead = []
        for key, fn in self.functions.items():
            if fn['callers']:
                continue
            name = fn['name']
            if name in entry_names or any(name.startswith(p) for p in entry_prefixes):
                continue
            dead.append({
                'name': name, 'file': fn['file'], 'line': fn['line_start'],
                'subsystem': fn['subsystem'], 'language': fn['language'],
                'complexity': fn.get('complexity', 0),
                'lines_of_code': fn.get('lines_of_code', 0),
            })

        dead.sort(key=lambda x: x.get('lines_of_code', 0), reverse=True)
        total_dead_loc = sum(d.get('lines_of_code', 0) for d in dead)
        total_loc = sum(f['lines'] for f in self.files.values())

        return {
            'total_dead': len(dead),
            'total_functions': len(self.functions),
            'dead_percentage': round(100 * len(dead) / max(len(self.functions), 1), 1),
            'dead_loc': total_dead_loc,
            'total_loc': total_loc,
            'dead_loc_percentage': round(100 * total_dead_loc / max(total_loc, 1), 1),
            'by_subsystem': self._group_by(dead, 'subsystem'),
            'functions': dead[:50],
        }

    # ── Tier 1: Clone detection ──────────────────────────────────────

    _NOISE_TOKENS = frozenset({
        'self', 'return', 'true', 'false', 'none', 'null', 'let', 'var',
        'const', 'int', 'str', 'string', 'void', 'fn', 'def', 'func',
        'function', 'if', 'else', 'for', 'while', 'class', 'struct',
        'pub', 'mut', 'async', 'await', 'import', 'from', 'this',
    })

    def query_clones(self, threshold=0.7, min_lines=5):
        """Detect near-duplicate functions using token Jaccard similarity."""
        token_sets = {}
        for key, fn in self.functions.items():
            loc = fn.get('lines_of_code', 0)
            if loc < min_lines:
                continue
            lines = self._read_file(os.path.join(self.root, fn['file']))
            s = fn['line_start'] - 1
            e = fn['line_end'] or (s + 50)
            body = '\n'.join(lines[s:min(e, len(lines))])
            tokens = set(re.findall(r'\b\w{2,}\b', body.lower())) - self._NOISE_TOKENS
            if len(tokens) >= 3:
                token_sets[key] = tokens

        keys = list(token_sets.keys())
        cap = min(len(keys), 500)  # O(n²) cap for performance
        clones = []

        for i in range(cap):
            for j in range(i + 1, cap):
                a, b = token_sets[keys[i]], token_sets[keys[j]]
                intersection = len(a & b)
                union = len(a | b)
                if union == 0:
                    continue
                sim = intersection / union
                if sim >= threshold:
                    fa, fb = self.functions[keys[i]], self.functions[keys[j]]
                    if fa['name'] == fb['name']:
                        continue  # same name in different files isn't a "clone"
                    clones.append({
                        'function_a': fa['name'], 'file_a': fa['file'], 'line_a': fa['line_start'],
                        'function_b': fb['name'], 'file_b': fb['file'], 'line_b': fb['line_start'],
                        'similarity': round(sim, 3),
                        'shared_tokens': intersection,
                    })

        clones.sort(key=lambda x: x['similarity'], reverse=True)
        return {
            'total_clones': len(clones),
            'threshold': threshold,
            'functions_analyzed': len(token_sets),
            'clones': clones[:30],
        }

    # ── Tier 2: Complexity + velocity ────────────────────────────────

    def query_complexity(self, name=None, n=20):
        """Cyclomatic + cognitive complexity. Per-function or top-N ranking."""
        if name:
            fn = self._find_fn(name)
            if not fn:
                return {'error': f'Function not found: {name}'}
            key, finfo = fn
            c = finfo.get('complexity', 0)
            risk = 'LOW' if c < 5 else 'MEDIUM' if c < 10 else 'HIGH' if c < 20 else 'CRITICAL'
            return {
                'name': finfo['name'], 'file': finfo['file'],
                'line': finfo['line_start'],
                'cyclomatic': c,
                'cognitive': finfo.get('cognitive_complexity', 0),
                'lines_of_code': finfo.get('lines_of_code', 0),
                'callers': len(finfo['callers']),
                'calls': len(finfo['calls']),
                'risk': risk,
            }

        ranked = [(k, f) for k, f in self.functions.items() if f.get('complexity', 0) > 1]
        ranked.sort(key=lambda x: x[1].get('complexity', 0), reverse=True)

        complexities = [f.get('complexity', 0) for f in self.functions.values()]
        avg = sum(complexities) / max(len(complexities), 1)

        return {
            'total_functions': len(self.functions),
            'average_complexity': round(avg, 1),
            'high_complexity_count': sum(1 for c in complexities if c >= 10),
            'critical_complexity_count': sum(1 for c in complexities if c >= 20),
            'top_complex': [{
                'name': f['name'], 'file': f['file'], 'line': f['line_start'],
                'cyclomatic': f.get('complexity', 0),
                'cognitive': f.get('cognitive_complexity', 0),
                'lines_of_code': f.get('lines_of_code', 0),
                'subsystem': f['subsystem'],
            } for _, f in ranked[:n]],
        }

    def query_complexity_velocity(self, n_commits=10):
        """Track complexity changes over recent git history."""
        try:
            r = subprocess.run(
                ['git', '-C', self.root, 'log', f'-{n_commits}',
                 '--format=%H|%ci|%s', '--name-only'],
                capture_output=True, text=True, timeout=10)
        except Exception:
            return {'error': 'Not a git repository or git not available'}
        if r.returncode != 0:
            return {'error': 'Not a git repository'}

        commits = []
        current = None
        for line in r.stdout.strip().split('\n'):
            if not line.strip():
                current = None
                continue
            if '|' in line and len(line.split('|')) >= 3:
                parts = line.split('|', 2)
                current = {'hash': parts[0][:8], 'date': parts[1].strip()[:10],
                           'message': parts[2][:60], 'files': []}
                commits.append(current)
            elif current is not None and line.strip():
                current['files'].append(line.strip())

        history = []
        for c in commits[:n_commits]:
            changed_fns = 0
            total_complexity = 0
            for fp in c['files']:
                for fn_key, fn in self.functions.items():
                    if fn['file'] == fp:
                        changed_fns += 1
                        total_complexity += fn.get('complexity', 0)
            history.append({
                'hash': c['hash'], 'date': c['date'], 'message': c['message'],
                'files_changed': len(c['files']),
                'functions_in_changed_files': changed_fns,
                'complexity_in_changed_files': total_complexity,
            })

        return {'commits': len(history), 'history': history}

    # ── Tier 2: Semantic search ──────────────────────────────────────

    def query_semantic(self, query, n=20):
        """Semantic search using TF-IDF similarity. Zero dependencies."""
        if not hasattr(self, '_semantic_docs') or not self._semantic_docs:
            return {'error': 'Semantic index not built'}

        expanded = []
        for t in re.findall(r'\w{2,}', query):
            expanded.extend(self._CAMEL_RE.findall(t))
            expanded.append(t)
        query_tokens = list(set(t.lower() for t in expanded if len(t) > 1))

        scores = []
        for key, doc_tokens in self._semantic_docs.items():
            doc_set = set(doc_tokens)
            score = sum(self._idf.get(t, 0) for t in query_tokens if t in doc_set)
            if score > 0:
                fn = self.functions[key]
                scores.append((key, fn, score))

        scores.sort(key=lambda x: x[2], reverse=True)
        return {
            'query': query, 'tokens': query_tokens,
            'results': [{
                'name': fn['name'], 'file': fn['file'], 'line': fn['line_start'],
                'subsystem': fn['subsystem'], 'language': fn['language'],
                'doc': fn.get('doc', ''), 'score': round(s, 3),
            } for _, fn, s in scores[:n]],
        }

    # ── Tier 2: Multi-repo federation ────────────────────────────────

    def query_federation(self, repos, search_query):
        """Federated search across multiple repositories."""
        results = {}
        all_fns = 0
        all_files = 0
        for repo_path in repos:
            if not os.path.isdir(repo_path):
                continue
            name = os.path.basename(os.path.abspath(repo_path))
            if repo_path == self.root or name == self.project_name:
                r = self.query_search(search_query)
                results[name] = r
                all_fns += len(self.functions)
                all_files += len(self.files)
            else:
                try:
                    g = LiLBrain(repo_path)
                    g.build()
                    r = g.query_search(search_query)
                    if r.get('total_matches', 0) > 0:
                        results[name] = r
                    all_fns += len(g.functions)
                    all_files += len(g.files)
                except Exception as e:
                    results[name] = {'error': str(e)}

        return {
            'repos_searched': len(repos),
            'total_functions_across_repos': all_fns,
            'total_files_across_repos': all_files,
            'results': results,
        }

    def query_federation_overview(self, repos):
        """Overview of multiple repositories."""
        overviews = {}
        for repo_path in repos:
            if not os.path.isdir(repo_path):
                continue
            name = os.path.basename(os.path.abspath(repo_path))
            if repo_path == self.root or name == self.project_name:
                overviews[name] = self.query_overview()
            else:
                try:
                    g = LiLBrain(repo_path)
                    g.build()
                    overviews[name] = g.query_overview()
                except Exception as e:
                    overviews[name] = {'error': str(e)}

        return {
            'repos': len(overviews),
            'total_functions': sum(o.get('total_functions', 0) for o in overviews.values() if isinstance(o, dict)),
            'total_files': sum(o.get('total_files', 0) for o in overviews.values() if isinstance(o, dict)),
            'overviews': overviews,
        }

    # ── Tier 3: Natural language queries ─────────────────────────────

    def query_ask(self, question):
        """Answer natural language questions about the codebase."""
        q = question.lower().strip()

        # Dead code
        if any(w in q for w in ['dead code', 'unused', 'unreachable', 'never called', 'orphan']):
            return {'interpreted_as': 'dead code detection', **self.query_deadcode()}

        # Complexity
        if any(w in q for w in ['complex', 'complicated', 'messy', 'spaghetti', 'worst code']):
            return {'interpreted_as': 'complexity ranking', **self.query_complexity()}

        # Clones
        if any(w in q for w in ['duplicate', 'clone', 'copy-paste', 'similar function', 'redundant']):
            return {'interpreted_as': 'clone detection', **self.query_clones()}

        # Architecture
        if any(w in q for w in ['architecture', 'structure', 'overview', 'how is', 'organized', 'layout']):
            return {'interpreted_as': 'architecture overview', **self.query_architecture()}

        # Hotspots
        if any(w in q for w in ['hotspot', 'most called', 'most used', 'popular', 'critical path', 'bottleneck']):
            return {'interpreted_as': 'hotspot analysis', **self.query_hotspots()}

        # Diagram
        if any(w in q for w in ['diagram', 'visual', 'draw', 'map', 'picture', 'chart']):
            m = re.search(r'(?:of|for)\s+["\']?(\w+)', q)
            target = m.group(1) if m else 'architecture'
            return {'interpreted_as': f'diagram of {target}', **self.query_diagram(target)}

        # Who/what calls X
        m = re.search(r'(?:who|what)\s+calls?\s+["\']?(\w+)', q)
        if m:
            return {'interpreted_as': f'callers of {m.group(1)}', **self.query_callers(m.group(1))}

        # Functions that call X
        m = re.search(r'(?:functions?|methods?|code)\s+(?:that\s+)?calls?\s+["\']?(\w+)', q)
        if m:
            return {'interpreted_as': f'callers of {m.group(1)}', **self.query_callers(m.group(1))}

        # Impact of X
        m = re.search(r'(?:impact|blast|affect|risk|break|change|modify)\s+(?:of\s+)?(?:changing\s+)?["\']?(\w+)', q)
        if m:
            return {'interpreted_as': f'impact of {m.group(1)}', **self.query_impact(m.group(1))}

        # Functions in subsystem X
        m = re.search(r'(?:functions?|methods?|code)\s+in\s+["\']?(\w+)', q)
        if m and m.group(1) in self.subsystems:
            return {'interpreted_as': f'subsystem {m.group(1)}', **self.query_subsystem(m.group(1))}

        # What does X do
        m = re.search(r'(?:what\s+does|explain|describe|about)\s+["\']?(\w+)', q)
        if m:
            fn = self._find_fn(m.group(1))
            if fn:
                return {'interpreted_as': f'function lookup: {m.group(1)}', **self._fmt_fn(*fn)}

        # Fallback: semantic search
        return {'interpreted_as': 'semantic search', **self.query_semantic(question)}

    # ── Tier 3: Git diff + time travel ───────────────────────────────

    def query_diff(self, base='HEAD~1', head='HEAD'):
        """Graph diff between two git refs — changed functions + blast radius."""
        try:
            r = subprocess.run(
                ['git', '-C', self.root, 'diff', '--name-status', f'{base}..{head}'],
                capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                return {'error': f'git diff failed: {r.stderr.strip()}'}
        except Exception as e:
            return {'error': f'git not available: {e}'}

        changed_files = {}
        for line in r.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                changed_files[parts[-1]] = parts[0]

        # Parse diff hunks for line ranges
        r2 = subprocess.run(
            ['git', '-C', self.root, 'diff', '-U0', '--no-color', f'{base}..{head}'],
            capture_output=True, text=True, timeout=10)

        changed_ranges = {}
        current_file = None
        for line in r2.stdout.split('\n'):
            if line.startswith('+++ b/'):
                current_file = line[6:]
            elif line.startswith('@@') and current_file:
                m = re.search(r'\+(\d+)(?:,(\d+))?', line)
                if m:
                    start = int(m.group(1))
                    count = int(m.group(2)) if m.group(2) else 1
                    changed_ranges.setdefault(current_file, []).append(
                        (start, start + count))

        # Map changed ranges to functions
        changed_fns = []
        for fn_key, fn in self.functions.items():
            fp = fn['file']
            if fp not in changed_files:
                continue
            if fp in changed_ranges:
                for (rs, re_) in changed_ranges[fp]:
                    fn_end = fn['line_end'] or (fn['line_start'] + 50)
                    if fn['line_start'] <= re_ and fn_end >= rs:
                        changed_fns.append({
                            'name': fn['name'], 'file': fp,
                            'line': fn['line_start'], 'subsystem': fn['subsystem'],
                            'complexity': fn.get('complexity', 0),
                            'callers': len(fn['callers']), 'calls': len(fn['calls']),
                        })
                        break
            else:
                changed_fns.append({
                    'name': fn['name'], 'file': fp,
                    'line': fn['line_start'], 'subsystem': fn['subsystem'],
                    'complexity': fn.get('complexity', 0),
                    'callers': len(fn['callers']), 'calls': len(fn['calls']),
                })

        # Compute blast radius via BFS through callers
        all_affected = set()
        for cf in changed_fns:
            fn = self._find_fn(cf['name'])
            if fn:
                visited = set()
                queue = [fn[0]]
                while queue:
                    k = queue.pop(0)
                    if k in visited:
                        continue
                    visited.add(k)
                    f = self.functions.get(k)
                    if f:
                        for caller in f.get('callers', []):
                            queue.append(caller)
                all_affected |= visited

        subs_affected = set()
        for k in all_affected:
            f = self.functions.get(k)
            if f:
                subs_affected.add(f['subsystem'])

        n = len(all_affected)
        risk = 'LOW' if n < 10 else 'MEDIUM' if n < 50 else 'HIGH' if n < 100 else 'CRITICAL'

        return {
            'base': base, 'head': head,
            'files_changed': len(changed_files),
            'file_details': [{'file': f, 'status': s}
                             for f, s in list(changed_files.items())[:30]],
            'functions_changed': len(changed_fns),
            'function_details': changed_fns[:50],
            'blast_radius': n,
            'subsystems_affected': sorted(subs_affected),
            'risk': risk,
        }

    # ── Tier 3: PR auto-review context ───────────────────────────────

    def query_pr_review(self, base_branch='main'):
        """Auto-generate PR review: changes, blast radius, new edges, risk."""
        try:
            r = subprocess.run(
                ['git', '-C', self.root, 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5)
            current_branch = r.stdout.strip()
        except Exception:
            return {'error': 'Not a git repository'}

        try:
            r = subprocess.run(
                ['git', '-C', self.root, 'log', f'{base_branch}..HEAD', '--oneline'],
                capture_output=True, text=True, timeout=5)
            commits = [l.strip() for l in r.stdout.strip().split('\n') if l.strip()]
        except Exception:
            commits = []

        diff = self.query_diff(base_branch, 'HEAD')
        if 'error' in diff:
            return diff

        # Detect new cross-subsystem edges
        new_edges = set()
        for cf in diff.get('function_details', []):
            fn = self._find_fn(cf['name'])
            if fn:
                key, finfo = fn
                for callee in finfo.get('calls', []):
                    if callee in self.functions:
                        dst_sub = self.functions[callee]['subsystem']
                        if dst_sub != finfo['subsystem']:
                            new_edges.add(f"{finfo['subsystem']} -> {dst_sub}")

        # Complexity of changed code
        total_complexity = sum(
            cf.get('complexity', 0) for cf in diff.get('function_details', []))

        # Build summary
        nf = diff.get('functions_changed', 0)
        nfiles = diff.get('files_changed', 0)
        blast = diff.get('blast_radius', 0)
        lines = [
            f"**{nfiles} files changed**, **{nf} functions modified**",
            f"**Blast radius**: {blast} functions potentially affected",
            f"**Risk**: {diff.get('risk', '?')}",
        ]
        if diff.get('subsystems_affected'):
            lines.append(f"**Subsystems touched**: {', '.join(diff['subsystems_affected'])}")
        if new_edges:
            lines.append(f"**New cross-subsystem edges**: {', '.join(sorted(new_edges))}")
        lines.append(f"**Complexity in changed code**: {total_complexity}")
        if commits:
            lines.append(f"**Commits**: {len(commits)}")

        return {
            'branch': current_branch,
            'base': base_branch,
            'commits': len(commits),
            'commit_list': commits[:20],
            'summary': '\n'.join(lines),
            **diff,
        }

    # ── Tier 3: Runtime correlation (OpenTelemetry) ──────────────────

    def query_runtime(self, trace_file=None, trace_dir=None):
        """Correlate OpenTelemetry/Jaeger traces with static call graph."""
        traces = []
        if trace_file and os.path.isfile(trace_file):
            traces = [trace_file]
        elif trace_dir and os.path.isdir(trace_dir):
            for f in sorted(os.listdir(trace_dir)):
                if f.endswith('.json') or f.endswith('.otlp'):
                    traces.append(os.path.join(trace_dir, f))
        else:
            for d in ['traces', '.traces', 'otel', '.otel', 'telemetry', 'spans']:
                td = os.path.join(self.root, d)
                if os.path.isdir(td):
                    for f in sorted(os.listdir(td)):
                        if f.endswith('.json'):
                            traces.append(os.path.join(td, f))

        if not traces:
            return {
                'status': 'no_traces',
                'hint': 'Export OpenTelemetry traces as JSON to a traces/ directory in your project root. '
                        'Supported formats: OTLP JSON ({resourceSpans: [...]}), Jaeger JSON ({data: [{spans: [...]}]}). '
                        'Or pass trace_file/trace_dir parameter.',
                'setup_example': {
                    'otel_collector': 'exporters: { file: { path: traces/spans.json } }',
                    'jaeger': 'curl http://jaeger:16686/api/traces?service=myapp > traces/spans.json',
                },
            }

        span_counts = {}
        for tf in traces[:20]:
            try:
                with open(tf, 'r') as f:
                    data = json.load(f)
                spans = []
                for rs in data.get('resourceSpans', data.get('resource_spans', [])):
                    for ss in rs.get('scopeSpans', rs.get('scope_spans', [])):
                        spans.extend(ss.get('spans', []))
                if 'data' in data:
                    for trace in data['data']:
                        spans.extend(trace.get('spans', []))

                for span in spans:
                    name = span.get('name', span.get('operationName', ''))
                    duration = 0
                    if 'endTimeUnixNano' in span and 'startTimeUnixNano' in span:
                        duration = (int(span['endTimeUnixNano']) - int(span['startTimeUnixNano'])) / 1e6
                    elif 'duration' in span:
                        duration = span['duration'] / 1000.0
                    if name not in span_counts:
                        span_counts[name] = {'count': 0, 'total_ms': 0, 'max_ms': 0}
                    span_counts[name]['count'] += 1
                    span_counts[name]['total_ms'] += duration
                    span_counts[name]['max_ms'] = max(span_counts[name]['max_ms'], duration)
            except Exception:
                continue

        fn_names = {fn['name'] for fn in self.functions.values()}
        hot_paths = []
        matched = set()

        for span_name, stats in sorted(span_counts.items(), key=lambda x: -x[1]['count']):
            base_name = span_name.split('.')[-1].split('::')[-1].split('/')[-1]
            if base_name in fn_names:
                matched.add(base_name)
                fn = self._find_fn(base_name)
                hot_paths.append({
                    'span': span_name, 'function': base_name,
                    'file': fn[1]['file'] if fn else '?',
                    'subsystem': fn[1]['subsystem'] if fn else '?',
                    'invocations': stats['count'],
                    'total_ms': round(stats['total_ms'], 1),
                    'avg_ms': round(stats['total_ms'] / max(stats['count'], 1), 2),
                    'max_ms': round(stats['max_ms'], 1),
                })

        cold_functions = []
        for fn_key, fn in self.functions.items():
            if fn['name'] not in matched and fn['callers']:
                cold_functions.append({
                    'name': fn['name'], 'file': fn['file'],
                    'callers': len(fn['callers']),
                })
        cold_functions.sort(key=lambda x: x['callers'], reverse=True)

        return {
            'trace_files': len(traces),
            'total_spans': sum(s['count'] for s in span_counts.values()),
            'unique_operations': len(span_counts),
            'matched_to_functions': len(hot_paths),
            'hot_paths': hot_paths[:30],
            'potentially_cold': cold_functions[:20],
        }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool definitions
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        'name': 'lilbrain_overview',
        'description': 'Project overview: files, functions, classes, languages, subsystems, pipelines. Start here.',
        'inputSchema': {'type': 'object', 'properties': {}, 'required': []},
    },
    {
        'name': 'lilbrain_function',
        'description': 'Look up any function by name. Returns signature, location, callers, callees, language.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name (exact or partial)'},
        }, 'required': ['name']},
    },
    {
        'name': 'lilbrain_callers',
        'description': 'Call graph for a function: who calls it and what it calls.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name'},
        }, 'required': ['name']},
    },
    {
        'name': 'lilbrain_search',
        'description': 'Search everything: functions, classes, sections, constants.',
        'inputSchema': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Search query'},
        }, 'required': ['query']},
    },
    {
        'name': 'lilbrain_file',
        'description': 'Get info about a file: functions, classes, sections, language.',
        'inputSchema': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'File path (relative or partial)'},
        }, 'required': ['path']},
    },
    {
        'name': 'lilbrain_read',
        'description': 'Read source code of a function (by name) or file region (by path + line range).',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name or file path'},
            'start': {'type': 'integer', 'description': 'Start line (for file reads)'},
            'end': {'type': 'integer', 'description': 'End line (for file reads)'},
        }, 'required': ['name']},
    },
    {
        'name': 'lilbrain_subsystem',
        'description': 'Deep dive into a subsystem: files, top functions, languages.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Subsystem name'},
        }, 'required': ['name']},
    },
    {
        'name': 'lilbrain_pipeline',
        'description': 'Trace a named pipeline or pattern (parse, validate, handle, compile, etc.).',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Pipeline name'},
        }, 'required': ['name']},
    },
    {
        'name': 'lilbrain_dataflow',
        'description': 'Data flow: upstream callers and downstream callees for a function.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name'},
        }, 'required': ['name']},
    },
    {
        'name': 'lilbrain_trace',
        'description': 'Depth-limited call chain trace from a function.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Starting function'},
            'depth': {'type': 'integer', 'description': 'Max depth (default 5)'},
        }, 'required': ['name']},
    },
    {
        'name': 'lilbrain_hotspots',
        'description': 'Most connected functions (highest fan-in + fan-out).',
        'inputSchema': {'type': 'object', 'properties': {
            'n': {'type': 'integer', 'description': 'Number of hotspots (default 20)'},
        }, 'required': []},
    },
    {
        'name': 'lilbrain_architecture',
        'description': 'Architecture: subsystems, cross-subsystem dependencies, language mix.',
        'inputSchema': {'type': 'object', 'properties': {}, 'required': []},
    },
    # ── Tier 1 ────────────────────────────────────────────────────────
    {
        'name': 'lilbrain_impact',
        'description': 'Blast radius: if you change this function, what breaks? Affected callers, subsystems, risk level.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function to analyze'},
            'depth': {'type': 'integer', 'description': 'Max caller depth (default 5)'},
        }, 'required': ['name']},
    },
    {
        'name': 'lilbrain_diagram',
        'description': 'Auto-generate Mermaid or D2 architecture diagrams. Target: "architecture", subsystem name, or function name.',
        'inputSchema': {'type': 'object', 'properties': {
            'target': {'type': 'string', 'description': '"architecture", a subsystem name, or a function name (default: architecture)'},
            'format': {'type': 'string', 'description': '"mermaid" (default) or "d2"', 'enum': ['mermaid', 'd2']},
        }, 'required': []},
    },
    {
        'name': 'lilbrain_deadcode',
        'description': 'Find dead code: functions with zero callers, grouped by subsystem, with LOC waste estimate.',
        'inputSchema': {'type': 'object', 'properties': {}, 'required': []},
    },
    {
        'name': 'lilbrain_clones',
        'description': 'Detect near-duplicate functions using token similarity. Finds copy-paste code.',
        'inputSchema': {'type': 'object', 'properties': {
            'threshold': {'type': 'number', 'description': 'Similarity threshold 0.0-1.0 (default 0.7)'},
        }, 'required': []},
    },
    # ── Tier 2 ────────────────────────────────────────────────────────
    {
        'name': 'lilbrain_complexity',
        'description': 'Cyclomatic + cognitive complexity analysis. Per-function detail or top-N ranking.',
        'inputSchema': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Function name (omit for top-N ranking)'},
            'n': {'type': 'integer', 'description': 'Number of results for ranking (default 20)'},
        }, 'required': []},
    },
    {
        'name': 'lilbrain_complexity_velocity',
        'description': 'Track complexity changes over recent git history. Shows which commits touched complex code.',
        'inputSchema': {'type': 'object', 'properties': {
            'n_commits': {'type': 'integer', 'description': 'Number of commits to analyze (default 10)'},
        }, 'required': []},
    },
    {
        'name': 'lilbrain_semantic',
        'description': 'Semantic search: find functions by meaning, not just name. "handle authentication" finds verify_token, check_session, etc.',
        'inputSchema': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Natural language query'},
            'n': {'type': 'integer', 'description': 'Number of results (default 20)'},
        }, 'required': ['query']},
    },
    {
        'name': 'lilbrain_federation',
        'description': 'Multi-repo federated search: query across multiple codebases at once.',
        'inputSchema': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Search query'},
            'repos': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Additional repo paths to include'},
        }, 'required': ['query']},
    },
    # ── Tier 3 ────────────────────────────────────────────────────────
    {
        'name': 'lilbrain_ask',
        'description': 'Ask a natural language question about the codebase. Auto-routes to the right analysis tool.',
        'inputSchema': {'type': 'object', 'properties': {
            'question': {'type': 'string', 'description': 'Question in plain English'},
        }, 'required': ['question']},
    },
    {
        'name': 'lilbrain_diff',
        'description': 'Git-aware graph diff: changed functions, blast radius, risk level between any two refs.',
        'inputSchema': {'type': 'object', 'properties': {
            'base': {'type': 'string', 'description': 'Base git ref (default HEAD~1)'},
            'head': {'type': 'string', 'description': 'Head git ref (default HEAD)'},
        }, 'required': []},
    },
    {
        'name': 'lilbrain_pr_review',
        'description': 'Auto-generate PR review context: changes, blast radius, new cross-subsystem edges, complexity delta, risk.',
        'inputSchema': {'type': 'object', 'properties': {
            'base_branch': {'type': 'string', 'description': 'Base branch to compare against (default "main")'},
        }, 'required': []},
    },
    {
        'name': 'lilbrain_runtime',
        'description': 'Correlate OpenTelemetry/Jaeger traces with static call graph. Find hot production paths and cold code.',
        'inputSchema': {'type': 'object', 'properties': {
            'trace_file': {'type': 'string', 'description': 'Path to trace JSON file'},
            'trace_dir': {'type': 'string', 'description': 'Directory containing trace JSON files'},
        }, 'required': []},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Tool dispatch
# ─────────────────────────────────────────────────────────────────────────────

def handle_tool_call(graph: LiLBrain, watcher: GraphWatcher,
                     tool_name: str, args: dict) -> Any:
    if watcher.is_stale():
        sys.stderr.write('[lilbrain] Sources changed, reindexing...\n')
        sys.stderr.flush()
        graph.__init__(graph.root)
        graph.build()
        watcher.snapshot()
        sys.stderr.write('[lilbrain] Reindex complete.\n')
        sys.stderr.flush()

    dispatch = {
        'lilbrain_overview': lambda: graph.query_overview(),
        'lilbrain_function': lambda: graph.query_function(args.get('name', '')),
        'lilbrain_callers': lambda: graph.query_callers(args.get('name', '')),
        'lilbrain_search': lambda: graph.query_search(args.get('query', '')),
        'lilbrain_file': lambda: graph.query_file(args.get('path', '')),
        'lilbrain_read': lambda: graph.query_read(args.get('name', ''), args.get('start', 0), args.get('end', 0)),
        'lilbrain_subsystem': lambda: graph.query_subsystem(args.get('name', '')),
        'lilbrain_pipeline': lambda: graph.query_pipeline(args.get('name', '')),
        'lilbrain_dataflow': lambda: graph.query_dataflow(args.get('name', '')),
        'lilbrain_trace': lambda: graph.query_trace(args.get('name', ''), args.get('depth', 5)),
        'lilbrain_hotspots': lambda: graph.query_hotspots(args.get('n', 20)),
        'lilbrain_architecture': lambda: graph.query_architecture(),
        # Tier 1
        'lilbrain_impact': lambda: graph.query_impact(args.get('name', ''), args.get('depth', 5)),
        'lilbrain_diagram': lambda: graph.query_diagram(args.get('target', 'architecture'), args.get('format', 'mermaid')),
        'lilbrain_deadcode': lambda: graph.query_deadcode(),
        'lilbrain_clones': lambda: graph.query_clones(args.get('threshold', 0.7)),
        # Tier 2
        'lilbrain_complexity': lambda: graph.query_complexity(args.get('name'), args.get('n', 20)),
        'lilbrain_complexity_velocity': lambda: graph.query_complexity_velocity(args.get('n_commits', 10)),
        'lilbrain_semantic': lambda: graph.query_semantic(args.get('query', ''), args.get('n', 20)),
        'lilbrain_federation': lambda: graph.query_federation(args.get('repos', []), args.get('query', '')),
        # Tier 3
        'lilbrain_ask': lambda: graph.query_ask(args.get('question', '')),
        'lilbrain_diff': lambda: graph.query_diff(args.get('base', 'HEAD~1'), args.get('head', 'HEAD')),
        'lilbrain_pr_review': lambda: graph.query_pr_review(args.get('base_branch', 'main')),
        'lilbrain_runtime': lambda: graph.query_runtime(args.get('trace_file'), args.get('trace_dir')),
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


def run_mcp_server(graph: LiLBrain, watcher: GraphWatcher):
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
                    'serverInfo': {'name': 'lilbrain', 'version': '0.2.0'},
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
        description='LiLBrain — instant codebase knowledge graph MCP server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  lilbrain                     # Index current directory, run MCP server
  lilbrain /path/to/project    # Index specific project
  lilbrain --dump              # Print graph JSON and exit
  lilbrain --query main        # Quick function lookup and exit

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

    sys.stderr.write(f'[lilbrain] Indexing {root} ...\n')
    sys.stderr.flush()

    graph = LiLBrain(root)
    graph.build()

    # Set up watcher
    watcher = GraphWatcher()
    watcher.track_dir(root, list(LANGUAGES.keys()))
    watcher.track_sentinel(root)
    watcher.snapshot()

    sys.stderr.write(
        f'[lilbrain] {len(graph.functions)} functions, '
        f'{len(graph.files)} files, '
        f'{len(graph.classes)} classes, '
        f'{len(graph.subsystems)} subsystems '
        f'in {graph.build_time:.1f}s\n'
    )
    langs = ', '.join(f'{k}({v})' for k, v in sorted(graph.languages_found.items(), key=lambda x: -x[1]))
    sys.stderr.write(f'[lilbrain] Languages: {langs}\n')
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
