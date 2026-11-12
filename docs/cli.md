# A CLI `tickerlab`: a API externa no terminal e no agente de IA

A CLI `tickerlab` (linha 772 da fila, ADR 0127) é um cliente fino da API externa de dados (`/data/v1`). Ela pega a
resposta da API e a mostra numa tabela, para a pessoa, ou no envelope JSON inteiro, para o agente de IA de quem
analisa empresas (Claude Code, Codex e outros). Ela não tem regra própria: a chave, a quota, o contrato, o portão de
licença e o "como era" são todos da API, e a CLI só repassa o que a API serviu.

O código fica em `cli/`. É um pacote à parte, que depende só de `click` e `httpx` e não importa nada de `src/` nem de
`base/` (há teste que cobra), para não levar o resto do repositório ao PC de quem o instala.

## Instalar

Num PC de fora (Windows, sem o repositório e **sem o Git**), com o Python 3.11 ou mais novo instalado do python.org
(marcando "Add python.exe to PATH"):

```powershell
py -m pip install --user pipx
py -m pipx ensurepath          # feche e abra o terminal depois deste
pipx install "https://github.com/tbc174/tickerlab/archive/refs/heads/main.zip#subdirectory=cli"
tickerlab --help
```

O `pipx` põe a CLI num ambiente só dela, sem misturar com outros pacotes do Python da pessoa. Para atualizar, o
mesmo `pipx install ... --force`. O endereço é o zip da `main` no GitHub (o repositório é público): o `pip` baixa,
entra em `cli/` e instala, sem precisar do Git (conferido num ambiente limpo em 10/11/2026).

Para quem tem o Git ou mexe no código:

```powershell
pip install "git+https://github.com/tbc174/tickerlab#subdirectory=cli"   # de um ramo ou da main
pip install -e cli                                                        # no repositório, para mexer
```

Publicar o pacote (PyPI, Homebrew) e escolher o nome público dele são decisões do Tiago (nível 1). Até lá, a
instalação é pelo zip ou pelo Git.

## Chave e endereço

A chave da organização (`tld_...`) **nunca** entra como argumento, porque ficaria no histórico do terminal. Ela pode
vir de dois lugares:

1. **`TICKERLAB_API_KEY`**, a variável de ambiente, que vale mais que o arquivo. É o caminho para um agente ou um
   servidor.
2. **`tickerlab login`**, que pergunta a chave sem mostrá-la e confere com a API se ela vale (com `--sem-conferir`,
   não confere). Depois grava a chave num arquivo que só o usuário lê: `%APPDATA%\tickerlab\credenciais.json` no
   Windows, `~/.config/tickerlab/credenciais.json` no Linux e no macOS (permissão `600`, pasta `700`), ou na pasta
   de `TICKERLAB_CONFIG_DIR`. `tickerlab logout` apaga o arquivo.

`TICKERLAB_API_URL` troca o endereço; o padrão é a produção, `https://api.tickerlab.com.br`. A CLI recusa um
endereço sem HTTPS, a não ser que ele aponte para a própria máquina (`localhost`, `127.0.0.1`, `*.localhost`).
Assim, a chave não vai em texto aberto pela rede.

## Os comandos

