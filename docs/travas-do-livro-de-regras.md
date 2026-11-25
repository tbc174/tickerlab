# Travas do livro de regras: o que garante cada regra do `AGENTS.md`

Regra sem exceção não fica só no texto: vira teste, passo do CI ou proteção do GitHub. Esta página diz, para as
regras do `AGENTS.md` e do `trader/AGENTS.md` que valem para o código, **o que garante cada uma hoje**. Conferido
em 25/11/2026 lendo os testes, o `.github/workflows/testes.yml` e a proteção da `main` no GitHub.

- **Máquina:** um teste, um passo do CI ou a proteção da `main` barra quem quebra a regra.
- **Em parte:** há trava, mas ela não cobre todos os casos (o que fica de fora está na linha).
- **Só texto:** nada barra; vale a disciplina de quem trabalha. É o risco que sabemos que temos.

Regra nova com trava entra aqui, com o nome do teste.

## Arquitetura e código

| Regra | O que garante | Classe |
|---|---|---|
| `src/` não importa o Streamlit | `tests/test_travas_do_livro_de_regras.py::test_src_nao_importa_o_streamlit` | máquina |
| Nenhum estado mutável num módulo de `telas/` | `test_telas_nao_guardam_estado_no_modulo` (pega `global` e lista ou dicionário do módulo mudado dentro de função; não pega objeto mutável criado de outro jeito) | em parte |
| Limites dos planos num lugar só (`src/planos.py`) | `tests/test_limites_iguais.py` | máquina |
| Cores e fontes em `src/marca.py` | `tests/test_marca.py` | em parte |
| Endereços de `src/paginas.py` estáveis | `tests/test_paginas.py` | em parte |
| Pastas geradas (`site/`, `novo/`, `web/conteudo/`) iguais aos geradores | passos do CI "Ferramentas do site" e "App em React", `tests/test_exportar_conteudo.py` | máquina |
| Tabela de órgão público com CNPJ entra num tema da vitrine | `tests/test_vitrine_da_base.py` | máquina |
| Código morto não piora | passo do CI "vulture" (`scripts/conferir_codigo_morto.py`) | máquina |
| Tipos e estilo | passos do CI "ruff" e "pyright" | máquina |
| Raiz trancada | `tests/test_raiz_do_repositorio.py` | máquina |
| Dependência pinada é dependência usada | `tests/test_requirements.py` | máquina |
| Todo `scripts/*.py` diz quem o roda | `tests/test_scripts_dizem_quem_roda.py` | máquina |
| Mudança só de texto roda só os testes do README | `scripts/mudou_so_texto.py` e `tests/test_mudou_so_texto.py` | máquina |
| Teste novo do trader se chama `test_trader_*` ou `test_c1_*` | indireto: `scripts/repartir_testes.py` manda os outros nomes às partes sem as bibliotecas do trader, onde quebram | em parte |

## Banco

| Regra | O que garante | Classe |
|---|---|---|
| `hide_parameters=True` | `test_toda_engine_do_codigo_esconde_os_valores_das_consultas` e `test_a_engine_do_app_esconde_os_valores` | máquina |
| Migração com numeração seguida | `test_migracoes_numeradas_em_fila_sem_buraco_novo` e `test_as_migracoes_formam_uma_fila_so_sem_ramo` (os números 33 e 38 já faltavam) | máquina |
| Migração nova tem `downgrade` | `test_toda_migracao_tem_caminho_de_volta` (confere que existe e não é vazio; testar a volta continua por migração, como em `tests/test_migracao_0048.py`) | em parte |
| Toda consulta filtra pelo `usuario_id`, com teste de isolamento | testes de duas contas por função (ex.: `tests/test_alertas.py`); nada confere a consulta nova que vier sem teste | em parte |
| Migrações ao mesmo tempo esperam a vez | `tests/test_banco_trava_das_migracoes.py` | máquina |

## Cobrança e acesso

| Regra | O que garante | Classe |
|---|---|---|
| Stripe só em modo de teste | `tests/test_cobranca.py::test_chave_que_nao_e_de_teste_e_recusada` | máquina |
| O plano só muda pelo webhook (assinado, idempotente, fora de ordem) | `tests/test_cobranca.py` | máquina |
| Pessoa física na tela só com a permissão da organização | testes de duas organizações nas rotas (`tests/test_api_v1_analista_titular.py` e vizinhos) | máquina |
| API externa nega por padrão | `tests/test_portao_externo.py` | máquina |
| PDF tem a seção "Limites e cuidados" | `tests/test_amostra_do_relatorio.py` e vizinhos | máquina |

## Segurança, privacidade e licença

| Regra | O que garante | Classe |
|---|---|---|
| Segredo fora do Git | `test_nenhum_arquivo_de_segredo_no_git` (nomes de arquivo) e o passo do CI "Procurar chaves da API" (formato das chaves da API) | em parte |
| Nenhum e-mail pessoal versionado | `test_nenhum_email_pessoal_versionado` (provedores de e-mail pessoal; não roda nos PRs só de texto) | em parte |
| Nenhum CPF que confere em teste ou exemplo | `tests/test_exemplos_sem_cpf.py` | máquina |
| Logs sem e-mail nem nome | `hide_parameters` acima; o texto de cada log não é conferido | em parte |
| Sem `LICENSE` e sem dependência GPL/AGPL | `test_repositorio_sem_arquivo_de_licenca_aberta`, `test_nenhuma_biblioteca_instalada_e_gpl` e o passo do CI "Licenças permitidas" (pacotes do `web/`) | máquina |
| Endereço de servidor ou IP fora do código | nada ainda | só texto |
| Nome de pessoa em código, log ou teste | nada | só texto |

## Git e GitHub

| Regra | O que garante | Classe |
|---|---|---|
| Nada entra na `main` sem PR e CI verde | proteção da `main`: PR obrigatório, checks `testes`, `imagem Docker`, `web (React)` e `o que mudou`, vale também para administrador | máquina |
| Sem push forçado na `main` | proteção da `main` (`allow_force_pushes` desligado) | máquina |
| Ramo `claude/agente-*` só entra sozinho com teste e doc | passo do CI "Portão do agente" e `tests/test_portao_do_agente.py` | máquina |
| Área sensível mescla só depois das duas revisões | a proteção pede 0 aprovações; nada confere a revisão de segurança nem a cruzada | só texto |
| Mensagem de commit `tipo: o que mudou` e `Co-Authored-By` | nada | só texto |
| `Feito por:` no corpo do PR | nada | só texto |
| Nunca `git add -A` sem conferir o `git status` | a raiz trancada pega arquivo solto na raiz; fora dela, nada | em parte |

## Trader (`trader/AGENTS.md`)

| Regra | O que garante | Classe |
|---|---|---|
| Só leitura: nenhum módulo envia ordens | `tests/test_trader_mt5.py` | máquina |
| Critério vigente com o SHA-256 conferido | `trader/holdout.py`, `trader/criterio_quant.py` e `tests/test_trader_holdout.py`, `tests/test_trader_criterio_quant.py` | máquina |
| Versões superadas do pré-registro não se editam | quant v0.1 por `trader/criterio_quant.py`; M2 v0.1 a v0.3 por `test_pre_registro_antigo_da_m2_continua_igual` | máquina |
| Holdout lacrado | `tests/test_trader_holdout.py` | máquina |
| Toda execução é uma tentativa | o registro em `trader/registro.py` e os testes `tests/test_trader_*_rodada.py` | em parte |
| Um modelo por vez | nada no repositório | só texto |
