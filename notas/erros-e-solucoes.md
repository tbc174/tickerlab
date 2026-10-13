# Erros e soluções

Todo erro resolvido vira uma entrada aqui. Formato: **sintoma, causa, solução**.

## Terminal abre com `(base)` e Python 3.14 em vez de `(.venv)` e 3.12.10
- **Causa:** o Conda ativa o ambiente `base` automaticamente, antes do `.venv`.
- **Solução:** `Ctrl+Shift+P`, `Python: Select Interpreter`, `.venv`; abrir um terminal novo. Se persistir, `conda deactivate` e `.\.venv\Scripts\Activate.ps1`.
- **Data:** 09/10/2026

## Pylance sublinha `dados.describe` / `dados.columns`: `"describe" is not a known attribute of "None"`
- **Sintoma:** o notebook roda normalmente (`dados.head()` mostra a tabela), mas o VS Code sublinha o uso de `dados` logo depois de `dados = yf.download(...)`.
- **Causa:** é aviso do Pylance (análise estática), não erro de execução. O `yf.download` é declarado como devolvendo `DataFrame | None`; como `dados` *poderia* ser `None`, o editor reclama de acessar atributos nele.
- **Solução:** validar o download logo depois da chamada. Além de calar o aviso, dá uma mensagem clara se o Yahoo falhar:
  ```python
  if dados is None or dados.empty:
      raise ValueError(f"Não consegui baixar dados de {ticker}")
  ```
- **Data:** 10/10/2026

## `streamlit run app.py` não roda: dois comandos na mesma linha
- **Sintoma:** o app não abre; o terminal mostra `SyntaxError: invalid syntax` apontando para a linha do `st.text_input`.
- **Causa:** o código do comentário `# TODO` foi colado **depois** do que eu já tinha escrito, na mesma linha: `ticker = st.text_input(...) st.text_input(...)`. Em Python, cada comando precisa da própria linha (ou de `;`).
- **Solução:** deixar só um `st.text_input` por linha, apagando o duplicado. Ler a mensagem do terminal inteira mostra o número da linha com problema.
- **Data:** 10/10/2026

## Resultado de cálculo dentro de `st.text_input`
- **Sintoma:** campos de texto estranhos aparecendo na tela e `retorno` virando texto, não série.
- **Causa:** usei `st.text_input("Retorno", value=ind.calcular_retorno_diario(fechamento))`. O `st.text_input` cria um **campo de digitação**; não é para guardar contas.
- **Solução:** chamar a função e guardar numa variável: `retorno = ind.calcular_retorno_diario(fechamento)`. Cada função recebe o argumento certo (`retorno` ou `fechamento`).
- **Data:** 10/10/2026

## `streamlit` solto no terminal usa o Conda, não o `.venv`
- **Sintoma:** `which streamlit` aponta para `anaconda3\Scripts`; pode faltar biblioteca ou ser outra versão.
- **Causa:** o Conda `base` vem antes do `.venv` no `PATH` (mesma origem do erro do `(base)`).
- **Solução:** rodar com o Python do ambiente: `python -m streamlit run app.py`, com `(.venv)` no começo do terminal.
- **Data:** 10/10/2026

## `fillna(0)` no retorno diário distorce a volatilidade
- **Sintoma:** a volatilidade das minhas funções ficava um pouco menor do que a da conferência.
- **Causa:** `pct_change().fillna(0)` troca o `NaN` do primeiro dia por 0, e esse 0 entra no desvio padrão.
- **Solução:** deixar o `NaN` (o `std()` já o ignora): `return fechamento.pct_change()`.
- **Data:** 10/10/2026

