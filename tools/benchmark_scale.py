import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from tools import analyzer


def _run_git(directory, *args):
    return subprocess.run(
        ['git', *args], cwd=directory, check=True, capture_output=True, text=True
    )


def _generate_project(root, test_count, test_file_count, affected_file_count):
    source_root = root / 'src'
    feature_root = source_root / 'features'
    test_root = root / 'tests'
    feature_root.mkdir(parents=True)
    test_root.mkdir()
    (source_root / '__init__.py').write_text('', encoding='utf-8')
    (feature_root / '__init__.py').write_text('', encoding='utf-8')

    feature_count = min(10, test_file_count)
    for feature_index in range(feature_count):
        (feature_root / f'feature_{feature_index:03d}.py').write_text(
            f'VALUE = {feature_index}\n', encoding='utf-8'
        )

    cases_per_file = [[] for _ in range(test_file_count)]
    for case_index in range(test_count):
        file_index = case_index % test_file_count
        if file_index < affected_file_count:
            feature_index = 0
        else:
            feature_index = 1 + ((file_index - affected_file_count) % (feature_count - 1))
        cases_per_file[file_index].append((case_index, feature_index))

    for file_index, cases in enumerate(cases_per_file):
        feature_index = cases[0][1]
        lines = [f'from src.features.feature_{feature_index:03d} import VALUE', '']
        lines.extend(
            f'def test_case_{case_index:05d}():\n    assert VALUE == {feature_index}\n'
            for case_index, _ in cases
        )
        (test_root / f'test_feature_{file_index:04d}.py').write_text(
            '\n'.join(lines), encoding='utf-8'
        )

    return feature_root / 'feature_000.py', test_count


def _prepare_git_repository(root):
    _run_git(root, 'init', '--quiet')
    _run_git(root, 'add', 'src', 'tests')
    _run_git(
        root,
        '-c', 'user.name=Benchmark',
        '-c', 'user.email=benchmark@example.invalid',
        'commit', '--quiet', '-m', 'synthetic baseline',
    )


def _measure(command_paths, cwd):
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', *command_paths],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=os.environ.copy(),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    summary_lines = [
        line.strip() for line in result.stdout.splitlines()
        if re.search(r'\b\d+ passed\b|\b\d+ failed\b|\b\d+ error', line)
    ]
    if result.returncode:
        raise RuntimeError(
            f"pytest failed with exit code {result.returncode}:\n"
            + '\n'.join(result.stdout.splitlines()[-30:])
        )
    return elapsed_ms, summary_lines[-1] if summary_lines else 'pytest passed (summary unavailable)'


def _mean(values):
    return sum(values) / len(values)


def _fmt(milliseconds):
    return f'{milliseconds:,.1f} ms'


