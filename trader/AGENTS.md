# `trader/`: regras da pesquisa de trading (TickerLab Trade)

Vale junto com o `AGENTS.md` da raiz do repositório (regras de todas as IAs). Este pacote roda **no PC (Windows)**, fica
fora do app publicado e da imagem Docker, e conecta no MetaTrader 5 **só para ler**.

## Regras que não se quebram

1. **Só leitura.** Nenhum módulo envia ordens (há teste que impede `order_send` e parecidos). Código
   de ordens só existe a partir da fase M3, em conta demo, com autorização escrita do Tiago.
2. **Critério antes dos resultados.** O critério vigente é `docs/pre-registro-m2-v0.4.md` (o
   SHA-256 fica em `trader/holdout.py`). Mudar qualquer coisa nele = versão nova, com data, **+25
   tentativas**, aprovação do Tiago e cópia do registro antes.
3. **Toda execução é uma tentativa.** `python -m trader.rodar_modelo` e `rodar_baselines` gravam no
   registro (`pesquisa_m2/registro.db`) e deixam o Sharpe deflacionado mais exigente. **Não rode
   "só para ver"**, não repita uma rodada sem motivo e não proponha variações de um modelo
   reprovado para fazê-lo passar.
4. **Holdout lacrado.** Pesquise só com `holdout.carregar_desenvolvimento`. Os últimos 3 anos só
   podem ser usados uma vez, por um candidato aprovado, com decisão do Tiago.
5. **Um modelo por vez.** As rodadas usam os 8 núcleos (joblib) e o mesmo registro. Antes de lançar,
   confira se já há um `rodar_modelo` ativo; não rode a suíte de testes inteira enquanto um modelo
   roda. Rodadas longas: em segundo plano, com log em arquivo, num processo que sobreviva à sessão.
6. **Dados:** trocar ou acrescentar fontes só ao começar uma pesquisa nova (não no meio da M2).

## Comandos

```powershell
abrir_painel_trader.bat                                   # painel (janela nativa, só leitura)
.venv\Scripts\python -m trader.rodar_modelo --modelo logistica|floresta|lightgbm|arima|mlp|lstm|tcn [--por-classe] [--meta]
.venv\Scripts\python -m trader.rodar_baselines
.venv\Scripts\python -m trader.baixar_historico            # MT5 + Yahoo para dados_mt5/
.venv\Scripts\python -m trader.atualizar_b3                # boletim diário da B3 (agendado, seg–sex 20h)
.venv\Scripts\python -m trader.atualizar_juros             # taxas do BIS
```

Dependências extras: `requirements-trader.txt` (scikit-learn, LightGBM, statsmodels, PyTorch CPU,
numba, joblib, MetaTrader5, PySide6).

## Onde fica cada coisa

| O quê | Onde |
|---|---|
| Critério em código (A1–A10, V, B, C) | `criterio.py`; vazamento em `vazamento.py` |
| Validação (CPCV 45 divisões, 9 caminhos, expurgo e embargo 21; bootstrap) | `validacao.py` |
| Atributos e rótulo (5 pregões) | `atributos.py` |
| Pipeline (sinal, posição, custos, variantes do vazamento) | `pipeline.py`, `posicao.py`, `custos.py`, `backtest.py` |
| Modelos | `modelos.py` (H1/H2), `redes.py` (H4), `arima.py` (H5) |
| Registro de tentativas e holdout | `registro.py`, `holdout.py` |
| Universo e grupos | `universo.py` |
| Diário das operações e ficha da tentativa | `diario.py`, `ficha.py` |
| Leitura que recusa dado ausente; balanço só depois de público | `base_local.py` |
| Aquecimento das janelas e cobertura | `aquecimento.py` |
| VaR/CVaR históricos e Benjamini-Hochberg | `quant.py` |
| Catálogo de fatores candidatos (nenhum medido) | `fatores/` |
| Scalp no mini índice, fase 1 (pesquisa à parte da M2; reprovada em 29/10/2026) | `scalp_win.py`; critério em `docs/pre-registro-scalp-win-fase1.md`, resultado em `docs/resultado-scalp-win-fase1.md` |
| Conferência dos custos (B3 à vista) e da validação | `docs/trader-conferencia-custos-e-validacao.md` |
| Painel | `interface/` |

Pastas fora do Git (no PC): `dados_mt5/`, `dados_b3/`, `dados_juros/` e **`pesquisa_m2/`**
(registro, relatórios de cada rodada e cópias de segurança em `pesquisa_m2/copias/`).

## Ao terminar uma rodada

1. Ler o veredito no relatório (`pesquisa_m2/relatorios/`) e no registro.
2. Anotar no histórico do projeto e no relatório da M2 (pasta privada `projeto-acoes/`).
3. Fazer uma cópia do registro se a rodada foi importante.