## Relatórios de proventos da CVM sumiam da coleta de eventos
- **Sintoma:** nenhum evento do tipo "Relatório Proventos" entrava no banco, mesmo existindo no arquivo da CVM.
- **Causa:** no arquivo IPE da CVM, essas linhas vêm com a coluna `Protocolo_Entrega` **vazia**; o coletor descartava toda linha sem protocolo.
- **Solução:** quando o protocolo vier vazio, usar o número que está no próprio link do documento (`numProtocolo=...&numVersao=...`), como `rad-1477025`. Entraram ~1.400 relatórios de proventos que se perdiam. Lição: conferir os dados reais antes de supor que uma coluna sempre vem preenchida.
- **Data:** 11/10/2026

## `StreamlitAPIException` ao mudar o valor de um campo depois de desenhá-lo
- **Sintoma:** ao criar uma lista no Research, o código tentava abrir a lista nova trocando `st.session_state["research_lista"]`, e o Streamlit recusa.
- **Causa:** o valor de um campo com `key` só pode ser mudado **antes** de o campo aparecer na tela naquela execução (ou dentro de um `on_click`).
- **Solução:** guardar um "pedido pendente" (`research_lista_pendente`) e aplicá-lo no começo da próxima execução, antes do `st.selectbox`.
- **Data:** 11/10/2026

## Testes de migração quebravam a cada migração nova
- **Sintoma:** `test_migracao_0006_vai_e_volta` falhou depois de criar a 0007 (e de novo com a 0008).
- **Causa:** o teste descia "uma versão" (`migrar_para("-1")`) a partir da última; com uma migração nova, "-1" passou a desfazer outra.
- **Solução:** função `desfazer_ate("0005")` em `src/banco/conexao.py`, que desce até uma versão exata; os testes usam o número da versão, não uma contagem.
- **Data:** 11/10/2026

## Página nova acusava "não consegui ler os eventos" no modo local
- **Sintoma:** a página Acontecimentos mostrava erro ao rodar sem conta, num banco SQLite antigo.
- **Causa:** o app abre o banco sem aplicar as migrações (no servidor, quem aplica é o contêiner ao subir); no banco local antigo, a tabela `eventos` não existia.
- **Solução:** tratar "tabela não existe" (`OperationalError`/`ProgrammingError`) como "eventos ainda não coletados", com a dica de rodar `python -m scripts.atualizar_eventos` (que também prepara o banco).
- **Data:** 11/10/2026

## Coleta da SEC ficava mais lenta a cada empresa (7,5 min para 500)
- **Sintoma:** a primeira coleta dos eventos dos EUA começava rápida e ia ficando lenta; cada empresa demorava mais que a anterior.
- **Causa:** `gravar_eventos` lia **todos** os protocolos já guardados da fonte para saber o que era novo. Gravando empresa por empresa, a leitura crescia a cada uma (500 empresas × milhares de linhas).
- **Solução:** ler só os protocolos do lote que está sendo gravado (`protocolo IN (...)`, em pedaços de 5.000, porque o SQLite limita o número de parâmetros de uma consulta).
- **Data:** 11/10/2026

## A coleta de um mercado apagaria o mapa de tickers do outro
- **Sintoma (evitado antes de acontecer):** `gravar_tickers` apagava a tabela inteira antes de gravar o mapa novo; com a SEC, a coleta da CVM das 7h apagaria as empresas dos EUA (e vice-versa).
- **Solução:** cada origem apaga só as suas linhas (`origem="sec"` mexe nas que começam com `CIK`; a CVM, nas outras). Teste: `test_mapa_da_sec_e_o_da_cvm_nao_se_apagam`.
- **Data:** 11/10/2026

## 13D/13G da Berkshire apareciam como se fossem sobre a própria Berkshire
- **Sintoma (achado antes de publicar):** a lista de documentos de uma empresa na SEC traz os 13G entregues **sobre** ela e também os que **ela** entrega sobre outras (a Berkshire tem dezenas).
- **Causa:** a lista (`submissions`) não diz o papel da empresa no documento; nem o número do protocolo resolve (os dois tipos usam o mesmo agente de entrega).
- **Solução:** para cada 13D/13G novo, ler o cabeçalho do documento (`.hdr.sgml`), que traz a empresa-alvo (`SUBJECT-COMPANY`), e guardar só quando ela é a própria empresa.
- **Data:** 11/10/2026

