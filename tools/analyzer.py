import argparse
import ast
import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
TEST = ROOT / 'tests'
CACHE = ROOT / '.cache' / 'index.json'
INDEX_VERSION = 2


def files():
  return sorted([*SRC.rglob('*.py'), *TEST.rglob('*.py')])


def key(path):
  return path.relative_to(ROOT).as_posix()


def _git_names(*args):
  result = subprocess.run(
    ['git', *args], cwd=ROOT, check=True, capture_output=True, text=True
  )
  return result.stdout.splitlines()


def _environment_base_ref():
  if os.environ.get('SELECTIVE_TEST_BASE'):
    return os.environ['SELECTIVE_TEST_BASE']
  if os.environ.get('GITHUB_BASE_REF'):
    return f"origin/{os.environ['GITHUB_BASE_REF']}"
  if os.environ.get('CI_MERGE_REQUEST_DIFF_BASE_SHA'):
    return os.environ['CI_MERGE_REQUEST_DIFF_BASE_SHA']
  if os.environ.get('BITBUCKET_PR_DESTINATION_BRANCH'):
    return f"origin/{os.environ['BITBUCKET_PR_DESTINATION_BRANCH']}"
  for variable in ('GITHUB_EVENT_BEFORE', 'CI_COMMIT_BEFORE_SHA'):
    value = os.environ.get(variable)
    if value and set(value) != {'0'}:
      return value
  return None


def changed(base_ref=None):
  base_ref = base_ref or _environment_base_ref()
  paths = set()
  if base_ref:
    try:
      paths.update(_git_names('diff', '--name-only', '--no-renames', f'{base_ref}...HEAD'))
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
      print(f'Cannot compare base {base_ref!r}; will run the full suite: {error}', file=sys.stderr)
      return []
  try:
    paths.update(_git_names('diff', '--name-only', '--no-renames', 'HEAD'))
    paths.update(_git_names('ls-files', '--others', '--exclude-standard'))
  except (subprocess.CalledProcessError, FileNotFoundError) as error:
    print(f'Cannot read Git changes; will run the full suite: {error}', file=sys.stderr)
    return []
  return sorted(
    path.replace('\\', '/') for path in paths
    if path.endswith('.py')
  )


def _module_file(module_name, available):
  if not module_name:
    return set()
  module_path = module_name.replace('.', '/')
  return {
    candidate
    for candidate in (f'{module_path}.py', f'{module_path}/__init__.py')
    if candidate in available
  }


def _import_targets(file_key, node, available):
  if isinstance(node, ast.Import):
    targets = set()
    for alias in node.names:
      targets.update(_module_file(alias.name, available))
    return targets

  if not isinstance(node, ast.ImportFrom):
    return set()

  if node.level:
    package_parts = list(PurePosixPath(file_key).parent.parts)
    package_parts = package_parts[:len(package_parts) - node.level + 1]
    if node.module:
      package_parts.extend(node.module.split('.'))
  else:
    package_parts = node.module.split('.') if node.module else []
  base_module = '.'.join(package_parts)
  targets = _module_file(base_module, available)
  for alias in node.names:
    if alias.name != '*':
      targets.update(_module_file('.'.join((*package_parts, alias.name)), available))
  return targets


def _parse_file(file_key, available):
  tree = ast.parse((ROOT / file_key).read_text(encoding='utf-8'))
  dependencies = set()
  for node in ast.walk(tree):
    dependencies.update(_import_targets(file_key, node, available))
  symbols = {
    'classes': [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)],
    'functions': [
      node.name for node in ast.walk(tree)
      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ],
  }
  return dependencies, symbols


def _reverse_graph(dependencies):
  reverse = {path: set() for path in dependencies}
  for importer, imported in dependencies.items():
    for dependency in imported:
      reverse.setdefault(dependency, set()).add(importer)
  return reverse


def parse_all():
  started = time.perf_counter()
  source_files = files()
  discovery_ms = (time.perf_counter() - started) * 1000
  available = {key(path) for path in source_files}
  started = time.perf_counter()
  dependencies = {}
  symbols = {}
  for path in source_files:
    file_key = key(path)
    dependencies[file_key], symbols[file_key] = _parse_file(file_key, available)
  ast_ms = (time.perf_counter() - started) * 1000
  started = time.perf_counter()
  reverse = _reverse_graph(dependencies)
  graph_ms = (time.perf_counter() - started) * 1000
  return source_files, dependencies, reverse, symbols, discovery_ms, ast_ms, graph_ms


