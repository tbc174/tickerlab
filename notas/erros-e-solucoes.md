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
- **Solução:** janelas de 3 anos (#83): a mesma série 432 volta em 2 a 5 s por janela. O CDI do app (`src/cdi.py`) usa o mesmo desenho (9 anos, 20 s) e podia falhar igual num período longo (corrigido no fim da tarde, ver abaixo).
- **E um 502 isolado:** na carga seguinte, 1 de 35 consultas voltou 502 (repetida, respondeu em 2,6 s) e derrubou as séries que vinham depois. O leitor do BC agora tenta de novo até 2 vezes (5 s e 15 s) só em erro passageiro (5xx, timeout, conexão); 4xx e página que não é JSON não repetem (#84).
- **Nem 3 anos bastam com o cache frio (13/10, tarde):** ao corrigir o CDI, a janela 2020–2023 da série 12 levou 30,9 s e voltou com a mesma página HTML; repetida, respondeu em 3,8 s (numa segunda conferência, 2021–2024: 31,9 s e depois 1,4 s). Agora a página que não é JSON também conta como passageira e é tentada de novo; 4xx continua sem repetir. O CDI do app passou a usar o mesmo leitor (`bcb.baixar_sgs`, fora de `bcb.SERIES` para a coleta do acervo não pegá-lo): janelas de 3 anos, 60 s e as novas tentativas.
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

## Site no ar com o visual "desmontado" logo depois do deploy
- **Sintoma:** HTML novo com o estilo antigo (fundo errado, botão do tema virou um quadrado cinza).
- **Causa:** a Cloudflare guarda `estilo.css`, `site.js` e as imagens por 4 horas (`cf-cache-status: HIT`,
  `max-age=14400`); o HTML vem novo, o CSS vem velho.
- **Solução:** o gerador do site põe `?v=<hash do conteúdo>` no endereço do CSS e do JS (há teste). Para
  imagens trocadas com o mesmo nome: "Purge Everything" no painel da Cloudflare (Caching → Configuration).
- **Data:** 13/10/2026

## `st.html(..., unsafe_allow_javascript=True)` não executa o script
- **Sintoma:** o `<script>` não aparece na página e nada roda, sem erro no console.
- **Causa:** o Streamlit passa o HTML pelo DOMPurify, que apaga o elemento inteiro se o texto tiver `<`
  seguido de letra, `/` ou `!`, até num comentário (ex.: `stActiveTheme-<página>-v2`).
- **Solução:** nada de "menor que" colado em letra no JavaScript enviado ao `st.html` (há teste em
  `tests/test_tema_do_app.py`).
- **Data:** 13/10/2026

## Streamlit local roda o código antigo de `src/` depois de editar
- **Sintoma:** `TypeError: script() got an unexpected keyword argument` na tela, embora os testes passem.
- **Causa:** o `streamlit run` recarrega o `app.py` a cada execução, mas guarda os módulos de `src/` já
  importados.
- **Solução:** reiniciar o `streamlit run` depois de mudar a assinatura de uma função em `src/`.
- **Data:** 13/10/2026

## Conferência "verde" que estava vermelha: `ruff format --check | tail -1`
- **Sintoma:** "1 file would be reformatted" e o comando seguinte rodou mesmo assim; o CI quebrou depois.
- **Causa:** num encadeamento com `&&`, o código de saída de um `| tail` é o do `tail`, não o do `ruff`.
- **Solução:** guardar a saída num arquivo e testar o código (`ruff format --check ... > f.txt; echo $?`)
  antes do push, ou rodar o `ruff format` sem `--check` e conferir o `git status`.
- **Data:** 13/10/2026

## O ITR inteiro da CVM não cabe no contêiner do app (741 MB na leitura)
- **Sintoma:** medindo a tarefa das regras de qualidade no PC, ler o ITR inteiro (`ler_contas`) levou o processo a 741 MB; o contêiner do app tem 768 MB, dividido com o Streamlit.
- **Causa:** o arquivo tem ~1,2 milhão de linhas lidas como texto, com todas as demonstrações (DFC inclusive), e a tarefa precisava de dois arquivos ao mesmo tempo.
- **Solução:** ler só o que as regras usam (`so_as_das_regras=True`: BPA, BPP e o 1º nível da DRE), segurar um arquivo inteiro por vez (dos outros, só as contas principais) e rodar a tarefa num contêiner próprio (`docker run --rm --memory 1500m`), como a coleta do IEX. Pico: 665 MB.
- **Data:** 13/10/2026

## O SHA-256 do pacote do ENET muda a cada download
- **Sintoma:** o mesmo documento do ENET (DFP 2022 v1 do BRB) baixado duas vezes deu dois SHA-256 diferentes.
- **Causa:** o ENET monta o zip na hora; o PDF dentro dele leva a data e a hora do download no nome. O XML do documento sai idêntico.
- **Solução:** registrar e guardar o **XML limpo** (sem o PDF e sem os dados de quem entregou, `base.enet.limpar_xml`), que é estável: o mesmo documento vira um arquivo só no acervo (47 a 60 KB, contra 13 a 17 MB do pacote).
- **Data:** 13/10/2026

## `gh pr merge` falhou e o comando seguinte apagou o ramo, fechando o PR
- **Sintoma:** o merge do #102 falhou por conflito (outra sessão tinha mexido no site), mas a linha seguinte do mesmo comando apagou o ramo local e o remoto; o GitHub fechou o PR.
- **Causa:** comandos encadeados com `;` seguem mesmo quando o anterior falha.
- **Solução:** recriar o ramo pelo commit (`git checkout -B ramo <sha>`), resolver o conflito, mandar de novo e `gh pr reopen`. Daqui em diante, limpeza só dentro de `if gh pr merge ...; then ...; fi`.
- **Data:** 13/10/2026

## Regra boa "falha" no teste contra o acaso com dados sintéticos de tendência
- **Sintoma:** num teste da ficha "Foi sorte?", uma regra de tendência em dados feitos com altas e quedas de 150 dias tinha p-valor de 14% no teste contra o acaso, como se fosse sorte.
- **Causa:** o teste contra o acaso desloca a posição no tempo. Com tendências de duração **fixa**, o deslocamento de um ciclo inteiro (300 dias) realinha a posição com as tendências, e várias versões "ao acaso" acertam tanto quanto a regra.
- **Solução:** sortear a duração de cada tendência (`rng.integers(80, 260)`). Dado sintético periódico engana testes que deslocam no tempo.
- **Data:** 13/10/2026

## Duas sessões criam a mesma ADR (dois arquivos `0044-...`)
- **Sintoma:** a pasta de decisões ficou com dois arquivos 0044 diferentes, de sessões abertas ao mesmo tempo.
- **Causa:** cada sessão conferiu o último número livre e criou a sua antes de ver a da outra.
- **Solução:** conferir a pasta logo antes de criar; havendo repetição, renumerar a ADR que ninguém cita ainda para o próximo número livre e corrigir as referências dela.
- **Data:** 13/10/2026

## `git worktree remove` falha com "Invalid argument" depois da suíte
- **Sintoma:** ao apagar a cópia de trabalho, o Git solta a cópia mas a pasta fica com `trader/interface/tipografia/Manrope-VariableFont_wght.ttf`; `rm` diz "Device or resource busy".
- **Causa:** um processo da suíte (a interface do Trader carrega essa fonte) ainda segura o arquivo no Windows.
- **Solução:** `git worktree prune` para o Git esquecer a cópia; a pasta sai depois de reiniciar o PC (só tem arquivos que já estão no Git).
- **Data:** 13/10/2026

## Regra "salto de mais de 30%" disparava num salto de exatamente 30%
- **Sintoma:** de 200 para 140 é uma queda de exatamente 30%, mas a regra de qualidade da base de cripto a apontava como "mais de 30%".
- **Causa:** em ponto flutuante, `1 - 140/200` dá `0.30000000000000004`, um pouco acima de `0.30`. O mesmo com `510/500 - 1` contra 2%.
- **Solução:** comparar sem dividir: `abs(novo - velho) > LIMITE * velho` (`60 > 60.0` é falso). Limite de porcentagem em ponto flutuante merece um teste no valor exato do limite.
- **Data:** 13/10/2026

## `pd.to_datetime` falha com horas em formatos misturados
- **Sintoma:** `ValueError` do `strptime` ao converter uma lista com `"2024-01-01 08:00"` e `"2024-01-01 23:59:59"`.
- **Causa:** o pandas deduz o formato pelo primeiro texto (sem segundos) e recusa os que não seguem esse formato.
- **Solução:** `pd.to_datetime(textos, utc=True, format="mixed")`, ou escrever todos no mesmo formato.
- **Data:** 13/10/2026

## GDELT responde texto em vez de JSON
- **Sintoma:** o pedido ao GDELT devolve "Please limit requests to one every 5 seconds..." no lugar do JSON, e voltou a bloquear mesmo com 6 s entre dois pedidos de teste.
- **Causa:** o GDELT aceita um pedido a cada 5 segundos por endereço e conta os pedidos seguidos de quem já passou do limite.
- **Solução:** na coleta, um dia por pedido, pausa de 6 s depois de **cada** pedido e limite de dias por rodada; resposta que não é JSON conta como **falha** (devolve 1), nunca como "dia sem notícia". Nos testes, nada de rede.
- **Data:** 13/10/2026

## Números em quadradinhos (▯▯▯) numa tabela do PDF, depois de uma seta ▲
- **Sintoma:** no PDF da carteira ("Cada ativo sozinho") e da comparação, Volatilidade, Maior queda e Sharpe saíam como quadradinhos; o leitor de PDF extraía caracteres de controle (`\x1c#\x1a`). A coluna com a seta ▲ saía certa.
- **Causa:** defeito do fpdf2 2.8.9. A Manrope não tem ▲ ▼ ■, então esses caracteres vêm da fonte reserva (JetBrains Mono). Numa célula com a reserva, a troca de fonte fica dentro do `q … Q` da célula, que o PDF desfaz no fim; mesmo assim o fpdf2 passa a achar que a fonte já está declarada. A célula seguinte, na mesma fonte, não declarava a fonte de novo e saía desenhada com a de antes.
- **Solução:** `RelatorioPDF._render_styled_text_line` (`src/relatorio_pdf.py`) marca `current_font_is_set_on_page = False` depois de cada linha de texto, o que obriga o fpdf2 a declarar a fonte de novo. Teste de regressão em `tests/test_relatorios_propriedades.py`, e todo teste de PDF procura caracteres de controle no texto. Achado por um teste de propriedade com 300 exemplos (PR #126).
- **Data:** 13/10/2026

## Teste de propriedade que passa sem testar nada
- **Sintoma:** o teste do PDF da comparação passava rápido demais.
- **Causa:** o gerador do Hypothesis quase sempre criava ativos com poucos dias em comum, então o teste só conferia a recusa ("poucos pregões") e o PDF quase nunca era gerado (4,5% dos exemplos).
- **Solução:** marcar cada ramo com `hypothesis.event(...)`, rodar com `pytest --hypothesis-show-statistics` e ajustar o gerador até os dois ramos aparecerem (o Hypothesis prefere números pequenos: o ramo de cima entra duas vezes no `st.one_of`).
- **Data:** 13/10/2026

## `novo/` "está velho" no CI, mas igual no PC (uma linha em branco a mais)
- **Sintoma:** o passo "App em React (novo/ igual ao build)" do CI falhava só no `novo/index.html`; no PC, o build saía igual ao que estava no Git.
- **Causa:** o Git no Windows tirou o `web/app/index.html` com CRLF. O Vite tira a tag `<script>` da página antes da nossa normalização e, com CRLF, sobrava uma linha em branco; no CI (Linux, LF) não sobra.
- **Solução:** a normalização para LF roda com `transformIndexHtml: { order: "pre" }` (antes do Vite), e o `.gitattributes` tira `web/**` sempre com LF (`novo/**` fica `-text`). Para reproduzir o CI no PC: uma cópia com `core.autocrlf=false` e `npm run app` nela.
- **Data:** 13/10/2026

## O JavaScript arredonda diferente do Python (12,125 → "12,13" contra "12,12")
- **Sintoma:** o mesmo número saía com a última casa diferente na tela nova (React) e no Streamlit.
- **Causa:** no empate exato, o Python arredonda para o par e o `toFixed` do JS, para cima. E nem todo "…5" é empate: 2,675 vale 2,67499999… em binário (os dois mostram 2,67), mas `2.675 * 1000` dá 2675 e parecia empate.
- **Solução:** `web/src/app/formatar.ts` só trata como empate o número que é múltiplo exato de 1/8 (para 2 casas; multiplicar por potência de 2 é exato em binário) e arredonda para o par. Os casos vêm do Python (`src/formatos.py`, `web/conteudo/formatacao.json`) e o teste confere cada um.
- **Data:** 13/10/2026

## Teste acusa "preço na resposta da API" sem haver preço
- **Sintoma:** `test_nenhuma_resposta_traz_a_serie_de_precos` falhou ao entrar a curva em base 100 na visão geral.
- **Causa:** o teste procurava o preço como pedaço de texto: "48.0" (um fechamento) aparecia dentro de "148.0920..." (um valor em base 100).
- **Solução:** comparar números inteiros da resposta (`re.findall` de números) com os preços. Um preço vazado de verdade continua sendo pego.
- **Data:** 13/10/2026

## Teste do React não acha o que está na tela (Testing Library)
- **Sintoma:** `within(main).findByRole(...)` esgotava o tempo, mas a tela estava certa.
- **Causa:** o teste guardou o `<main>` do aviso "Carregando"; quando a configuração da API chega, o React troca a moldura inteira e aquele `<main>` sai da página.
- **Solução:** esperar algo da tela final (o menu "Telas") e só então pegar o `<main>`. Aumentar o tempo de espera não resolve.
- **Data:** 13/10/2026

## Planilha da B3 com "1.000" em texto vira 1, e não mil
- **Sintoma:** um teste da movimentação com a quantidade `"1.000"` (texto) leu 1 ação.
- **Causa:** `numero_brasileiro` (`src/carteira_b3.py`) só tratava o ponto como milhar quando havia vírgula (`"1.234,56"`); sem vírgula, `float("1.000")` é 1,0. Afetava também a planilha de posição enviada em CSV.
- **Solução:** ponto seguido de grupos de exatamente três dígitos (`1.000`, `12.345.678`) é milhar; `"30.5"` continua 30,5. Teste com a tabela de casos em `tests/test_carteira_b3.py`.
- **Data:** 13/10/2026

## AppTest: "`st.session_state['...']` is read-only" com dois `st.file_uploader` na página
- **Sintoma:** depois de pôr um segundo campo de arquivo na Carteira da B3, os testes que ligavam o exemplo com `app.toggle(...).set_value(True).run()` passaram a falhar com essa mensagem, apontando para o `st.file_uploader`.
- **Causa:** o AppTest reenvia o estado de todos os campos que já apareceram; o campo de arquivo não aceita valor vindo de fora. Com um campo só, ligar o exemplo o tirava da tela; com dois, um deles continuava lá.
- **Solução:** nos testes, ligar o exemplo **antes** de abrir a página (`app.session_state["carteira_b3_exemplo"] = True` e depois `ir_para`), para que ninguém interaja depois que os campos aparecem. Em uso real, os dois campos funcionam normalmente.
- **Data:** 13/10/2026

## `sed` troca `\U`, `\t` e `\a` num caminho do Windows por outra coisa
- **Sintoma:** uma substituição com `sed` gravou `C:SERS<tab>IAGOPROJETOS...` no lugar de `C:\Users\tiago\projetos\...`.
- **Causa:** no texto de substituição do GNU sed, `\U` deixa o resto em maiúsculas, `\t` vira tabulação e `\a` vira um caractere de controle. O mesmo acontece dentro de `"..."` no Python (`\U` é escape de Unicode).
- **Solução:** para trocar texto com barras invertidas, usar um script Python que monta a barra com `chr(92)` (ou string crua `r"..."`), e conferir o resultado depois.
- **Data:** 13/10/2026

## Ações emprestadas (aluguel) viravam venda no custo médio
- **Sintoma:** com a movimentação real, o custo médio de um FII mostrava só as cotas compradas depois de julho (1.300), quando a pessoa tinha 10.505; o custo total caía de ~R$ 100 mil para ~R$ 12,8 mil.
- **Causa:** ao emprestar as ações, a B3 escreve uma "Transferência - Liquidação" de **saída sem valor** (mais um par "Transferência" e uma linha "Empréstimo" no mesmo dia). O leitor tratava toda liquidação de saída como venda; vendendo "tudo", o médio recomeçava na compra seguinte.
- **Solução:** toda venda traz dinheiro. Liquidação sem valor não é compra nem venda: a saída fica fora das contas, com aviso na tela, e uma entrada sem valor depois de uma saída do mesmo ativo é a volta. Entrada sem valor sem saída antes continua como compra sem valor (custo incompleto). Teste de regressão com as 4 linhas copiadas da planilha real e valores inventados.
- **Data:** 13/10/2026

## PR vira "conflito" no GitHub sem que o código conflite (`novo/` e `site/`)
- **Sintoma:** o PR do relatório da empresa ficou `CONFLICTING` duas vezes em uma hora, sem nenhum arquivo de código em comum com os PRs da `main`; o CI nem dispara num PR em conflito.
- **Causa:** `novo/` (app em React) é um pacote minificado gerado e guardado no Git (o VPS não tem Node), com nome de arquivo que muda a cada build, e ele empacota `web/conteudo/paginas.json`. Todo PR que mexe numa página ou no React regrava os mesmos arquivos; o primeiro a entrar deixa os outros em conflito. Rebase não resolve: reescreve o ramo e exige push forçado (proibido pela trava).
- **Solução:** `python -m scripts.juntar_main`: merge da `main` no ramo; conflito só em pasta gerada (`site/`, `novo/`, `web/conteudo/`) é resolvido partindo da versão da `main` e rodando todos os geradores por cima; conflito em código desfaz o merge e para. Depois, `git push` comum. Regra no `CLAUDE.md` (Git e GitHub).
- **Detalhe:** numa cópia criada antes da regra `web/** eol=lf` do `.gitattributes`, o `web/app/index.html` tinha CRLF e o build do Windows punha uma linha em branco a mais no `novo/index.html` (o CI recusaria). Cópia nova (`git worktree add`) já sai com LF.
- **Data:** 13/10/2026

## Duas sessões criam a migração com o mesmo número
- **Sintoma:** depois de mesclar a `main` no ramo do Pulse, o Alembic acusou duas "cabeças" (`alembic heads` com duas revisões): a `0030_pulse.py` do ramo e a `0030_relatorio_empresa.py` que outra sessão tinha acabado de mesclar.
- **Causa:** cada sessão escolhe o próximo número olhando a `main` do momento em que começa; duas sessões em paralelo escolhem o mesmo.
- **Solução:** quem entra por último renumera: o arquivo, `revision` e `down_revision` (a do Pulse virou `0031`, apontando para a `0030`), e o nome do teste da migração. Conferir com `alembic heads` (uma linha só) e avisar no quadro de sessões o número usado, para a próxima sessão já pegar o seguinte.
- **Data:** 13/10/2026

## pyright numa cópia de trabalho não acha os pacotes
- **Sintoma:** numa cópia criada com `git worktree add` (`analise-acoes-NOME`), o pyright acusava `Import "streamlit" could not be resolved` em todo arquivo.
- **Causa:** a cópia não tem `.venv` própria; o pyright procura o ambiente dentro da pasta.
- **Solução:** apontar para o Python da cópia principal: `pyright --pythonpath "C:/Users/tiago/projetos/analise-acoes/.venv/Scripts/python.exe" src telas scripts`.
- **Data:** 13/10/2026

## Página nova no app deixa o `novo/` (React) velho
- **Sintoma:** no PR do Diário de Teses (#177), o job "web (React)" do CI falhou com `novo/ está velho: rode 'npm run app' em web/ e faça o commit`, embora o PR não mexesse no React.
- **Causa:** o app em React lê `web/conteudo/paginas.json`. Uma página nova em `src/paginas.py` muda esse arquivo (a trava do commit regenera), e o build guardado em `novo/` muda junto (outro nome do `assets/index-*.js`). A trava regenera o `web/conteudo/` e o `site/`, mas não o `novo/`.
- **Solução:** depois de mudar `src/paginas.py`, rodar `npm run app` em `web/` (e `npm ci` antes, numa cópia nova) e fazer o commit do `novo/` (`git add -A novo`, porque o arquivo antigo sai e entra um novo).
- **Data:** 13/10/2026

## Teste com Hypothesis passa mesmo com o código estragado (combinação rara)
- **Sintoma:** no teste de que o Streamlit e a API decidem igual (#182), estraguei o código de propósito (o Streamlit liberava plano vazio) e o teste com `@given(plano=..., chave=...)` continuou verde.
- **Causa:** o Hypothesis **sorteia** exemplos (100 por padrão). Só 4 das 184 combinações de plano × página mostravam o estrago (2 planos vazios × 2 páginas pagas); o sorteio não caiu em nenhuma.
- **Solução:** quando as combinações são poucas, **conferir todas** (`@pytest.mark.parametrize` ou um laço), sem sorteio; o Hypothesis fica para o que é grande de verdade (aqui, textos de plano quaisquer, cada um conferido em todas as páginas). E sempre fazer a conferência ao contrário: estragar o código e ver o teste falhar.
- **Data:** 14/10/2026

## `git status` mostra `web/conteudo/*.json` modificados, mas o `git diff` vem vazio
- **Sintoma:** depois de rodar a suíte ou o `exportar_conteudo`, todos os `web/conteudo/*.json` aparecem como `M`, e o `git diff` não mostra nada.
- **Causa:** alguns testes regravam o conteúdo (igual) e o `.gitattributes` (`web/** text=auto eol=lf`) faz o Git desconfiar da data do arquivo. O conteúdo é o mesmo: `git hash-object ARQUIVO` bate com `git rev-parse HEAD:ARQUIVO`.
- **Solução:** `git checkout -- web/conteudo` (ou só não adicionar esses arquivos; nunca `git add -A` sem olhar). Atrapalha o `git rebase`, que recusa "unstaged changes" até isso.
- **Data:** 14/10/2026

## `CHECK (... ficha IS NULL)` não barra a linha: `None` numa coluna JSON vira o texto `null`
- **Sintoma:** o teste que esperava `IntegrityError` ao gravar `ficha=None` num link do tipo "ficha" passou direto (`DID NOT RAISE`): o banco aceitou a linha.
- **Causa:** numa coluna `sa.JSON` (ou `JSONB`), o SQLAlchemy grava o `None` do Python como o **valor JSON** `null`, que para o banco não é `NULL`. A trava `ficha IS NOT NULL` vê um valor e deixa passar.
- **Solução:** para gravar o `NULL` do banco, usar `sa.null()` (ou simplesmente não mandar a coluna no `insert`). Outra opção é criar a coluna com `sa.JSON(none_as_null=True)`.
- **Data:** 13/10/2026

## `insert(...).values([lista])` falha com `CompileError ... explicitly rendered as a bound parameter`
- **Sintoma:** inserir várias linhas de uma vez quebrou com `INSERT value for column ... is explicitly rendered as a bound parameter`.
- **Causa:** as linhas da lista não tinham as mesmas chaves (uma tinha `relatorio_id`, as outras não). Num `insert` de várias linhas, todas precisam das mesmas colunas.
- **Solução:** pôr todas as colunas em todas as linhas (com `None` onde não há valor).
- **Data:** 13/10/2026

## PR empilhado em outro dá conflito em tudo depois do merge do primeiro com "squash"
- **Sintoma:** o PR 2 saiu do ramo do PR 1. Depois do merge do PR 1 na `main` (`gh pr merge --squash`), juntar a `main` no ramo do PR 2 deu conflito em todos os arquivos que os dois PRs mexiam (`rotas.py`, `esquemas.py`, o `openapi-v1.json`, o `novo/index.html`).
- **Causa:** o "squash" junta os commits do PR 1 num commit **novo**, com outro código (hash). O Git não sabe que é a mesma mudança que o ramo do PR 2 já tem, e vê as duas versões como edições diferentes das mesmas linhas.
- **Solução:** primeiro conferir que só o PR 1 mexeu nesses arquivos na `main` (`git log --oneline <commit do PR 1 no ramo>..origin/main -- ARQUIVO`) e que o conteúdo é igual (`git diff <commit do PR 1 no ramo> <commit do squash> -- ARQUIVOS` vazio). Aí a versão do ramo do PR 2 já contém o PR 1 inteiro: `git checkout --ours ARQUIVOS`, `git add`, regerar os arquivos gerados (`npm run app`, `python -m scripts.gerar_openapi`) e rodar os testes antes do commit do merge.
- **Data:** 14/10/2026

## `SyntaxError: (unicode error) 'unicodeescape' ... truncated \UXXXXXXXX escape`
- **Sintoma:** um script Python curto (para editar um arquivo de texto) parou antes de rodar, apontando para um texto com `C:\Users\tiago\...`.
- **Causa:** num texto Python comum, `\U` começa um código Unicode (`\U0001F600`); `\Users` não é um código válido. Caminhos do Windows dentro de aspas normais caem nisso (e também `\n`, `\t`).
- **Solução:** usar barras normais (`C:/Users/tiago/...`, o Python e o Windows aceitam), ou texto cru (`r"C:\Users\..."`), ou `pathlib.Path`.
- **Data:** 14/10/2026

## Teste de ordem "mais novo primeiro" falha às vezes no Windows (passa sozinho)
- **Sintoma:** `test_lista_vem_da_mais_nova_para_a_mais_antiga` (Diário de Teses) falhou uma vez na suíte inteira com a máquina carregada e passava sozinho.
- **Causa:** no Python 3.12 do Windows, `datetime.now()` usa `GetSystemTimeAsFileTime`, que anda de 15,6 em 15,6 ms (`time.get_clock_info("time").resolution`). Duas teses gravadas em seguida saíam com a mesma hora; a consulta desempata pelo `id`, que é um `uuid4` aleatório, então a ordem virava cara ou coroa (com o relógio parado, 10 de 20 rodadas falharam). Em produção (PostgreSQL no Linux, microssegundos) o empate não acontece.
- **Solução:** teste de ordem não depende do relógio: fixe as horas (aqui com `sa.update(...).values(criada_em=...)`; em `compartilhamentos` a função já recebe `agora=`). Para conferir que um teste aguenta o empate, rode-o com o `datetime` do módulo trocado por um relógio parado (`monkeypatch.setattr(modulo, "datetime", RelogioParado)`).
- **Data:** 14/10/2026

## Teste do React que passa sozinho e falha de vez em quando: duas fontes para o mesmo estado
- **Sintoma:** `meus_dados.test.tsx > revogar manda o id do link e atualiza a lista` falhava 1 vez em cada ~12 rodadas e estourou o tempo no CI da `main` (o deploy automático não implantou: "testes do GitHub falharam").
- **Causa:** a tela guardava a lista em `useState(inicial)` **e** tinha `useEffect(() => setDados(inicial), [inicial])`. Quando a resposta do revogar chegava antes de o efeito rodar, o efeito vinha depois e punha a lista velha de volta (com o botão "Revogar"). Contar os pedidos no teste mostrou que a lista foi pedida uma vez só: não era um segundo pedido.
- **Solução:** uma fonte só. O estado começa com a resposta da API e só muda pelo revogar; nada de efeito copiando a prop para o estado. Para conferir, repetir o teste em laço (`for i in $(seq 1 20); do npx vitest run ARQUIVO; done`) e ver quantas vezes falha.
- **Data:** 14/10/2026

## Teste que conta pedidos e erra por um: contou antes do primeiro pedido sair
- **Sintoma:** `planos.test.tsx > a volta do pagamento avisa e deixa atualizar o plano` falhava às vezes com "esperava antes + 1".
- **Causa:** o aviso da volta do pagamento aparece na hora, antes de o primeiro pedido do plano sair. O teste guardava "quantos pedidos já houve" logo depois do aviso; às vezes o primeiro pedido ainda não tinha saído e entrava na conta depois.
- **Solução:** esperar a tela carregar (`findByRole("region", { name: "Seu plano" })`) antes de contar.
- **Data:** 14/10/2026

## PR sem nenhum check no GitHub ("no checks reported")
- **Sintoma:** depois de um push, o PR ficou sem CI nenhum.
- **Causa:** o PR estava em conflito com a `main` (`mergeable: CONFLICTING`). O CI de PR roda sobre a junção do ramo com a `main`; com conflito, essa junção não existe e o GitHub não roda nada.
- **Solução:** juntar a `main` no ramo, resolver e mandar de novo. Conferir com `gh pr view N --json mergeable,mergeStateStatus`.
- **Data:** 14/10/2026

## Conflito só em `novo/` (o app em React gerado) ao juntar a `main`
- **Sintoma:** `CONFLICT (rename/rename): novo/assets/index-XXXX.js ...`, conflito em `novo/index.html` e `novo/sw.js`.
- **Causa:** o `novo/` é gerado pelo `npm run app` e o nome dos arquivos muda a cada build; os dois lados geraram arquivos diferentes.
- **Solução:** não resolver à mão. Confirmar que **não** há conflito fora do `novo/`, apagar os `novo/assets/*` em conflito, ficar com o `index.html`/`sw.js` de qualquer lado e **regerar** (`cd web && npm run app`), depois `git add -A novo`. O CI confere que o `novo/` está em dia.
- **Data:** 14/10/2026

## Lista de sugestões da busca por baixo do "Experimente" (site, página inicial)
- **Sintoma:** ao digitar um ativo na busca da página inicial, a lista de sugestões aparecia atrás dos exemplos ("Experimente:"), da linha decorativa do herói e da fita de ativos, e o fim dela era cortado. O `z-index: 4` da lista não resolvia.
- **Causa:** contextos de empilhamento criados sem querer. (1) `animation-fill-mode: both` na animação de chegada (`tl-chegar`) deixa o `transform` final aplicado para sempre, e todo elemento com `transform` vira um contexto de empilhamento com `z-index: auto`: o `z-index` da lista passa a valer só dentro do pai dela, que perde para os irmãos que vêm depois no HTML. (2) O `movimento.js` põe `translate` na coluna de texto (paralaxe): mesmo efeito. (3) `overflow: hidden` no topo da página cortava o que descia dele. (4) A fita de ativos é `position: relative` e vem depois do herói: pinta por cima de tudo o que o herói deixa vazar.
- **Solução:** `backwards` em vez de `both` nas animações de chegada (o estado final é o natural, então nada muda na tela); `z-index` explícito em quem precisa ficar por cima (`.busca`, `.heroi-texto`, `.topo-da-pagina`); as camadas de fundo que precisam de corte numa caixa própria (`.v2-camadas`, com `overflow: hidden`) em vez de cortar o topo inteiro. Para achar o culpado: no console, `getComputedStyle(el).transform`, `translate`, `filter`, `backdropFilter`, `opacity` e `isolation` de cada ancestral, e `document.elementsFromPoint(x, y)` para ver quem está por cima.
- **Data:** 14/10/2026 (PR #244)

## `StreamlitValueAssignmentNotAllowedError` ao clicar na Carteira da B3
- **Sintoma:** na página Carteira da B3, o primeiro clique depois de abrir a página (ligar um exemplo, por exemplo) mostrava `st.session_state['carteira_b3_arquivo'] is read-only and cannot be assigned through session state`.
- **Causa:** o `manter_estado` do `app.py` reatribui, a cada execução, toda chave com um dos prefixos que sobrevivem à troca de página (`carteira_`, `backtest_`...), para o Streamlit não esquecer os campos. As chaves dos campos de arquivo também começavam com `carteira_`, e o Streamlit proíbe escrever no valor de um `st.file_uploader`. Na primeira execução o campo aparece (com valor `None`); na seguinte, o `manter_estado` escreve `None` nele e o campo quebra. Os testes não pegavam porque ligavam o exemplo **antes** de abrir a página, então o campo de arquivo nunca chegava a aparecer.
- **Solução:** a chave de todo campo de arquivo começa com `arquivo_` (fora dos prefixos do `manter_estado`), como o `arquivo_b3` já fazia. Teste de regressão: abrir a página, **depois** ligar o exemplo e rodar de novo (`test_ligar_um_exemplo_depois_de_abrir_a_pagina_nao_quebra`). Achado conferindo a tela no navegador.
- **Data:** 14/10/2026 (PR #260)

## Acento "errado" ao olhar um CSV do Banco Central no terminal (parecia latin-1)
- **Sintoma:** ao abrir o `scrdata_AAAAMM.csv` do SCR.data, "Médio" e "salários mínimos" saíam com acento quebrado, e a primeira coluna vinha como `﻿data_base`; parecia que o arquivo era latin-1.
- **Causa:** o arquivo é UTF-8 com BOM; quem quebrava o acento era a saída do terminal do Windows (cp1252), não a leitura.
- **Solução:** ler com `encoding="utf-8-sig"` (tira a BOM) e conferir rodando o Python com `python -X utf8`. Teste com acento de verdade (`tests/test_base_bcb.py`).
- **Data:** 14/10/2026 (PR #226)

## SSH pelo nome do Tailscale: "Host key verification failed"
- **Sintoma:** fora da rede de casa, `ssh granserver@servidor.<tailnet>.ts.net` recusava com "Host key verification failed", apesar de ser o mesmo servidor.
- **Causa:** o `known_hosts` guarda a chave pelo IP da rede de casa (`192.168.15.5`); o nome do Tailscale é outro nome para o mesmo servidor e não está lá.
- **Solução:** `ssh -o HostKeyAlias=192.168.15.5 granserver@servidor.<tailnet>.ts.net` (confere a mesma chave, sem aceitar uma nova às cegas).
- **Data:** 14/10/2026

## Sessão SSH presa ao disparar uma carga longa com `setsid ... &`
- **Sintoma:** o comando que disparava a carga no servidor de casa não voltava; a sessão SSH só terminou pelo limite de tempo.
- **Causa:** não confirmada: a saída já estava redirecionada (`> ~/logs/x.log 2>&1 < /dev/null`) dentro do `setsid`; a suspeita é o `docker run -i` ou o `sleep 60; tail` na mesma chamada.
- **Solução:** disparar numa chamada e conferir o log numa chamada separada. Mesmo com a sessão presa, a carga segue viva (o `setsid` a solta da sessão): conferir com `pgrep -af <script>` e o log.

## Arquivista mensal falha no CNPJ com `RemoteDisconnected`, cada vez num arquivo diferente
- **Sintoma:** `FALHAS: rfb-cnpj (1 arquivos; ...)` com `('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`; em 14/10/2026 foram `Empresas4`, `Estabelecimentos0` e `Socios0` de manhã e `Qualificacoes` à noite. Baixado na mão com `curl`, o mesmo arquivo vinha inteiro.
- **Causa:** o servidor da Receita fecha a conexão antes de responder de vez em quando. O `requests` tenta **zero** vezes de novo por padrão, e a única nova tentativa do arquivista era a da fonte inteira, 5 minutos depois. Com 37 arquivos no mês, quase sempre algum caía.
- **Solução:** `HTTPAdapter(max_retries=Retry(...))` na sessão do `scripts/arquivar_fontes.py` (#257): repete o pedido na hora, até 3 vezes (0, 4 e 8 s), só quando a conexão cai ou não abre; resposta de erro (404, 500) não é repetida. O teste usa um servidor HTTP local que fecha a conexão sem responder. Lição: falha que muda de arquivo a cada rodada é da rede ou do servidor, não do arquivo; repetir a tarefa inteira à mão só esconde.
- **Data:** 14/10/2026

## CI vermelho: "novo/ está velho" depois de mexer só no site
- **Sintoma:** no PR #254 (ferramentas v2), o job `web (React)` falhou com `novo/ está velho: rode 'npm run app' em web/ e faça o commit`, mesmo o PR sendo das ferramentas do site.
- **Causa:** o app em React (`novo/`) usa o mesmo CSS (`web/src/estilo*.ts`) e alguns módulos comuns (a escala dos gráficos saiu de `web/src/app/graficos/` para `web/src/graficos/`). Mudou o CSS ou um módulo que o app importa, o build do app muda também. Rodei só o `npm run site`.
- **Solução:** mexeu em `web/`, rode os dois: `npm run site` **e** `npm run app`, e faça o commit de `site/` e `novo/` juntos. O mesmo PR também caiu no `ruff format` (linhas longas num teste): rodar `ruff format` nos arquivos Python mudados antes do push.
- **Data:** 14/10/2026 (PR #254)

## O CI do PR não roda depois de um push novo
- **Sintoma:** o push chega ao GitHub (o PR mostra o commit novo), mas nenhum "Testes e ruff" começa; `gh pr view --json mergeable` diz `UNKNOWN`.
- **Causa:** a `main` andou e mexeu no mesmo arquivo (aqui, `tests/test_base_dicionario.py`): com conflito, o GitHub **não dispara** o evento `pull_request`.
- **Solução:** `git merge-tree --write-tree --name-only HEAD origin/main` mostra o conflito sem mexer em nada; juntar a `main` no ramo (`git merge origin/main`), resolver, rodar os testes do arquivo e subir. O CI volta a rodar.
- **Data:** 14/10/2026

## Uma tabela da base aparecia em dobro depois da primeira carga mensal
- **Sintoma:** a ligação dos bancos de 2026-06 tinha cada instituição duas vezes (11.730 linhas em vez de 5.865).
- **Causa:** a montagem lia `glob("[0-9]*.parquet")`, e o padrão também pega as versões guardadas (`202506.v1.parquet`). As versões tinham nascido falsas: o BC devolve o cadastro com outros bytes e o mesmo conteúdo, e a regra de versões olhava só o SHA-256 do arquivo de origem.
- **Solução:** ler só o arquivo cujo nome é a data (`re.fullmatch(r"\d{6}", arquivo.stem)`), e criar versão só quando o **conteúdo** muda (`sha256_da_tabela`), não quando os bytes do original mudam (#266). Toda leitura de uma pasta com versões precisa filtrar o nome.
- **Data:** 14/10/2026

## Fechamento da B3 errado nas barras: correção da B3 vira o "último negócio" do dia
- **Sintoma:** em 25/09/2026 o fechamento do PETR4 nas barras saía 48,07, e o boletim oficial dizia 47,99. Volume e número de negócios batiam.
- **Causa:** o arquivo de negócios da B3 traz correções no meio do dia: às 17h06 a B3 cancelou o negócio 346910 (2.700.000 ações, das 16h08) e lançou o 346911 (270.000) **com a hora da correção**. Ordenando pela hora, o substituto ficava depois do leilão de fechamento. Os identificadores andam de 10 em 10 por instrumento; final diferente de 0 é negócio inserido depois (correção ou registro tardio).
- **Solução:** o negócio inserido herda o instante do negócio de dezena logo antes dele (`base/intradiario_b3.py`, `PASSO_DO_IDENTIFICADOR`), com teste dos dois casos reais (25/09 e 18/09). Lição: num arquivo de bolsa, conferir a ordem pelo identificador, não só pela hora.
- **Data:** 14/10/2026

## Volume da B3 "a mais" que o COTAHIST nas sextas, com o arquivo certo
- **Sintoma:** nas sextas de vencimento de opções, ~11% das ações tinham alguns negócios a mais no arquivo do que no COTAHIST do dia, com preços 100% iguais.
- **Causa:** o COTAHIST do dia deixa de fora registros tardios (lançados às 19h); o boletim PR (BVBG.086) os inclui e bate com o arquivo (PETR4 em 18/09: 31.339 negócios no arquivo e no PR, 31.321 no COTAHIST).
- **Solução:** conferir contra o PR; usar o COTAHIST só para saber se houve pregão, quem é do à vista e o que falta no PR. Lição: antes de culpar o dado, conferir com uma segunda fonte oficial.
- **Data:** 14/10/2026

## Carga da IEX falha num feriado dos EUA com `404 Not Found`
- **Sintoma:** a carga dos 12 meses parou em `2026-09-07: FALHOU ... 404 Client Error: Not Found for url: .../hist?date=20260907` e a marca virou `.falha`.
- **Causa:** o coletor pedia todos os dias de segunda a sexta e contava que, num feriado, a IEX respondesse uma lista vazia. Ela responde **404**. 07/09/2026 foi Labor Day.
- **Solução:** pedir só os pregões da NYSE (`src/calendario_nyse.py`: feriados pelas regras da bolsa e os fechamentos extras numa lista). Um 404 num dia de pregão continua sendo falha, para o alarme mostrar um fechamento que o calendário ainda não conhece (#264).
- **Data:** 14/10/2026

## GDELT responde `429 Too Many Requests` mesmo esperando entre os pedidos
- **Sintoma:** a coleta do GDELT falhava todo dia com 429, até no primeiro pedido depois de 20 horas parada, mesmo com 6 s entre os pedidos (o GDELT pede 5 s).
- **Causa:** em outubro/2026 o GDELT deixava passar só **um pedido a cada 10 a 20 minutos**, de casa e também do VPS (não era bloqueio só do endereço de casa). Pedindo um dia por vez, a carga desde 2017 levaria meses.
- **Solução:** pedir 30 dias de uma vez (com mais de 3 dias o GDELT responde um ponto por dia, com os mesmos números), pausa de 60 s, esperas de 2 a 15 min no 429 e no máximo 4 horas por rodada (#264, #276). Para medir sem gastar a cota: um pedido só, com `curl -w "%{http_code}"`.
- **Data:** 15/10/2026

## Dia do GDELT guardado "pela metade"
- **Sintoma:** 02/01/2017 aparecia na base com 5 notícias; os dias vizinhos tinham ~600.
- **Causa:** o pedido de um dia (`startdatetime=20170101000000&enddatetime=20170102000000`) devolve também o ponto da meia-noite do dia seguinte. Esse quarto de hora virava uma linha do dia 2, e a rodada seguinte começava no dia 3.
- **Solução:** guardar só os dias do período pedido (`dia < fim`) e, quando há dias novos, pedir de novo o último dia guardado (#276).
- **Data:** 15/10/2026

## Programa `ots` (OpenTimestamps) quebra no Windows com `TypeError: argument of type 'NoneType' is not iterable`
- **Sintoma:** depois de `pip install opentimestamps-client`, qualquer comando `ots` parava em `bitcoin/core/key.py`, dentro de `ctypes.cdll.LoadLibrary`.
- **Causa:** a `python-bitcoinlib` procura a biblioteca do OpenSSL (`libeay32`/`libssl`) por `ctypes` ao importar `bitcoin.rpc`; no Windows ela não acha e passa `None` como nome do arquivo. A biblioteca `opentimestamps` (o núcleo) não importa essa parte e funciona.
- **Solução:** usar a biblioteca `opentimestamps` direto em `scripts/ancorar_base.py` (o recibo `.ots` é o mesmo formato); o programa `ots` fica para quem confere com Linux e um nó do Bitcoin (#287).
- **Data:** 15/10/2026

## Valor que chega dos dados do dia apaga o número que veio de um link
- **Sintoma:** o link "continue a conta" do "quanto daria" abria a correção pela inflação com outra data de início; a inflação que a pessoa digitava no juro real antes de os dados do BC chegarem voltava para o IPCA.
- **Causa:** o `sugerir` do `useCamposNoEndereco` (usado para pôr o IPCA ou o último mês quando os dados chegam) trocava os campos sem saber quais tinham vindo do endereço ou sido mudados pela pessoa; cada tela remendava isso checando uma chave fixa do endereço (`anoFinal`), e a chave que o link trazia era outra.
- **Solução:** o gancho guarda o conjunto de campos "fixados" (lidos do endereço ao ligar ou mudados pela pessoa) e o `sugerir` nunca passa por cima deles. Regra: valor sugerido por dado externo nunca vence o que a pessoa ou o link escolheu.
- **Data:** 15/10/2026

## Financiamento pela Price não zera o saldo com taxa alta
- **Sintoma:** com 10% ao mês em 600 meses, a tabela terminava com o saldo inteiro (R$ 300 mil) e amortização zero em todos os meses; o Hypothesis achou resíduo também em casos menores.
- **Causa:** `(1 + taxa)^−meses` some na precisão do float, então a parcela calculada fica igual ao juro do mês e o resíduo de arredondamento se acumula.
- **Solução:** no último mês do prazo, a amortização é o saldo que sobrou (`amortizacao = saldo`), em Python e no TypeScript; o teste de propriedade "as amortizações somam o valor financiado" pega a volta do erro.
- **Data:** 15/10/2026

## Manifesto que não confere com o próprio Parquet (`1.0` na memória, `1` no arquivo)
- **Sintoma:** ao remontar `eventos_de_capital` com manifesto, cada ano virou versão `.v1` sem o dado ter mudado, e `conferir_tabela` dava `False` logo depois de gravar.
- **Causa:** o leitor deixa colunas `object` com float do Python. O `to_csv(float_format=...)` do hash não formata coluna `object` (`1.0`), mas o Parquet devolve `float64`, que sai `1`. O hash feito na memória era de um texto diferente do arquivo gravado.
- **Solução:** o hash do manifesto é sempre da tabela como volta do disco (`base/parquet.py::como_no_disco`), e a comparação "o dado mudou?" também; manifesto que não confere é refeito sem versão (#299). Regra: hash de conferência se calcula sobre o que foi gravado, nunca sobre o objeto em memória.
- **Data:** 15/10/2026

## Script do servidor esperou 2 h por um merge que já tinha acontecido
- **Sintoma:** o `ma-coletor-no-servidor.sh` (#313) ficou no laço "esperando o merge" e saiu com "não entrou na main em 2 h", embora `git log origin/main --oneline | grep '(#313)'` achasse o commit quando rodado à mão.
- **Causa:** o script tem `set -euo pipefail`. No laço `until git log ... | grep -q '(#313)'`, o `grep -q` termina assim que acha a linha; o `git log` ainda está escrevendo, leva SIGPIPE e sai com 141. Com `pipefail`, o pipeline inteiro conta como falha, então o `until` nunca via o merge.
- **Solução:** perguntar direto ao Git, sem pipeline: `git merge-base --is-ancestor <commit> origin/main` (sai 0 se o commit já está na `main`). Regra geral: com `pipefail`, não pôr `grep -q` (ou `head`) depois de um comando que escreve muito.
- **Data:** 16/10/2026
## Carga da IEX para no meio com `ProtocolError: Connection broken: IncompleteRead(...)`
- **Sintoma:** a tarefa `iex-carga` do VPS termina com saída 1 e um traceback da `urllib3` no log; o Kuma ("Tarefas do VPS") fica vermelho e o selo da rodada não roda.
- **Causa:** a conexão com a IEX caiu no meio do arquivo do dia (~17 GB). O coletor lê o `resposta.raw` direto, então o erro vem da `urllib3`, que não é `requests.RequestException` nem `OSError` e escapava do `except`.
- **Solução:** `scripts/coletar_iex_do_dia.py` baixa o dia de novo uma vez; se cair de novo, o dia falha sozinho ("FALHOU, nada gravado") e a rodada segue (PR #322). Lição: quem lê `.raw` de uma resposta do `requests` precisa tratar os erros da `urllib3` também.
- **Data:** 16/10/2026

## Carga da PGFN passa de 2,7 GB no servidor de casa (milhões de linhas em texto)
- **Sintoma:** a 1ª montagem da `pgfn_divida` (#339) chegou a 2,7 GB no contêiner; o vigia de memória pôs o Kuma de casa em "down" (728 MB livres) e a carga foi parada à mão.
- **Causa:** três coisas, medidas por fases com os dados reais: (1) 6,8 milhões de raízes de CNPJ num `set` de textos do Python (~60 bytes cada, mais o conjunto) e o `isin(set)` refeito a cada pedaço da Receita; (2) a conversão das raízes para número feita no lote inteiro de uma vez (cópias de 64 bits de tudo: 2,3 GB); (3) o maior CSV (2,28 milhões de linhas) gravado de uma vez, com a linhagem (SHA-256, datas, commit) repetida como texto em cada linha, e o hash do manifesto relendo e ordenando a tabela inteira (2,4 GB).
- **Solução (#342):** raiz como número de 8 bytes (`base/cnpj.py::raizes_em_numeros`, base 36, aceita o CNPJ com letras) e busca por ordenação (`contem`), em pedaços de 1 milhão; cada CSV gravado em 11 Parquets pelo 1º caractere do CNPJ, com a linhagem só no pedaço que está sendo gravado. Pico de 1,96 GB. **Lição:** antes de rodar uma carga nova no servidor de casa, um ensaio só de leitura com `ru_maxrss` por fase; pandas 3 guarda texto em Arrow, mas texto repetido em milhões de linhas ainda pesa.
- **Data:** 16/10/2026

## Script do servidor some sem mensagem depois de `cmd | grep -q`
- **Sintoma:** um script com `set -euo pipefail` para no meio sem escrever nada no log; o passo seguinte nunca roda (17/10/2026, `~/bin/ma-religar-356.sh`: fez o `git pull` e parou antes do `docker tag`).
- **Causa:** `git log --oneline -15 | grep -q "(#356)"`: o `grep -q` sai assim que acha, o `git log` ainda escrevendo leva SIGPIPE e sai com 141; com `pipefail` o pipe inteiro vale 141 e o `set -e` encerra o script, sem mensagem.
- **Solução:** não pôr `grep -q` (nem `head`) no fim de um pipe com `pipefail`. Guardar a saída numa variável e testar: `ultimos=$(git log --oneline -15)` e `[[ "$ultimos" == *"(#356)"* ]]`.
- **Data:** 17/10/2026

## A mesma base dá fichas diferentes na 15ª casa decimal (soma em DOUBLE no DuckDB)
- **Sintoma:** no ensaio do dossiê pela porta (#381), duas rodadas seguidas sobre a mesma base deram 4 fichas diferentes, só na 15ª casa decimal de somas (ex.: acessos da Anatel).
- **Causa:** o DuckDB soma em paralelo. Em ponto flutuante (DOUBLE), a ordem da soma muda o arredondamento (0,1 + 0,2 dá 0,30000000000000004), e a ordem muda de uma rodada para outra.
- **Solução:** a `Porta.somar` soma em `DECIMAL(38, 10)`, que é exato, e só no fim volta para DOUBLE (`test_somar_e_exato`). Regra: em resultado que precisa se reproduzir (ADR 0078), somar em decimal.
- **Data:** 17/10/2026

## Arquivo esparso passa pelo limite de tamanho do tar
- **Sintoma:** numa revisão de segurança de um recebedor de arquivos por tar, um tar de 10 KB passava no limite de tamanho e abria um arquivo de 3 GB.
- **Causa:** um arquivo esparso (com "buracos") ocupa quase nada no tar, mas o tamanho aparente dele, que é o que o app leria, é enorme. O limite só olhava o tar.
- **Solução:** depois de extrair, conferir também `du -s --apparent-size --block-size=1` da pasta contra o limite. Regra: limite de tamanho vale para o que entra e para o que sai aberto.
- **Data:** 17/10/2026

## `cat > arquivo` antes de um heredoc engole o texto
- **Sintoma:** o teste novo não apareceu em `tests/test_porta.py`, embora o comando tivesse "rodado".
- **Causa:** no comando `cat > x.py; python - <<'EOF' ...`, o `cat` sem entrada própria leu o heredoc que era do Python e o gravou no arquivo; o Python não recebeu nada.
- **Solução:** editar arquivo com a ferramenta de edição (ou um único `python - <<'EOF'` sem nada antes). Regra: um heredoc por comando, e só no comando que deve lê-lo.
- **Data:** 17/10/2026

## Variável local com o nome de um módulo importado (`'list' object has no attribute ...`)
- **Sintoma:** a 1ª montagem das colunas do modelo 8 no servidor (17/10, depois do #384) caiu com `AttributeError: 'list' object has no attribute 'contas_do_balanco'`, embora todos os testes passassem.
- **Causa:** o montador faz `from base.modelos.atraso import colunas` (o módulo). Dentro de `_demonstracoes`, uma lista de campos também se chamava `colunas`, e dentro da função esse nome passou a ser a lista; `colunas.contas_do_balanco(...)` procurou a função na lista. A troca automática de nomes (`contas_do_balanco` → `colunas.contas_do_balanco`) ao mover o código criou o choque. Os testes não pegaram porque nenhum gravava demonstrações na pasta, então o laço nunca rodava.
- **Solução:** a lista virou `campos`, e o teste da montagem passou a gravar demonstrações (com o código velho, ele falha com o mesmo erro). Regras: não dar a uma variável o nome de um módulo importado; o teste de montagem precisa ter pelo menos uma linha de cada fonte; e, depois de mover código com troca automática de nomes, ensaiar contra a base real antes do merge.
- **Data:** 17/10/2026
