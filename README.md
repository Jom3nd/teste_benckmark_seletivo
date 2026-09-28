# Execução seletiva de testes

Ferramenta Python para relacionar arquivos alterados a módulos e arquivos de teste dependentes. Ela lê mudanças do Git, analisa imports com a AST, constrói um grafo reverso de dependências e executa os testes encontrados com pytest. A saída lista os arquivos alterados, os testes escolhidos, os tempos e um caminho do grafo que justifica cada seleção.

Requer Python 3.11+, Git e pytest. Instale as dependências e execute a suíte completa:

```sh
python -m pip install -r requirements.txt
python -m pytest
```

## O que o projeto oferece

- Leitura de alterações entre uma base Git e `HEAD`, além de alterações locais e arquivos Python novos não rastreados.
- Indexação AST dos arquivos Python em `src/` e `tests/`, incluindo imports absolutos e relativos.
- Grafo direcionado de imports e grafo reverso para descobrir quem depende de um módulo alterado.
- Busca em largura pelos dependentes e explicação textual do caminho até cada teste selecionado.
- Grafo de dependências construído como `networkx.DiGraph` e visualização HTML interativa automática via PyVis durante execuções `indexed` e `selective`.
- Exportação em PNG, DOT, JSON e GraphML para visualização ou integração com outras ferramentas.
- Execução seletiva com pytest, com execução completa de fallback quando a seleção não é confiável.
- Índice JSON persistente e versionado, carregado em mapas Python para consultas rápidas.
- Modos de execução completa, análise AST sem cache, consulta indexada e benchmark comparativo.
- Script Bash e workflow GitHub Actions de exemplo, com cache do índice entre execuções.

O índice também guarda nomes de classes e funções encontrados pela AST. A seleção atual, porém, é baseada nas arestas de imports entre arquivos.

## Como a seleção funciona

1. O analisador obtém os caminhos Python alterados a partir da base do diff e do estado local do Git.
2. A AST converte imports locais em arestas `importador -> dependência`, resolvendo níveis de imports relativos a partir do pacote do arquivo.
3. O grafo reverso permite percorrer de uma dependência alterada para seus importadores e, em seguida, para os testes dependentes.
4. A busca em largura registra um caminho explicativo para cada arquivo `test_*.py` selecionado.
5. Pytest executa apenas os arquivos selecionados. Se não há diff confiável ou nenhum teste relacionado, executa a suíte completa.

As alterações são filtradas para `.py`; uma mudança isolada em documentação ou configuração não resulta em uma seleção vazia silenciosa: o fallback executa a suíte completa.

Por padrão, os modos `indexed` e `selective` usam NetworkX para construir o `DiGraph` e PyVis para renderizar `.cache/dependency-graph.html`. Abra o HTML em um navegador: é possível ampliar, mover a visualização, arrastar nós e filtrar entre `Source` e `Tests`; passe o cursor sobre um nó para ver o caminho completo do arquivo. O JavaScript da visualização fica embutido no HTML, então não é necessário acessar CDN. Arquivos de teste aparecem como quadrados amarelos e arquivos de produção como pontos azuis. As arestas apontam do importador para a dependência (`arquivo -> arquivo importado`), enquanto a seleção percorre o grafo no sentido inverso. O relatório mostra a quantidade de nós e arestas e o local do arquivo gerado.

## Uso

Passe uma branch ou SHA disponível localmente como base do diff:

```sh
python tools/analyzer.py --mode indexed --base-ref origin/main
```

Opções disponíveis:

- `--mode full`: executa todos os testes.
- `--mode selective`: reconstrói o grafo a partir da AST em cada execução.
- `--mode indexed`: carrega ou atualiza `.cache/index.json` e é o modo padrão.
- `--mode benchmark`: compara os modos `full`, `selective` e `indexed`.
- `--base-ref REF`: usa `REF...HEAD` para identificar mudanças de commit.
- `--graph-output PATH`: altera o caminho do grafo exportado; padrão `.cache/dependency-graph.html`.
- `--graph-format html|dot|json|graphml`: escolhe o formato visual ou de intercâmbio; padrão `html`.
- `--repeat N`: número de repetições do benchmark, no mínimo 1.
- `--results DIR`: diretório para os resultados JSON e CSV do benchmark; padrão `benchmark/results`.

Sem `--base-ref`, a ferramenta consulta a variável `SELECTIVE_TEST_BASE` e variáveis comuns de CI. Em desenvolvimento local, também considera o diff do worktree e arquivos Python novos. Se não houver mudanças detectáveis, executa todos os testes.

O script Bash fixa o diretório raiz antes de invocar o analisador:

```sh
bash scripts/test-selective.sh
```

Ele usa `indexed` por padrão. Pode-se definir `SELECTIVE_TEST_BASE`, `SELECTIVE_TEST_MODE` ou `PYTHON`; argumentos adicionais são encaminhados ao analisador. Por exemplo:

```sh
SELECTIVE_TEST_BASE=origin/main bash scripts/test-selective.sh
```

O modo padrão já gera o HTML interativo. Para gerar JSON estruturado ou GraphML para abrir em ferramentas como Gephi:

```sh
python tools/analyzer.py --mode indexed --graph-format json --graph-output .cache/dependency-graph.json
python tools/analyzer.py --mode indexed --graph-format graphml --graph-output .cache/dependency-graph.graphml
```

O formato DOT continua disponível para Graphviz. O modo `full` apenas executa pytest e não constrói o índice nem exporta o grafo.

## Índice incremental

O índice persistido em `.cache/index.json` contém a versão do formato, identidades dos arquivos, arestas diretas e reversas e nomes de classes e funções. O primeiro uso analisa todos os arquivos Python de `src/` e `tests/`. Nas execuções seguintes, compara as identidades, reanalisa apenas arquivos novos ou alterados, remove arquivos excluídos e atualiza o grafo.

Para arquivos rastreados e limpos, a identidade é o blob SHA do Git, que permanece estável entre checkouts do CI. Para arquivos modificados localmente ou não rastreados, usa-se SHA-256 do conteúdo. O JSON é gravado por substituição atômica. Apague `.cache/index.json` para forçar uma reconstrução completa; o cache é gerado e não precisa ser versionado.

## Correções para execução confiável

 Caminhos `.pyc` não são tratados como fontes nem como testes.
- O diretório de execução do script Bash é sempre a raiz do repositório.

## CI

O workflow [`.github/workflows/selective-tests.yml`](.github/workflows/selective-tests.yml) executa em pushes, pull requests e disparos manuais. Ele usa Python 3.11, checkout com histórico completo, cache Actions para `.cache/index.json` e chama `scripts/test-selective.sh`.

O workflow fornece `SELECTIVE_TEST_BASE` com o SHA base do pull request ou com o commit anterior do push. Para outras pipelines, defina essa variável com uma referência que exista no clone, por exemplo `origin/main` ou um SHA. O analisador também reconhece `GITHUB_BASE_REF`, `CI_MERGE_REQUEST_DIFF_BASE_SHA` e `BITBUCKET_PR_DESTINATION_BRANCH`.

## Benchmark e fixtures

Compare tempo de análise e execução dos três modos:

```sh
python tools/analyzer.py --mode benchmark --repeat 5
```

Os resultados são exibidos no terminal e gravados em arquivos JSON e CSV. Para gerar fixtures de módulos:

```sh
python tools/generate_fixture.py --modules 100
```

O gerador cria arquivos em `generated/`; esse diretório ainda não faz parte do escopo do indexador, que analisa `src/` e `tests/`.

### Benchmark isolado com 10.000 testes

`tools/benchmark_scale.py` cria um projeto sintético dentro de um diretório temporário, inicializa um repositório Git descartável e remove todo o fixture ao terminar. Não escreve em `src/`, `tests/` ou no índice do projeto. O teste compara a suíte completa, seleção com parse AST sem índice e seleção com índice incremental aquecido:

```sh
python tools/benchmark_scale.py --tests 10000 --test-files 100 --affected-files 10 --repeat 3
```

Parâmetros configuráveis: `--tests`, `--test-files`, `--affected-files` e `--repeat`. A medição atual usa casos distribuídos uniformemente em arquivos; uma alteração simulada afeta 10 dos 100 módulos de teste. A seleção opera por arquivo, não por caso individual.

Na medição de referência em Windows, os tempos médios foram: suíte completa `7,45 s`; seleção sem índice `1,62 s`; seleção indexada e aquecida `1,35 s`. A construção inicial do índice levou `0,83 s`. Os modos seletivos executaram 1.000 dos 10.000 casos. Esses números descrevem somente este fixture e ambiente; a proporção de arquivos afetados, o custo dos testes, o sistema operacional e a frequência de reconstrução determinam o ganho em um projeto real. O primeiro índice é um custo de setup; os valores indexados representam atualizações posteriores.

## Limites e adaptação

A análise é estática e baseada em imports entre arquivos. Imports dinâmicos, reflexão e dependências escolhidas em runtime não são inferidos. Apesar de classes e funções terem seus nomes armazenados, chamadas de funções, métodos, herança e uso de símbolos não formam arestas do grafo. O projeto atualmente atende projetos Python com `src/`, `tests/`, arquivos de teste `test_*.py` e pytest.

Para outra linguagem, substitua a extração AST por um parser que resolva imports e módulos para caminhos de arquivo. Mantenha o formato do grafo e do índice ou adapte seus campos, e atualize a descoberta dos testes e o comando do runner, por exemplo TypeScript/Jest ou Java/JUnit.

Os testes da ferramenta podem ser executados isoladamente:

```sh
python -m pytest tests/test_analyzer.py
```