## Um Form 4 que falha travava todos os outros da mesma empresa
- **Sintoma:** no teste, a coleta pulava a Apple inteira quando um único Form 4 não baixava.
- **Causa:** o erro de rede de um documento subia até o laço das empresas.
- **Solução:** cada Form 4 tem o próprio `try`; o que falha não é marcado como lido e é tentado de novo no dia seguinte, sem travar os outros.
- **Data:** 11/10/2026

## Número do NumPy no PostgreSQL (`int64`)
- **Cuidado:** valores tirados de um DataFrame (`to_dict`) vêm como `numpy.int64`, que o psycopg não sabe gravar (o SQLite dos testes aceita, então o erro só apareceria em produção).
- **Solução:** converter antes de gravar (`valor.item()`), como faz `_python` em `src/banco/negociacoes.py`.
- **Data:** 11/10/2026

## Os 12 meses supunham ano fiscal igual ao do calendário
- **Sintoma (achado ao trazer os EUA):** a regra "o anual do ano anterior ao trimestre" pegaria, para o Walmart (ano fiscal termina em janeiro), o balanço anual de dois anos antes.
- **Solução:** usar o último balanço anual **anterior** ao trimestre e a no máximo 371 dias dele (53 semanas). Para as empresas da B3 o resultado é o mesmo. Teste: `test_walmart_usa_o_anual_de_janeiro_e_os_minoritarios`.
- **Data:** 11/10/2026

## Gravar o setor de uma empresa apagava os de todas
- **Sintoma (evitado antes de acontecer):** `gravar_setores` apagava a tabela inteira; com a SEC gravando empresa por empresa, cada uma apagaria as outras, e a coleta da CVM apagaria as dos EUA.
- **Solução:** a CVM apaga só as suas linhas; os EUA usam `gravar_setor` (uma empresa). Mesmo cuidado já tomado com o mapa de tickers.
- **Data:** 11/10/2026

## Carteira dos fundos: o número de fundos "caía pela metade" sem ninguém vender
- **Sintoma (achado antes de publicar):** junho de 2026 tinha 6.653 fundos com ações no arquivo da CVM; julho e agosto, ~3.400; setembro (ainda chegando), 1.966. Contar fundos crus mostraria saídas em massa que não aconteceram.
- **Causa:** um fundo pode manter posições em **sigilo por até 90 dias** (elas aparecem depois), e o arquivo do mês mais recente ainda está sendo completado.
- **Solução:** guardar a cobertura de cada mês (quantos fundos informaram), mostrar a **fatia** dos que informaram e comparar só meses seguidos com cobertura parecida (≥ 85%); o mês mais novo incompleto fica de fora (`src/detentores.py`).
- **Data:** 11/10/2026

## 13F estourava a memória do contêiner
- **Sintoma:** ler a tabela de posições do 13F (400 MB descompactada) chegava a ~360 MB de memória, perto do limite do contêiner (768 MB, dividido com o app).
- **Solução:** ler em pedaços de 200 mil linhas, filtrar só as ações do S&P 500 e guardar cada pedaço em formato compacto (categorias e números); pico caiu para ~144 MB, mesmo resultado.
- **Data:** 11/10/2026

## Regex lê "R$ 500 milhões" como "R$ 500 mil"
- **Sintoma:** no resumo dos fatos relevantes (R5), um valor de milhões saía mil vezes menor.
- **Causa:** numa alternativa `(?:mil|milhão|milhões)` a regex testa as opções na ordem escrita e para na primeira que casa: "mil" casa com o começo de "milhões".
- **Solução:** pôr as palavras mais longas primeiro e exigir o fim da palavra: `(?:milhões|milhão|mil)\b`. Um teste com o valor real pegou o erro.
- **Data:** 12/10/2026