def benchmark(test_count=10_000, test_file_count=100, affected_file_count=10, repeat=3):
    if test_count < test_file_count:
        raise ValueError('--tests must be greater than or equal to --test-files')
    if not 1 <= affected_file_count < test_file_count:
        raise ValueError('--affected-files must be between 1 and test-files - 1')
    if repeat < 1:
        raise ValueError('--repeat must be at least 1')

    original_values = (analyzer.ROOT, analyzer.SRC, analyzer.TEST, analyzer.CACHE)
    with tempfile.TemporaryDirectory(prefix='selective-10k-benchmark-') as temp_dir:
        root = Path(temp_dir)
        changed_file, generated_case_count = _generate_project(
            root, test_count, test_file_count, affected_file_count
        )
        _prepare_git_repository(root)

        analyzer.ROOT = root
        analyzer.SRC = root / 'src'
        analyzer.TEST = root / 'tests'
        analyzer.CACHE = root / '.cache' / 'index.json'
        try:
            index_started = time.perf_counter()
            baseline_index, baseline_timings, baseline_analyzed = analyzer.load_or_update_index()
            baseline_index_ms = (time.perf_counter() - index_started) * 1000
            if baseline_analyzed != test_file_count + min(10, test_file_count) + 2:
                raise RuntimeError(f'Unexpected baseline index size: {baseline_analyzed} files')

            changed_key = analyzer.key(changed_file)
            changed_file.write_text(
                changed_file.read_text(encoding='utf-8') + '# simulated source change\n',
                encoding='utf-8',
            )
            all_test_paths = sorted(
                analyzer.key(path) for path in analyzer.TEST.glob('test_*.py')
            )
            affected_paths = sorted(
                analyzer.key(path) for path in analyzer.TEST.glob('test_*.py')
                if int(path.stem.rsplit('_', 1)[1]) < affected_file_count
            )
            if len(affected_paths) != affected_file_count:
                raise RuntimeError('Generated affected test-file count did not match configuration')

            no_index_totals = []
            no_index_analysis = []
            no_index_test_times = []
            no_index_summary = ''
            for _ in range(repeat):
                started = time.perf_counter()
                git_started = time.perf_counter()
                detected_changes = analyzer.changed()
                git_ms = (time.perf_counter() - git_started) * 1000
                if changed_key not in detected_changes:
                    raise RuntimeError('Git did not detect the simulated source change')
                _, _, reverse, _, discovery_ms, ast_ms, graph_ms = analyzer.parse_all()
                selected, _, selection_ms = analyzer.select(reverse, detected_changes)
                analysis_total_ms = git_ms + discovery_ms + ast_ms + graph_ms + selection_ms
                test_ms, no_index_summary = _measure(selected, root)
                no_index_totals.append((time.perf_counter() - started) * 1000)
                no_index_analysis.append(analysis_total_ms)
                no_index_test_times.append(test_ms)

            indexed_totals = []
            indexed_update_times = []
            indexed_test_times = []
            indexed_summary = ''
            indexed_selected_count = 0
            indexed_parsed_counts = []
            for _ in range(repeat):
                started = time.perf_counter()
                git_started = time.perf_counter()
                detected_changes = analyzer.changed()
                git_ms = (time.perf_counter() - git_started) * 1000
                if changed_key not in detected_changes:
                    raise RuntimeError('Git did not detect the simulated source change')
                index, timings, analyzed = analyzer.load_or_update_index()
                selected, _, selection_ms = analyzer.select(index['rev'], detected_changes)
                index_update_ms = git_ms + sum(timings) + selection_ms
                test_ms, indexed_summary = _measure(selected, root)
                indexed_totals.append((time.perf_counter() - started) * 1000)
                indexed_update_times.append(index_update_ms)
                indexed_test_times.append(test_ms)
                indexed_selected_count = len(selected)
                indexed_parsed_counts.append(analyzed)

            full_times = []
            full_test_times = []
            full_summary = ''
            for _ in range(repeat):
                full_started = time.perf_counter()
                analyzer.changed()
                full_ms, full_summary = _measure([], root)
                full_times.append((time.perf_counter() - full_started) * 1000)
                full_test_times.append(full_ms)

            expected_selected_cases = sum(
                1 for case_index in range(test_count)
                if case_index % test_file_count < affected_file_count
            )
            if indexed_selected_count != affected_file_count:
                raise RuntimeError(f'Expected {affected_file_count} selected files, got {indexed_selected_count}')
            if not any(f'{generated_case_count} passed' in line for line in full_summary.splitlines()):
                raise RuntimeError(f'Full suite did not confirm {generated_case_count} passing tests: {full_summary}')
            if not any(f'{expected_selected_cases} passed' in line for line in indexed_summary.splitlines()):
                raise RuntimeError(
                    f'Selected run did not confirm {expected_selected_cases} passing tests: {indexed_summary}'
                )

            full_mean = _mean(full_times)
            no_index_mean = _mean(no_index_totals)
            indexed_mean = _mean(indexed_totals)
            print('Isolated synthetic benchmark; all generated files live in a temporary directory.')
            print(
                f'Workload: {generated_case_count:,} pytest cases in {test_file_count:,} files; '
                f'one changed source selects {affected_file_count:,} files and '
                f'{expected_selected_cases:,} cases.'
            )
            print(f'Repeats per run mode: {repeat}')
            print(f'Initial full index build (one-time setup): {_fmt(baseline_index_ms)}')
            print(
                f'Initial index AST parse: {_fmt(baseline_timings[1])} '
                f'({baseline_analyzed:,} Python files analyzed)'
            )
            print()
            print(f"{'Mode':<30} {'Total mean':>14} {'Analysis mean':>16} {'Pytest mean':>14} {'Savings vs full':>18}")
            print('-' * 98)
            print(
                f"{'Full suite':<30} {_fmt(full_mean):>14} {'not applicable':>16} "
                f'{_fmt(_mean(full_test_times)):>14} {"0.0%":>18}'
            )
            print(
                f"{'Selective, no index':<30} {_fmt(no_index_mean):>14} "
                f'{_fmt(_mean(no_index_analysis)):>16} '
                f'{_fmt(_mean(no_index_test_times)):>14} '
                f'{(1 - no_index_mean / full_mean) * 100:>17.1f}%'
            )
            print(
                f"{'Selective, indexed':<30} {_fmt(indexed_mean):>14} "
                f'{_fmt(_mean(indexed_update_times)):>16} '
                f'{_fmt(_mean(indexed_test_times)):>14} '
                f'{(1 - indexed_mean / full_mean) * 100:>17.1f}%'
            )
            print()
            print('Pytest summaries:')
            print(f'  Full: {full_summary}')
            print(f'  Selective, no index: {no_index_summary}')
            print(f'  Selective, indexed: {indexed_summary}')
            print(f'Changed source: {changed_key}')
            print(f'Indexed files parsed after the simulated change: {indexed_parsed_counts}')
            print(
                'Note: test selection is file-granular. The benchmark distributes cases evenly; '
                'adjust --tests, --test-files, --affected-files, and --repeat to model another layout.'
            )
            return {
                'full_mean_ms': full_mean,
                'selective_no_index_mean_ms': no_index_mean,
                'selective_indexed_mean_ms': indexed_mean,
                'initial_index_build_ms': baseline_index_ms,
                'selected_test_files': indexed_selected_count,
                'selected_test_cases': expected_selected_cases,
            }
        finally:
            analyzer.ROOT, analyzer.SRC, analyzer.TEST, analyzer.CACHE = original_values


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Benchmark full and selective pytest runs on an isolated synthetic project.'
    )
    parser.add_argument('--tests', type=int, default=10_000, help='Synthetic pytest case count')
    parser.add_argument('--test-files', type=int, default=100, help='Number of generated test modules')
    parser.add_argument('--affected-files', type=int, default=10, help='Related test modules for one changed source')
    parser.add_argument('--repeat', type=int, default=3, help='Runs per mode')
    args = parser.parse_args(argv)
    try:
        benchmark(args.tests, args.test_files, args.affected_files, args.repeat)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
