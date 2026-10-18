# TickerLab: instruções para revisores e auditores automáticos (Codex e outros)

Você está aqui como **auditor**: lê o código e aponta problemas. **Não mude nada:** sem commit, sem
push, sem PR, sem editar arquivos fora de uma pasta temporária sua. Quem corrige é o autor, por PR
com teste e CI verde.

As regras de código do projeto estão em [`CLAUDE.md`](CLAUDE.md) (arquitetura, testes, banco, Git) e
em [`docs/padroes-de-codigo.md`](docs/padroes-de-codigo.md). Leia o `CLAUDE.md` antes de auditar: um
achado que contradiz uma regra escrita lá provavelmente é real. Visão geral: [`README.md`](README.md).

O repositório é **público**. Se encontrar um segredo, uma senha, um IP de servidor ou um e-mail
pessoal versionado, isso é achado grave: descreva onde está, **sem copiar o valor**.

## O que é

SaaS de análise de ações (B3 e EUA) e teste de estratégias com dados do passado. Python 3.12,
Pandas, Streamlit (`app.py`, `telas/`), FastAPI (`src/api.py`, `src/api_v1/`), SQLAlchemy 2 +
Alembic + PostgreSQL, Stripe **só em modo de teste**, React em `web/` (gera `site/` e `novo/`, o app
principal em `app.tickerlab.com.br`; o Streamlit é a versão clássica, em `/classico/`).
`base/` é a base de dados para machine learning (coletas públicas da CVM, Receita, B3 etc.).
`trader/` é uma pesquisa pausada: fora do escopo.

## Como rodar

```bash
python -m pip install -r requirements.txt
python -m pytest -q -n 4 --dist loadgroup   # suíte inteira (~2 min); sem internet, usa dados_de_exemplo/
python -m pytest -q tests/test_planos.py     # um arquivo
python -m ruff check .
python -m pyright
```

Os testes não precisam de internet nem de segredos. Se um teste precisar de PostgreSQL e não houver,
anote e siga com os demais.

## Mapa de risco (onde procurar primeiro)

| Risco | Onde |
|---|---|
| **Alto** | login e admins (`src/autenticacao.py`, `src/administracao.py`; OAuth do Google, `TICKERLAB_ADMINS`, `TICKERLAB_AMBIENTE`); API (`src/api.py`, `src/api_v1/`); cobrança e webhook do Stripe (`src/cobranca.py`: assinatura verificada, idempotência, eventos fora de ordem); limites dos planos (`src/planos.py` e quem os confere); **consulta ao banco sem filtro por `usuario_id`** (vazamento entre contas); SQL montado com texto; migrações (`migracoes/versions/`); compartilhamento por link (`src/compartilhamentos.py`, `src/api_v1/compartilhados.py`); coletas que baixam URL vinda de dado (SSRF); PDF e e-mail com texto do usuário; `Dockerfile`, `compose.yaml`, `.github/workflows/` |
| **Alto (dados)** | **olhar o futuro**: em `base/`, `src/backtest.py`, indicadores e rótulos, um dado só pode ser usado a partir da data em que ficou público (colunas como `disponivel_em`, `visto_em`) |
| **Médio** | regras de negócio (backtest, Research, Radar), estado gravado no banco, telas que mostram dados da conta, exportação e exclusão da conta (LGPD, `src/conformidade.py`) |
| **Baixo** | textos, CSS, documentação, logs (exceto log com e-mail ou nome: isso é médio) |

## Como relatar um achado

Um achado por bloco, do mais grave ao menos grave:

```
### [P0|P1|P2] Título curto
- Arquivo e linha: `src/x.py:123`
- O que está errado (uma frase)
- Cenário concreto: quem (visitante, conta Gratuita, outra conta, webhook falso, dado de entrada),
  o que faz, passo a passo, e o que acontece de errado
- Como reproduzir: um teste ou comando, se possível
- Confiança: alta | média | baixa
```

- **P0:** perda ou vazamento de dados, acesso indevido, cobrança errada, dado do futuro no passado.
- **P1:** resultado errado para o usuário ou na base, sem vazamento.
- **P2:** robustez (erro não tratado, caso de borda) com efeito real.

Não relate estilo, nomes, formatação, "talvez fosse melhor", nem sugestões de refatoração: o projeto
tem `ruff` e `pyright` no CI para isso. Sem cenário concreto, escreva "suspeita" no título e use
confiança baixa. Prefira poucos achados certos a muitos duvidosos.

## Review guidelines

Para revisão de pull request:

- Revise só o que o PR muda e o que essas linhas afetam; aponte apenas P0 e P1.
- Toda consulta nova ao banco filtra pelo `usuario_id` e tem teste com duas contas.
- Webhook do Stripe: assinatura verificada antes de qualquer efeito; nenhuma chave que não seja de teste.
- Nada de segredo, e-mail ou nome de pessoa em código, log ou teste.
- Em `base/` e no backtest: nenhum dado usado antes da data em que ficou público.
- Migração nova tem caminho de volta (`downgrade`) e não apaga dado sem aviso.