## `ORDER BY ... DESC` põe a data vazia em primeiro no PostgreSQL
- **Sintoma:** a leitura "mais recente" de um 10-K poderia ser uma sem data.
- **Causa:** no PostgreSQL, `NULL` conta como maior que tudo, então vem primeiro em ordem decrescente (no SQLite, vem por último; por isso os testes locais não mostram).
- **Solução:** `coluna.desc().nulls_last()` no SQLAlchemy.
- **Data:** 12/10/2026

## Duas funções com o mesmo nome no `app.py`
- **Sintoma:** a página Admin mostrava "Criada em: coletado em 10/10/2026 às 14:00".
- **Causa:** havia duas `def _quando(...)`; em Python a segunda substitui a primeira no arquivo inteiro, e a da Newsletter escrevia "coletado em".
- **Solução:** a da Newsletter foi para `src/edicao.py` com um nome próprio (`quando_foi_coletado`). Arquivos menores (a etapa 4 da qualidade) evitam isso.
- **Data:** 12/10/2026

## `StreamlitValueAssignmentNotAllowedError` num botão novo
- **Sintoma:** a página Minha carteira quebrava ao abrir com um botão de chave `carteira_research_...`.
- **Causa:** o `manter_estado()` do app reatribui todo campo cujo nome começa com `carteira_` (para a página de estratégia de carteiras não perder o estado); botões e envio de arquivo não podem ser reatribuídos.
- **Solução:** usar outro prefixo (`minha_carteira_`). Antes de escolher a chave de um campo, conferir `PREFIXOS_QUE_SOBREVIVEM_A_TROCA_DE_PAGINA`.
- **Data:** 12/10/2026

## CI para antes do primeiro teste: `ImportError: libEGL.so.1`
- **Sintoma:** no GitHub Actions, o passo dos testes termina com `INTERNALERROR` e código 3, sem rodar nenhum teste; no PC (Windows) a suíte passa.
- **Causa:** o `pytest-qt` importa o PySide6 (Qt) assim que o pytest começa, mesmo que os testes do painel sejam pulados fora do Windows. O Qt precisa de bibliotecas gráficas do sistema (`libEGL` e outras) até no modo sem tela ("offscreen"), e o Ubuntu do GitHub não as traz.
- **Solução:** um passo no `.github/workflows/testes.yml` antes dos testes: `sudo apt-get install -y --no-install-recommends libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3`. Lição: erro que só aparece no Linux do CI se vê no log do passo (`gh run view --log-failed`), não no PC.
- **Data:** 12/10/2026