| Comando | Rota | Gasta a quota |
|---|---|---|
| `tickerlab empresa <cnpj> [--como-era AAAA-MM-DD]` | `GET /data/v1/companies/{cnpj}/profile` | sim |
| `tickerlab empresa <cnpj> --so-cadastro` | `GET /data/v1/companies/{cnpj}` | sim |
| `tickerlab comparaveis <cnpj> [--como-era ...]` | `GET /data/v1/companies/{cnpj}/comparables` (rota da linha 736) | sim |
| `tickerlab compradores --cnae <5 ou 7 dígitos> [--uf SP] [--anos 3] [--limite 20]` | `GET /data/v1/buyers` (rota da linha 810) | sim, um pedido |
| `tickerlab vinculos <cnpj> [--profundidade 1-3] [--tipo ...]` | `GET /data/v1/companies/{cnpj}/links` (rota da linha 736) | sim |
| `tickerlab dossie <cnpj> [--como-era ...]` | `profile`, `events`, `links` e `comparables` da empresa | sim, 4 pedidos |
| `tickerlab eventos <cnpj> [--tipo ...] [--todas]` | `GET /data/v1/companies/{cnpj}/events` (rota da linha 736) | sim, um pedido por página |
| `tickerlab demonstracoes <cnpj> [--como-era ...] [--periodo AAAA-MM-DD]` | `GET /data/v1/companies/{cnpj}/financials` (sem dado: "faturamento de empresa fechada a base não tem", mesma frase do conector) | sim |
| `tickerlab fundo <cnpj> [--como-era ...] [--retorno-suposto 0.12]` | `GET /data/v1/funds/{cnpj}` | sim |
| `tickerlab prospectar --cnae ... [--uf ..] [--todas] ...` | `GET /data/v1/companies` (busca, rota da linha 794) | sim, um pedido por página |
| `tickerlab setor` | `GET /data/v1/sectors` | não |
| `tickerlab setor <chave> [--como-era ...]` | `GET /data/v1/sectors/{key}` | sim |
| `tickerlab deck <cnpj>` ou `tickerlab deck --setor <chave>` `[--como-era ...] [--saida arq.pptx] [--substituir]` | `GET /data/v1/companies/{cnpj}/deck` ou `GET /data/v1/sectors/{key}/deck` (linha 782) | sim, um pedido |
| `tickerlab catalogo` | `GET /data/v1/catalog` | não |
| `tickerlab consumo` | `GET /data/v1/usage` | não |

- `tickerlab empresa` pede o perfil (linha 736): o cadastro na Receita e, da companhia aberta, cada DFP e ITR
  devida até o dia, com o prazo da CVM, a primeira entrega, os dias úteis de atraso e a situação (`on_time`,
  `gray_zone`, `late`, `severely_late`, `not_filed`), mais os limites da leitura (`limits`). O perfil pede o
  conjunto `profiles` no contrato; a chave que tem só `companies` usa `--so-cadastro`.
- `tickerlab comparaveis` traz as companhias abertas do mesmo grupo de setores (pelo setor do FCA entregue até o
  dia), cada uma com os números do último DFP (`revenue`, `ebitda`, `net_income`, `net_assets`, `net_debt` e as
  razões), a mediana de cada razão entre os pares (`peer_medians`) e os `limits`. Com `--como-era`, os pares de
  então: a empresa que mudou de setor no FCA muda de pares. Pede o conjunto `comparables` no contrato.
- `tickerlab compradores` lista candidatos a comprador do setor: quem entrou como sócio, fundo sócio ou controla
  empresa do setor nos últimos `--anos` (1 a 10), só pessoa jurídica, com os sinais e as evidências (empresa do
  setor, UF e data). Movimento passado não é intenção de compra: leia os `limits`.
- `tickerlab vinculos` traz os vínculos da empresa como eram no dia, de 1 a 3 saltos (`--profundidade`): de quem ela
  era controlada, coligada ou participada e quem ela controlava (pelo FRE, com a participação no capital) e a firma
  que a auditava (pelo FCA). `--tipo controlada|coligada|participada|auditor` (repete) filtra. Cada ponta sai com o
  id da rede, a raiz do CNPJ e a razão social do retrato mensal da Receita mais novo já público no dia, com o mês
  dele; pessoa física não sai. A tabela mostra `de` e `para`
  em uma célula cada; o `--json` traz as pontas inteiras. Pede o conjunto `links` no contrato.
