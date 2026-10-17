"""Bounded, read-only repository context. Imported code is parsed, never executed."""
import ast
import base64
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

from .schema import Entity, Link
from .source_http import remote_json

SUFFIXES = {'.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.md', '.txt', '.toml', '.json'}
SKIP = {'node_modules', 'vendor', 'dist', 'build', '.git', '.venv', 'venv', '__pycache__'}


def eligible(path):
    p = PurePosixPath(path)
    return (not set(p.parts) & SKIP and p.suffix.lower() in SUFFIXES
            and not any(part.startswith('.') for part in p.parts)
            and not any(word in p.name.lower() for word in ('lock', 'secret', 'credential')))


def priority(item):
    path = item['path'].lower()
    name = PurePosixPath(path).name
    score = 0
    if name in {'readme.md', 'package.json', 'pyproject.toml', 'requirements.txt'}: score += 30
    if name in {'main.py', 'app.py', 'index.ts', 'index.js'}: score += 25
    if any(word in path for word in ('pipeline', 'routes', 'context_builder', 'prompt_builder')): score += 20
    if any(word in path for word in ('factory', 'service')): score += 10
    if any(word in path for word in ('test', 'schema', 'exception', 'base_')): score -= 15
    return (-score, path)


def python_summary(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return '', []
    notes, imports = [], []
    if ast.get_docstring(tree): notes.append(ast.get_docstring(tree))
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            notes.append(f'{node.name}: {doc}' if doc else f'Defines {node.name}')
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imports.append(node.module)
            imports.extend(node.module + '.' + alias.name for alias in node.names)
    return '\n'.join(notes)[:5000], imports


def resolve_import(module, by_path):
    suffixes = (module.replace('.', '/') + '.py', module.replace('.', '/') + '/__init__.py')
    for suffix in suffixes:
        if suffix in by_path:
            return by_path[suffix], 'confirmed'
    # Source roots depend on runtime configuration; unique suffix matches are candidates.
    matches = {value for path, value in by_path.items() if any(path.endswith('/' + suffix) for suffix in suffixes)}
    return (next(iter(matches)), 'candidate') if len(matches) == 1 else (None, 'candidate')


async def repository_code(client, base, metadata, project_id, repo_id):
    entities, links, warnings = [], [], []
    branch = metadata.get('default_branch')
    if not branch:
        return entities, links, warnings
    try:
        tree, _ = await remote_json(client, 'GET', base + '/git/trees/' + quote(branch, safe=''), params={'recursive': '1'})
    except (httpx.HTTPError, ValueError):
        return [], [], ['Repository file listing could not be loaded. Code questions may be incomplete.']
    files = [item for item in tree.get('tree', []) if item.get('type') == 'blob'
             and item.get('mode') != '120000' and eligible(item['path']) and item.get('size', 0) > 0]
    files.sort(key=priority)
    if tree.get('truncated') or len(files) > 500:
        warnings.append('Repository file listing is partial (maximum 500 eligible files).')
    files = files[:500]
    by_path = {item['path']: f"{project_id}:file:{item['path']}" for item in files}
    content_files = [item for item in files if item.get('size', 0) <= 40000][:24]
    loaded = {}
    failed = 0
    for item in content_files:
        try:
            blob, _ = await remote_json(client, 'GET', base + '/git/blobs/' + quote(item['sha'], safe=''))
            text = base64.b64decode(blob['content']).decode('utf-8')
            if '\x00' not in text:
                loaded[item['path']] = text[:40000]
        except (httpx.HTTPError, ValueError, KeyError):
            failed += 1
    for item in files:
        path = item['path']
        file_id = by_path[path]
        url = metadata['html_url'] + '/blob/' + quote(branch, safe='') + '/' + quote(path, safe='/')
        text = loaded.get(path, '')
        summary, imports = python_summary(text) if path.endswith('.py') else (text[:1800], [])
        description = f'File: {path}\n' + (summary or ('Content available in linked sections.' if text else 'File listed; content not imported.'))
        entities.append(Entity(id=file_id, kind='CodeFile', name=path, source='github', url=url, description=description))
        links.append(Link(source=file_id, target=repo_id, kind='PART_OF', evidence=url))
        for module in set(imports):
            target, confidence = resolve_import(module, by_path)
            if target and target != file_id:
                links.append(Link(source=file_id, target=target, kind='IMPORTS', evidence=url, confidence=confidence))
        lines = text.splitlines()
        for offset in range(0, len(lines), 50):
            section_id = f'{file_id}:lines:{offset + 1}'
            end = min(offset + 50, len(lines))
            entities.append(Entity(id=section_id, kind='CodeSection', name=f'{path} lines {offset + 1}-{end}', source='github',
                                   url=f'{url}#L{offset + 1}-L{end}', description='\n'.join(lines[offset:end])[:10000]))
            links.append(Link(source=section_id, target=file_id, kind='PART_OF', evidence=url))
    warnings.append(f'Code coverage: content from {len(loaded)} of {len(files)} listed eligible files; maximum 24 files of 40 KB each. Import links are parsed from absolute Python imports, not runtime call tracing.')
    if failed:
        warnings.append(f'{failed} selected files could not be read. Configure GITHUB_TOKEN if the API rate limit was reached.')
    return entities, links, warnings
