# A CLI `tickerlab`: a API externa no terminal e no agente de IA

A CLI `tickerlab` (linha 772 da fila, ADR 0127) é um cliente fino da API externa de dados (`/data/v1`). Ela pega a
resposta da API e a mostra numa tabela, para a pessoa, ou no envelope JSON inteiro, para o agente de IA de quem
analisa empresas (Claude Code, Codex e outros). Ela não tem regra própria: a chave, a quota, o contrato, o portão de
licença e o "como era" são todos da API, e a CLI só repassa o que a API serviu.

O código fica em `cli/`. É um pacote à parte, que depende só de `click` e `httpx` e não importa nada de `src/` nem de
`base/` (há teste que cobra), para não levar o resto do repositório ao PC de quem o instala.

## Instalar

```powershell
pip install "git+https://github.com/tbc174/tickerlab#subdirectory=cli"   # de um ramo ou da main
pip install -e cli                                                        # no repositório, para mexer
```

Publicar o pacote (PyPI, Homebrew) e escolher o nome público dele são decisões do Tiago (nível 1). Até lá, a
instalação é pelo Git.

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
| `tickerlab demonstracoes <cnpj> [--como-era ...] [--periodo AAAA-MM-DD]` | `GET /data/v1/companies/{cnpj}/financials` | sim |
| `tickerlab fundo <cnpj> [--como-era ...] [--retorno-suposto 0.12]` | `GET /data/v1/funds/{cnpj}` | sim |
| `tickerlab setor` | `GET /data/v1/sectors` | não |
| `tickerlab setor <chave> [--como-era ...]` | `GET /data/v1/sectors/{key}` | sim |
| `tickerlab catalogo` | `GET /data/v1/catalog` | não |
| `tickerlab consumo` | `GET /data/v1/usage` | não |

- `tickerlab empresa` pede o perfil (linha 736): o cadastro na Receita e, da companhia aberta, cada DFP e ITR
  devida até o dia, com o prazo da CVM, a primeira entrega, os dias úteis de atraso e a situação (`on_time`,
  `gray_zone`, `late`, `severely_late`, `not_filed`), mais os limites da leitura (`limits`). O perfil pede o
  conjunto `profiles` no contrato; a chave que tem só `companies` usa `--so-cadastro`.
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
- Uma resposta cortada no limite do plano (`truncated`) ganha um aviso na tabela.
- Com `--planilha ARQUIVO` (em `empresa`, `demonstracoes`, `fundo` e `setor`), grava a resposta para o Excel, em
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
- `4`: limite ou quota.
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

Os comandos de M&A da linha 773 entram um por PR, quando a rota de cada um existe na API: `setor` e o perfil do
`empresa` já estão aqui; os eventos, os vínculos e os comparáveis esperam as outras rotas da linha 736; `exportar` e `precedentes`, as linhas 782 e 783. O
servidor MCP é a linha 570.
