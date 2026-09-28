from types import SimpleNamespace

import pytest
import networkx as nx

from tools import analyzer


@pytest.fixture
def mini_project(tmp_path, monkeypatch):
    source = tmp_path / 'src' / 'pkg'
    tests = tmp_path / 'tests'
    source.mkdir(parents=True)
    tests.mkdir()
    (source / '__init__.py').write_text('', encoding='utf-8')
    (source / 'model.py').write_text('class Model: pass\n', encoding='utf-8')
    (source / 'service.py').write_text('from .model import Model\n', encoding='utf-8')
    (tests / 'test_service.py').write_text('from src.pkg.service import Model\n', encoding='utf-8')
    monkeypatch.setattr(analyzer, 'ROOT', tmp_path)
    monkeypatch.setattr(analyzer, 'SRC', tmp_path / 'src')
    monkeypatch.setattr(analyzer, 'TEST', tests)
    monkeypatch.setattr(analyzer, 'CACHE', tmp_path / '.cache' / 'index.json')
    return tmp_path


def test_relative_imports_reach_affected_tests(mini_project):
    _, dependencies, reverse, _, *_ = analyzer.parse_all()

    assert 'src/pkg/model.py' in dependencies['src/pkg/service.py']
    selected, paths, _ = analyzer.select(reverse, ['src/pkg/model.py'])
    assert selected == ['tests/test_service.py']
    assert paths['tests/test_service.py'] == [
        'src/pkg/model.py', 'src/pkg/service.py', 'tests/test_service.py'
    ]


def test_export_dependency_graph_writes_dot_edges(mini_project):
    output_path, node_count, edge_count = analyzer.export_dependency_graph(
        {
            'src/pkg/service.py': {'src/pkg/model.py'},
            'tests/test_service.py': {'src/pkg/service.py'},
        },
        '.cache/graph.dot',
        'dot',
    )

    graph = output_path.read_text(encoding='utf-8')
    assert node_count == 3
    assert edge_count == 2
    assert 'digraph dependencies {' in graph
    assert 'src/pkg/service.py' in graph
    assert 'shape=box' in graph
    assert ' -> ' in graph


def test_build_dependency_graph_uses_networkx_digraph(mini_project):
    graph = analyzer.build_dependency_graph({
        'src/pkg/service.py': {'src/pkg/model.py'},
        'tests/test_service.py': {'src/pkg/service.py'},
    })

    assert isinstance(graph, nx.DiGraph)
    assert graph.has_edge('tests/test_service.py', 'src/pkg/service.py')
    assert graph.nodes['tests/test_service.py']['kind'] == 'test'
    assert graph.nodes['tests/test_service.py']['group'] == 'Tests'
    assert graph.nodes['src/pkg/model.py']['kind'] == 'source'


def test_export_dependency_graph_renders_interactive_html(mini_project):
    output_path, node_count, edge_count = analyzer.export_dependency_graph(
        {
            'src/pkg/service.py': {'src/pkg/model.py'},
            'tests/test_service.py': {'src/pkg/service.py'},
        },
        '.cache/graph.html',
    )

    rendered = output_path.read_text(encoding='utf-8')
    assert node_count == 3
    assert edge_count == 2
    assert '<html>' in rendered
    assert 'vis-network' in rendered
    assert 'tests/test_service.py' in rendered
    assert 'new vis.Network' in rendered
    assert rendered.count('<h1>Python Dependency Graph</h1>') == 1


def test_export_dependency_graph_writes_graphml(mini_project):
    output_path, node_count, edge_count = analyzer.export_dependency_graph(
        {'tests/test_service.py': {'src/pkg/service.py'}},
        '.cache/graph.graphml',
        'graphml',
    )

    imported = nx.read_graphml(output_path)
    assert node_count == 2
    assert edge_count == 1
    assert imported.has_edge('tests/test_service.py', 'src/pkg/service.py')