def _git_index_blobs():
  try:
    indexed = subprocess.run(
      ['git', 'ls-files', '--stage', '-z', '--', 'src', 'tests'],
      cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    dirty = subprocess.run(
      ['git', 'ls-files', '--modified', '--others', '--exclude-standard', '-z', '--', 'src', 'tests'],
      cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
  except (subprocess.CalledProcessError, FileNotFoundError):
    return {}

  dirty_paths = set(dirty.split('\0'))
  blobs = {}
  for entry in indexed.split('\0'):
    if not entry or '\t' not in entry:
      continue
    metadata, file_key = entry.split('\t', 1)
    if file_key not in dirty_paths:
      blobs[file_key] = metadata.split()[1]
  return blobs


def _file_state(path, git_blob=None):
  if git_blob:
    return {'git_blob': git_blob}
  return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _read_index():
  try:
    index = json.loads(CACHE.read_text(encoding='utf-8'))
    if (
      index.get('version') == INDEX_VERSION
      and isinstance(index.get('files'), dict)
      and isinstance(index.get('deps'), dict)
      and isinstance(index.get('rev'), dict)
      and isinstance(index.get('symbols'), dict)
    ):
      return index
  except (OSError, json.JSONDecodeError, AttributeError):
    pass
  return None


def _write_index(index):
  CACHE.parent.mkdir(parents=True, exist_ok=True)
  temporary_path = None
  try:
    with tempfile.NamedTemporaryFile(
      mode='w', encoding='utf-8', dir=CACHE.parent, delete=False
    ) as temporary_file:
      temporary_path = Path(temporary_file.name)
      json.dump(index, temporary_file, separators=(',', ':'))
    os.replace(temporary_path, CACHE)
  finally:
    if temporary_path and temporary_path.exists():
      temporary_path.unlink()


def load_or_update_index():
  started = time.perf_counter()
  source_files = files()
  git_blobs = _git_index_blobs()
  current_state = {
    key(path): _file_state(path, git_blobs.get(key(path))) for path in source_files
  }
  discovery_ms = (time.perf_counter() - started) * 1000
  started = time.perf_counter()
  index = _read_index()
  load_ms = (time.perf_counter() - started) * 1000

  if index is None:
    dependencies = {}
    symbols = {}
    changed_keys = set(current_state)
    removed_keys = set()
  else:
    changed_keys = {
      file_key for file_key, state in current_state.items()
      if index['files'].get(file_key) != state
    }
    removed_keys = set(index['files']) - set(current_state)
    if not changed_keys and not removed_keys:
      return index, (discovery_ms, 0.0, 0.0, load_ms), 0
    dependencies = {
      file_key: set(values) for file_key, values in index['deps'].items()
      if file_key in current_state
    }
    symbols = {
      file_key: value for file_key, value in index['symbols'].items()
      if file_key in current_state
    }

  started = time.perf_counter()
  available = set(current_state)
  for file_key in changed_keys:
    dependencies[file_key], symbols[file_key] = _parse_file(file_key, available)
  ast_ms = (time.perf_counter() - started) * 1000
  started = time.perf_counter()
  reverse = _reverse_graph(dependencies)
  graph_ms = (time.perf_counter() - started) * 1000
  updated_index = {
    'version': INDEX_VERSION,
    'files': current_state,
    'deps': {file_key: sorted(values) for file_key, values in dependencies.items()},
    'rev': {file_key: sorted(values) for file_key, values in reverse.items()},
    'symbols': symbols,
  }
  started = time.perf_counter()
  _write_index(updated_index)
  index_ms = (time.perf_counter() - started) * 1000 + load_ms
  return updated_index, (discovery_ms, ast_ms, graph_ms, index_ms), len(changed_keys)


def select(reverse, changed_paths):
  started = time.perf_counter()
  seen = set(changed_paths)
  queue = deque(changed_paths)
  paths = {path: [path] for path in changed_paths}
  while queue:
    path = queue.popleft()
    for dependent in sorted(reverse.get(path, [])):
      if dependent not in seen:
        seen.add(dependent)
        paths[dependent] = paths[path] + [dependent]
        queue.append(dependent)
  selected = sorted(
    path for path in seen
    if path.startswith('tests/') and PurePosixPath(path).name.startswith('test_')
    and path.endswith('.py')
  )
  return selected, paths, (time.perf_counter() - started) * 1000


def run_tests(selected=None):
  started = time.perf_counter()
  command = [sys.executable, '-m', 'pytest', '-q']
  if selected:
    command.extend(selected)
  result = subprocess.run(command)
  return (time.perf_counter() - started) * 1000, result.returncode


def one(mode, execute=True, base_ref=None):
  started = time.perf_counter()
  changed_paths = changed(base_ref)
  all_tests = [key(path) for path in TEST.rglob('test_*.py')]
  discovery_ms = ast_ms = graph_ms = index_ms = selection_ms = 0.0
  analyzed = 0
  paths = {}
  fallback = None

  if mode == 'full':
    selected = all_tests
  else:
    if mode == 'selective':
      source_files, dependencies, reverse, symbols, discovery_ms, ast_ms, graph_ms = parse_all()
      analyzed = len(source_files)
    else:
      index, timings, analyzed = load_or_update_index()
      discovery_ms, ast_ms, graph_ms, index_ms = timings
      reverse = index['rev']
    if changed_paths:
      selected, paths, selection_ms = select(reverse, changed_paths)
    else:
      selected = []
    if not changed_paths or not selected:
      selected = all_tests
      fallback = 'No reliable related-test selection; running the full suite.'

  test_ms, test_exit = run_tests(selected if mode != 'full' else None) if execute else (0.0, 0)
  total_ms = (time.perf_counter() - started) * 1000
  return {
    'mode': mode,
    'changed': changed_paths,
    'total_tests': len(all_tests),
    'selected_tests': len(selected),
    'ignored_tests': len(all_tests) - len(selected),
    'discovery_ms': discovery_ms,
    'ast_ms': ast_ms,
    'graph_ms': graph_ms,
    'index_ms': index_ms,
    'selection_ms': selection_ms,
    'test_ms': test_ms,
    'total_ms': total_ms,
    'files_analyzed': analyzed,
    'selected': selected,
    'paths': paths,
    'fallback': fallback,
    'test_exit': test_exit,
  }


def report(result):
  print('=' * 40 + '\nSELECTIVE TEST ANALYSIS\n' + '=' * 40)
  print('Changed files:', *(result['changed'] or ['(none)']), sep='\n- ')
  if result['fallback']:
    print(result['fallback'])
  print('Selected tests:', *(result['selected'] or ['(none)']), sep='\n- ')
  print(
    f"tests={result['total_tests']} selected={result['selected_tests']} "
    f"ignored={result['ignored_tests']} ast={result['ast_ms']:.3f}ms "
    f"index={result['index_ms']:.3f}ms selection={result['selection_ms']:.3f}ms "
    f"tests_time={result['test_ms']:.3f}ms exit={result['test_exit']} "
    f"total={result['total_ms']:.3f}ms"
  )
  for test in result['selected']:
    if test in result['paths']:
      print('Reason: ' + ' -> '.join(result['paths'][test]))


def main(argv=None):
  parser = argparse.ArgumentParser()
  parser.add_argument('--mode', choices=['full', 'selective', 'indexed', 'benchmark'], default='indexed')
  parser.add_argument('--base-ref', help='Git ref or commit SHA used as the diff base')
  parser.add_argument('--repeat', type=int, default=5)
  parser.add_argument('--results', default='benchmark/results')
  args = parser.parse_args(argv)
  if args.repeat < 1:
    parser.error('--repeat must be at least 1')

  modes = ['full', 'selective', 'indexed'] if args.mode == 'benchmark' else [args.mode]
  results = []
  for mode in modes:
    for _ in range(args.repeat if args.mode == 'benchmark' else 1):
      results.append(one(mode, base_ref=args.base_ref))
  for result in results:
    report(result)

  if args.mode == 'benchmark':
    output_dir = Path(args.results)
    if not output_dir.is_absolute():
      output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(int(time.time()))
    (output_dir / f'python-{stamp}.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    columns = [name for name, value in results[0].items() if not isinstance(value, (list, dict))]
    with (output_dir / f'python-{stamp}.csv').open('w', newline='', encoding='utf-8') as output_file:
      writer = csv.DictWriter(output_file, fieldnames=columns)
      writer.writeheader()
      writer.writerows([{name: result[name] for name in columns} for result in results])
    for mode in modes:
      measurements = [result for result in results if result['mode'] == mode]
      print(mode, {
        name: {
          'mean': statistics.mean(result[name] for result in measurements),
          'min': min(result[name] for result in measurements),
          'max': max(result[name] for result in measurements),
          'stdev': statistics.pstdev(result[name] for result in measurements),
        }
        for name in ('ast_ms', 'index_ms', 'selection_ms', 'test_ms', 'total_ms')
      })

  return max((result['test_exit'] for result in results), default=0)


if __name__ == '__main__':
  raise SystemExit(main())