- **Parte não disponível para a organização:** quando a API diz que um tipo (hoje `unavailable_event_types`, nos eventos) não foi consultado, a primeira linha da tela diz qual, o `dossie` o põe em `gaps` e a planilha o leva nas fontes; "nenhum evento" só vale para o que foi consultado. A leitura está num lugar só (`formato.CAMPOS_NAO_DISPONIVEIS`): rota nova com campo do mesmo tipo entra ali.
- `tickerlab dossie` junta o perfil, os eventos, os vínculos e os comparáveis de um CNPJ numa saída só, com fonte e
  data; o perfil é obrigatório e uma seção que a chave não cobre ou sem dado aparece em `gaps` com o motivo. Gasta
  4 pedidos da quota. Com `--planilha`, vai para o Excel (linha 831).
- `tickerlab eventos` traz os eventos da empresa, do mais novo ao mais velho: cada documento entregue à CVM pelo
  IPE (`ipe_filing`: protocolo, categoria, tipo, data de referência e endereço; o assunto escrito pela companhia
  não sai) e cada troca de auditor pelo FCA (`auditor_change`: o dia, o anterior, o novo e os anos com o
  anterior). `--tipo documento` ou `--tipo auditor` (repete) filtra; a página vai até o limite do plano e
  `--todas` segue o `next_cursor` (um pedido por página). Com `--como-era`, só o que já era público no dia. Pede o
  conjunto `events` no contrato.