## Coleta da SEC morreu no meio com "saída 137" (o deploy recriou o contêiner)
- **Sintoma:** a marca `eventos-sec.falha` com "saída 137"; o log para no meio, sem mensagem de erro.
- **Causa:** 137 é processo morto à força. Não foi falta de memória (o contêiner não marcou `OOMKilled`): as coletas rodam com `docker exec` dentro do contêiner do app, e um deploy (merge na `main` às 7h16) recriou o contêiner às 7h23, no meio da coleta.
- **Solução:** reconhecer pela hora: comparar a hora da falha com o `StartedAt` do contêiner (`docker inspect`) e com o log do deploy. Correção (#51): as tarefas seguram uma trava compartilhada (`/tmp/tickerlab-tarefas.lock`) e o deploy só implanta se pegar a trava sozinho; senão, tenta no minuto seguinte. A coleta perdida foi rodada de novo à mão.
- **Data:** 12/10/2026

## CI com `pytest -n auto` quase não ficou mais rápido
- **Sintoma:** com os testes em paralelo, o CI caiu só de ~9 para ~5 min, embora no PC fossem 2,5 min.
- **Causa:** o `-n auto` do pytest-xdist conta só os núcleos **físicos**: a máquina do GitHub tem 4 lógicos e 2 físicos, então rodou com 2 processos. E o `--dist loadfile` deixa um arquivo pesado segurando o fim.
- **Solução:** `-n logical --dist loadgroup`, com os testes que usam o PostgreSQL compartilhado marcados como um grupo (`pytestmark = pytest.mark.xdist_group("postgres")`). Testes em ~3 min.
- **Data:** 12/10/2026

## `Bad substitution` num comando `sh -c` dentro de um contêiner
- **Sintoma:** o comando parou logo no começo com `sh: 1: Bad substitution` (nada foi alterado).
- **Causa:** o `sh` da imagem é o **dash**, que não entende recursos do bash como `${f/antes/depois}`.
- **Solução:** no `sh`, escrever os nomes por extenso (`cp kuma.db kuma.db.antes-$TS`) ou chamar `bash -c` quando a imagem tiver bash.
- **Data:** 12/10/2026

## Vigia "achava" um processo que já tinha terminado
- **Sintoma:** um laço que esperava a coleta terminar continuava dizendo "rodando", mas a coleta já tinha acabado.
- **Causa:** `pgrep -f "rodar-tarefa.sh eventos-sec"` também encontrava o próprio comando de busca, porque o texto procurado estava na linha de comando do SSH que rodava o `pgrep`.
- **Solução:** usar um colchete no padrão (`pgrep -f "[r]odar-tarefa.sh eventos-sec"`), que acha o processo mas não a si mesmo, ou olhar o resultado (a marca `.ok`/`.falha`) em vez do processo.
- **Data:** 12/10/2026

## Primeira carga das séries macro: `ReadTimeout` no SGS do Banco Central
- **Sintoma:** a etapa `bcb-sgs` do `scripts/atualizar_series_macro.py` falhou na primeira rodada (desde 2010), no PC e no servidor, com `Read timed out. (read timeout=20)` na série 432; numa segunda rodada passou.
- **Causa:** sem cache, o SGS demora numa consulta longa: 26 s para 7 anos da série 432 e 18 s para 9 anos da série 11. Repetida, a mesma consulta volta em menos de 1 s (por isso a segunda rodada passava). O leitor desistia em 20 s.
- **Primeira tentativa:** `bcb.TEMPO_LIMITE` em 60 s (#77), com teste de regressão. Não bastou: com 60 s apareceu o erro de baixo.
- **Causa de verdade:** o próprio servidor do BC corta em ~30 s e devolve uma página HTML "Requisição inválida!" **com status 200** (o `json()` falha com `Expecting value`). Visto pelo acervo: o original guardado daquela coleta era o HTML. A janela de 9 anos (`ANOS_POR_CONSULTA`) é que era longa demais sem cache.
- **Solução:** janelas de 3 anos (#83): a mesma série 432 volta em 2 a 5 s por janela. O CDI do app (`src/cdi.py`) usa o mesmo desenho (9 anos, 20 s) e pode falhar igual num período longo: ficou para o Tiago decidir.
- **Data:** 13/10/2026

## `pwsh -File script.ps1 -Prs 72,73` virou o PR "7273"
- **Sintoma:** o script de merge em lote parou com `Could not resolve to a PullRequest with the number of 7273`.
- **Causa:** com `-File`, os argumentos chegam como texto; `"72,73"` convertido para `int[]` vira um número só (a vírgula é lida como separador de milhar).
- **Solução:** chamar com `pwsh -Command "& script.ps1 -Prs 72,73"`, que interpreta a lista do jeito do PowerShell. Nada tinha sido publicado.
- **Data:** 13/10/2026

## Script bash termina com erro depois de dar certo: `parcial: unbound variable`
- **Sintoma:** o recebedor do backup gravava o arquivo e mesmo assim saía com erro.
- **Causa:** o `trap ... EXIT` usava uma variável `local` da função; quando o script termina, a função já acabou, a variável não existe e o `set -u` derruba a saída.
- **Solução:** a variável do arquivo pela metade é global, criada vazia no começo, e o `trap` é armado uma vez só. Pego no teste numa pasta temporária, antes de instalar.
- **Data:** 13/10/2026