def test_export_dependency_graph_writes_json_schema(mini_project):
    output_path, node_count, edge_count = analyzer.export_dependency_graph(
        {'tests/test_service.py': {'src/pkg/service.py'}},
        '.cache/graph.json',
        'json',
    )
    import json

    graph = json.loads(output_path.read_text(encoding='utf-8'))
    assert node_count == 2
    assert edge_count == 1
    assert graph['edge_direction'] == 'importer_to_dependency'
    assert graph['edges'] == [
        {'from': 'tests/test_service.py', 'to': 'src/pkg/service.py'}
    ]
    assert graph['nodes'][0]['kind'] == 'source'


def test_indexed_run_generates_graph_artifact(mini_project, monkeypatch):
    monkeypatch.setattr(analyzer, 'changed', lambda base_ref=None: ['src/pkg/model.py'])

    result = analyzer.one(
        'indexed', execute=False, graph_output='.cache/generated.dot', graph_format='dot'
    )

    assert result['graph_edges'] >= 1
    assert result['graph_output'].endswith('generated.dot')
    assert (mini_project / '.cache' / 'generated.dot').exists()


def test_git_diff_uses_base_and_includes_worktree_and_untracked(mini_project, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-1] == 'origin/main...HEAD':
            output = 'src/pkg/model.py\n'
        elif command[-1] == 'HEAD':
            output = 'src/pkg/service.py\n'
        else:
            output = 'tests/test_new.py\n'
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(analyzer.subprocess, 'run', fake_run)

    assert analyzer.changed('origin/main') == [
        'src/pkg/model.py', 'src/pkg/service.py', 'tests/test_new.py'
    ]
    assert calls[0][-1] == 'origin/main...HEAD'


def test_git_changes_ignore_bytecode_and_non_python_files(mini_project, monkeypatch):
    def fake_run(command, **kwargs):
        if command[-1] == 'HEAD':
            return SimpleNamespace(stdout='tests/test_service.pyc\nREADME.md\nsrc/pkg/model.py\n')
        return SimpleNamespace(stdout='')

    monkeypatch.setattr(analyzer.subprocess, 'run', fake_run)

    assert analyzer.changed('') == ['src/pkg/model.py']


def test_cached_index_parses_only_changed_files(mini_project, monkeypatch):
    first, _, first_count = analyzer.load_or_update_index()
    second, timings, second_count = analyzer.load_or_update_index()

    assert first['rev'] == second['rev']
    assert first_count == 4
    assert second_count == 0
    assert timings[1] == 0

    service = mini_project / 'src' / 'pkg' / 'service.py'
    service.write_text('from .model import Model\n# update\n', encoding='utf-8')
    _, _, updated_count = analyzer.load_or_update_index()
    assert updated_count == 1


def test_cached_index_uses_stable_git_blob_identity(mini_project, monkeypatch):
    paths = analyzer.files()
    blobs = {analyzer.key(path): f'blob-{index}' for index, path in enumerate(paths)}
    monkeypatch.setattr(analyzer, '_git_index_blobs', lambda: blobs)

    analyzer.load_or_update_index()
    for path in paths:
        path.touch()
    _, _, analyzed_count = analyzer.load_or_update_index()

    assert analyzed_count == 0


def test_no_detected_diff_falls_back_to_full_suite(mini_project, monkeypatch):
    monkeypatch.setattr(analyzer, 'changed', lambda base_ref=None: [])

    result = analyzer.one('selective', execute=False)

    assert result['selected'] == ['tests/test_service.py']
    assert result['fallback']


def test_main_returns_pytest_failure_status(mini_project, monkeypatch):
    monkeypatch.setattr(analyzer, 'changed', lambda base_ref=None: [])
    monkeypatch.setattr(analyzer, 'run_tests', lambda selected=None: (1.0, 7))

    assert analyzer.main(['--mode', 'full']) == 7