- `tickerlab prospectar` busca empresas no cadastro da Receita (só empresa: sem sócio, contato nem endereço) pelos
  filtros `--cnae` (2 a 7 dígitos), `--uf`, `--municipio` (o nome, ou o código **da Receita**, de até 4 dígitos;
  o do IBGE não vale), `--porte` (`micro`, `pequena`, `demais`, `nao_informado`, que a API recebe como
  `micro|small|other|not_informed`), `--natureza` (até 4 dígitos, ou o começo), `--situacao` (`ativa`, `baixada`,
  `inapta`, `suspensa`, `nula`; sem ela, as ativas), `--aberta-depois`, `--aberta-antes` (a idade da empresa vira
  data de abertura) e `--so-matriz`. Os filtros de lista podem repetir, até 50 valores cada. Pelo menos um filtro
  além da situação e da data: sem ele, o comando para no código 2 sem chegar à API, porque a busca devolveria a
  base inteira. A rota pede o conjunto `prospecting` no contrato da organização; sem ele, o código 5. A resposta vem em páginas por ordem de CNPJ
  (`--por-pagina` até 100; o padrão da API é 50) com um `next_cursor` opaco. Sem `--todas`, sai a primeira página e
  o aviso de que há mais; com `--todas`, a CLI segue o cursor (até 100 páginas por vez, avisando no stderr) e junta
  as páginas numa resposta só, com as fontes sem repetir. A rota é da linha 584 (PR #973), combinada em 10/11/2026.
- O CNPJ entra com ou sem pontuação. A chave do setor (`eletricas`, `bancos`...) só aceita minúsculas, números e
  `_`; outra coisa para no código 2, sem chegar à API.
- O setor (molde D, linha 773; rota da linha 781) sai como a ficha da última noite o deixou. Na tabela, cada série
  da agência vira um bloco com a concentração e a fatia de cada companhia, e as notas de método (`notes`) saem como
  itens. O ano sai sem separador de milhar.
- Com `--json`, o comando imprime a resposta da API como ela veio, com `value`, `source`, `published_at` e
  `observed_at` em cada campo e `sources` no fim.
- Sem `--json`, imprime uma tabela por bloco, com a fonte e a data de publicação de cada campo ou linha. A tabela
  termina com as fontes (licença e frase de atribuição) e com o aviso de que nada é recomendação de investimento.
  Os nomes dos campos saem como a API os dá, para a pessoa e o agente falarem dos mesmos nomes.
- Dado de piloto (`pilot: true` no campo e `pilot_notice` na resposta, ADR 0108 Emenda 2): a tela mostra a coluna `piloto` ao lado da fonte e da data e a frase da API logo abaixo da tabela; a planilha leva a coluna `piloto` e a frase (aba `fontes` no XLSX); o `--json` passa tudo como veio. A CLI não escreve a frase: mostra a que a API mandou.
- Uma resposta cortada no limite do plano (`truncated`) ganha um aviso na tabela.
- Com `--planilha ARQUIVO` (em `empresa`, `comparaveis`, `eventos`, `vinculos`, `compradores`, `dossie`, `demonstracoes`, `fundo`, `setor` e `prospectar`), grava a resposta para o Excel, em
  vez de imprimir a tabela (pedido da Diretoria de 10/11: a equipe da casa de M&A leva os dados para o Excel).
  `.xlsx` dá uma aba por tabela da resposta, a aba `campos` (os campos soltos) e a aba `fontes` (atribuição,
  licença e o aviso); `.csv` dá um arquivo por tabela (`ARQUIVO-<tabela>.csv` quando há mais de uma), com `;`,
  vírgula decimal e BOM, que é o que o Excel em português abre direto. Cada linha leva as colunas `fonte` e
  `publicado_em`; os números vão como números. Texto que começa com `=`, `+`, `-` ou `@` ganha um apóstrofo no CSV
  (e no XLSX vai como texto), para o nome de uma empresa nunca virar fórmula. O XLSX é escrito com a biblioteca
  padrão (`cli/tickerlab/planilha.py`), sem dependência nova; os testes o leem com o `openpyxl`.

Os erros da API saem em português, na saída de erro, cada tipo com um código de saída. A lista inteira está em
`cli/tickerlab/instrucoes/AGENTS.md`, e um teste confere que ela bate com o código. Em resumo:

- `2`: comando errado.
- `3`: chave (falta ou foi recusada).
- `4`: limite ou quota. No limite do minuto, a CLI espera o `Retry-After` uma vez (até 60 segundos, avisando no
  stderr) e repete o pedido; só sai com `4` se o limite continuar, ou se for a quota do mês.
- `5`: nada disponível, que também cobre o campo que o portão não libera, para não contar o que existe.
- `6`: pedido recusado.
- `7`: fora do ar.

## Uso pelo agente de IA

O pacote leva as instruções do agente, que a CLI imprime:

```powershell
tickerlab instrucoes > AGENTS.md                                   # na pasta do projeto de quem analisa
tickerlab instrucoes skill > .claude/skills/tickerlab/SKILL.md     # a skill do Claude Code
```

As duas ensinam:

- os comandos e o que cada um devolve;
- usar `--json` para ler por programa;
- o que fazer com cada código de saída.

E trazem as travas:

- nada é recomendação de investimento;
- cite a fonte e a data de cada número;
- não invente número que a CLI não devolveu;
- conta própria sai separada;
- a chave é segredo;
- sem dado de pessoa física.

## Testes

`tests/test_cli_tickerlab.py` roda cada comando pelo `CliRunner` do click contra a API externa de verdade, montada
em memória: o `TestClient` do `src.api`, um banco novo, uma organização, uma chave e contratos de teste. Os testes
não usam internet e cobrem:

- os erros e os códigos de saída;
- login e logout;
- a pasta e a permissão do arquivo;
- o HTTPS;
- que a chave não aparece em nenhuma saída nem log;
- a planilha: abas, números como números, fonte e data por linha, CSV para o Excel e texto que não vira fórmula.

Para rodar: `.venv\Scripts\python -m pytest -q tests/test_cli_tickerlab.py`. O `pytest.ini` e o
`pyrightconfig.json` põem `cli/` no caminho, sem instalar o pacote.

Os comandos de M&A da linha 773 entram um por PR, quando a rota de cada um existe na API: `setor`, o perfil do
`empresa`, o `prospectar`, o `comparaveis`, o `eventos`, o `vinculos` e o `compradores` já estão aqui; `exportar` é o `--planilha` de cada comando (sem rota nova) e `precedentes` (783) segue travado pela licença. O
servidor MCP é a linha 570.
