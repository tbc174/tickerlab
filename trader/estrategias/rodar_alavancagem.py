"""Roda o núcleo (ficha P0-3, risk parity) a 1,0x e a 1,3x via WIN e via DI1 contra o critério.

    python -m trader.estrategias.rodar_alavancagem

**Cada execução conta como tentativa** da família P0-3 no registro `pesquisa_quant/registro.db`:
a base a 1,0x (a mesma configuração da ficha P0-3: a linha existente soma uma execução) e uma
configuração por instrumento (1,3x WIN e 1,3x DI1). Vizinhos, estresse, bruto, réguas, freios e
as verificações ficam dentro de cada tentativa (seção 9 do pré-registro). Só roda se o texto do
pré-registro for o aprovado (hash) e só com dados até o fim do desenvolvimento.

A alavancagem não tem sinal próprio: o item A6 (contra o acaso) usa os pesos da base, como na P0-3.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao, criterio_quant, freios
from trader.estrategias import (
    alavancagem,
    carteira_rp,
    dados_alavancagem,
    dados_p0_3,
    rodar_p0_3,
)
from trader.holdout import exigir_sem_holdout
from trader.registro import Registro

PASTA_DA_PESQUISA = dados_p0_3.PASTA_DA_PESQUISA
PASTA_DA_CURVA = dados_p0_3.PASTA_DA_CURVA
FICHA = rodar_p0_3.FICHA
CANDIDATO = rodar_p0_3.CANDIDATO
VIZINHOS = rodar_p0_3.VIZINHOS
FRACAO_DO_CORTE = rodar_p0_3.FRACAO_DO_CORTE
INSTRUMENTOS = alavancagem.INSTRUMENTOS
SEM_CUSTOS_DO_FUTURO = {"custos": carteira_rp.SEM_CUSTOS, "spread_por_lado": 0.0}
abrir_registro = rodar_p0_3.abrir_registro


def nome_da_versao(parametros: alavancagem.Parametros) -> str:
    if parametros.fator == 1.0:
        return "1,0x"
    return f"1,3x {parametros.instrumento}"


def versoes_pre_registradas() -> dict[str, alavancagem.Parametros]:
    """A 1,0x e a 1,3x por instrumento, nada entre elas."""
    todas = [alavancagem.Parametros(fator=1.0)] + [
        alavancagem.Parametros(fator=1.3, instrumento=i) for i in INSTRUMENTOS
    ]
    return {nome_da_versao(p): p for p in todas}


def carregar_curva(pasta: Path = PASTA_DA_CURVA) -> pd.DataFrame:
    arquivos = sorted(pasta.glob("*.parquet"))
    if not arquivos:
        raise FileNotFoundError(f"nenhuma curva de juros em {pasta}")
    return pd.concat(pd.read_parquet(a) for a in arquivos)


def carregar_tabelas(
    pasta: Path = PASTA_DA_PESQUISA, pasta_da_curva: Path = PASTA_DA_CURVA
) -> tuple[pd.DataFrame, pd.Series, pd.Series, dict[str, pd.Series]]:
    """As tabelas da P0-3 mais as pernas sintéticas dos futuros, só com o desenvolvimento."""
    precos, cdi, volumes = rodar_p0_3.carregar_tabelas(pasta)
    datas = pd.DatetimeIndex(precos.index)
    excessos = {
        "WIN": dados_alavancagem.excesso_do_win(precos["BOVA11"], cdi),
        "DI1": dados_alavancagem.excesso_do_di1(
            carregar_curva(pasta_da_curva), cdi, datas
        ),
    }
    for serie in excessos.values():
        exigir_sem_holdout(serie)
    return precos, cdi, volumes, excessos


def executar(
    precos: pd.DataFrame,
    cdi: pd.Series,
    volumes: pd.Series,
    excessos: dict[str, pd.Series],
    registro: Registro,
) -> dict:
    """Registra as tentativas, simula as versões, avalia cada uma e guarda no registro."""
    criterio_quant.conferir()
    base_parametros = carteira_rp.Parametros(esquema=CANDIDATO)
    spec_da_base = {
        **rodar_p0_3.especificacao_comum(precos),
        **base_parametros.especificacao(),
    }
    versoes = versoes_pre_registradas()
    ids = {
        nome: registro.registrar(FICHA, _nome_no_registro(p), _spec(spec_da_base, p))
        for nome, p in versoes.items()
    }
    cdi_alinhado = cdi.reindex(precos.index)

    def rodar_base(parametros: carteira_rp.Parametros) -> carteira_rp.Resultado:
        return carteira_rp.simular(precos, cdi, volumes, parametros)

    def alavancar(
        da_base: carteira_rp.Resultado, p: alavancagem.Parametros
    ) -> alavancagem.Resultado:
        return alavancagem.simular(
            da_base.retorno,
            cdi,
            excessos[p.instrumento],
            p,
            base_parametros.capital_inicial,
        )

    def sharpe_do_excesso(retorno: pd.Series) -> float:
        return avaliacao.sharpe(retorno - cdi_alinhado)

    base = rodar_base(base_parametros)
    base_estresse = rodar_base(
        carteira_rp.com(
            base_parametros,
            custos=base_parametros.custos.em_estresse(
                criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE
            ),
            fator_de_impacto=criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE,
        )
    )
    base_bruta = rodar_base(
        carteira_rp.com(
            base_parametros, custos=carteira_rp.SEM_CUSTOS, fator_de_impacto=0.0
        )
    )
    base_futuro = rodar_base(carteira_rp.com(base_parametros, olhar_o_futuro=True))
    base_de_novo = rodar_base(base_parametros)
    base_vizinhos = {
        nome: rodar_base(carteira_rp.com(base_parametros, **mudanca))
        for nome, mudanca in VIZINHOS.items()
    }
    regua_60_40 = rodar_base(carteira_rp.REGUA_60_40).retorno
    corte = precos.index[int(len(precos) * FRACAO_DO_CORTE)]
    cortar_a_base = carteira_rp.cortar_o_futuro_nao_muda_o_passado(
        precos, cdi, volumes, base_parametros, corte
    )
    acaso = carteira_rp.p_valor_do_acaso(
        base.pesos,
        precos.pct_change().fillna(0.0),
        cdi,
        base_parametros.custos.emolumentos_a_vista,
        sorteios=criterio_quant.SINAIS_DESLOCADOS,
    )
    tentativas_totais = (
        criterio_quant.tentativas_anteriores() + registro.total_para_o_dsr()
    )

    resultados = {nome: alavancar(base, p) for nome, p in versoes.items()}
    estresse = {
        nome: alavancar(
            base_estresse, p.em_estresse(criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE)
        )
        for nome, p in versoes.items()
    }
    candidatos = pd.DataFrame({n: r.retorno for n, r in resultados.items()})
    candidatos_estresse = pd.DataFrame({n: r.retorno for n, r in estresse.items()})
    reguas = {"60/40": regua_60_40, "CDI": cdi_alinhado}
    vereditos: dict[str, criterio_quant.Veredito] = {}
    vizinhos: dict[str, dict[str, float]] = {}
    brutos: dict[str, float] = {}
    for nome, p in versoes.items():
        bruto = alavancar(base_bruta, alavancagem.com(p, **SEM_CUSTOS_DO_FUTURO))
        futuro = alavancar(base_futuro, p)
        de_novo = alavancar(base_de_novo, p)
        vizinhos[nome] = {
            v: sharpe_do_excesso(alavancar(r, p).retorno)
            for v, r in base_vizinhos.items()
        }
        brutos[nome] = sharpe_do_excesso(bruto.retorno)
        cortar = cortar_a_base and alavancagem.cortar_o_futuro_nao_muda_o_passado(
            base.retorno,
            cdi,
            excessos[p.instrumento],
            p,
            corte,
            base_parametros.capital_inicial,
        )
        evidencia = criterio_quant.Evidencia(
            candidato=resultados[nome].retorno,
            cdi=cdi_alinhado,
            candidatos=candidatos,
            candidatos_estresse=candidatos_estresse,
            sharpe_bruto=brutos[nome],
            sharpes_vizinhos=vizinhos[nome],
            reguas=reguas,
            p_valor_do_acaso=acaso["p_valor"],
            sharpe_olhando_o_futuro=sharpe_do_excesso(futuro.retorno),
            reexecucao_identica=alavancagem.hash_do_resultado(de_novo)
            == alavancagem.hash_do_resultado(resultados[nome]),
            cortar_o_futuro_nao_muda=cortar,
            tentativas_totais=tentativas_totais,
            nome_do_candidato=nome,
        )
        vereditos[nome] = criterio_quant.avaliar(evidencia)

    freados = {
        nome: freios.aplicar_freio(r.retorno, cdi) for nome, r in resultados.items()
    }

    def resumo(nome: str, r: alavancagem.Resultado) -> dict:
        return {
            **avaliacao.resumir_serie(r.retorno),
            "sharpe_do_excesso": sharpe_do_excesso(r.retorno),
            "exposicao_media": float(r.exposicao.mean()),
            "custo_de_rolagem_por_ano": r.custo_de_rolagem_por_ano(),
            "custos_do_futuro": float(r.custos.sum()),
            "dias_com_margem_acima": r.dias_com_margem_acima(),
            "rolagens": len(r.rolagens),
            "cai_para_1_0x": alavancagem.cai_para_1_0x(r),
        }

    resumos = {
        nome: {
            **resumo(nome, r),
            "queda_com_freio": avaliacao.maior_queda(freados[nome].retorno),
            "disparos_do_freio": [d.date().isoformat() for d in freados[nome].disparos],
            "voltas_do_freio": [d.date().isoformat() for d in freados[nome].voltas],
        }
        for nome, r in resultados.items()
    }
    resumos_estresse = {nome: resumo(nome, r) for nome, r in estresse.items()}
    resumo_das_reguas = {nome: avaliacao.resumir_serie(r) for nome, r in reguas.items()}
    aprovadas_1_3 = [n for n in versoes if n != "1,0x" and vereditos[n].aprovado]
    versao = alavancagem.versao_que_entra(
        aprovada_1_0=vereditos["1,0x"].aprovado, aprovada_1_3=bool(aprovadas_1_3)
    )
    for nome, tentativa in ids.items():
        registro.salvar_resultado(
            tentativa,
            {
                "resumo": resumos[nome],
                "estresse": resumos_estresse[nome],
                "veredito": vereditos[nome].para_registro(),
                "vizinhos": vizinhos[nome],
                "bruto": brutos[nome],
                "reguas": resumo_das_reguas,
                "acaso": acaso,
                "tentativas_totais": tentativas_totais,
                "versao_que_entra": versao,
            },
        )
    return {
        "ids": ids,
        "vereditos": vereditos,
        "resumos": resumos,
        "estresse": resumos_estresse,
        "reguas": resumo_das_reguas,
        "vizinhos": vizinhos,
        "brutos": brutos,
        "acaso": acaso,
        "tentativas_totais": tentativas_totais,
        "versao_que_entra": versao,
        "aprovadas_1_3": aprovadas_1_3,
        "periodo": (spec_da_base["inicio"], spec_da_base["fim"]),
    }


def _nome_no_registro(p: alavancagem.Parametros) -> str:
    if p.fator == 1.0:
        return f"p0_3_{CANDIDATO}"
    return f"p0_3_{CANDIDATO}_1_3x_{p.instrumento.lower()}"


def _spec(spec_da_base: dict, p: alavancagem.Parametros) -> dict:
    """A 1,0x é a própria tentativa da P0-3 (mesmo hash); a 1,3x soma a alavancagem."""
    if p.fator == 1.0:
        return spec_da_base
    return {**spec_da_base, **p.especificacao()}


def _linha(nome: str, r: dict) -> str:
    return (
        f"| {nome} | {r['sharpe_do_excesso']:.2f} | {r['sharpe']:.2f} | {r['retorno_anual']:.1%} | "
        f"{r['volatilidade_anual']:.1%} | {r['maior_queda']:.1%} | {_queda_com_freio(r)} | "
        f"{r['custo_de_rolagem_por_ano']:.3%} | {r['dias_com_margem_acima']} | {r['exposicao_media']:.2f} |"
    )


def _queda_com_freio(resumo: dict) -> str:
    """O freio só é simulado nos custos base; no estresse a coluna fica vazia."""
    return (
        "-" if "queda_com_freio" not in resumo else f"{resumo['queda_com_freio']:.1%}"
    )


def _veredito_em_linhas(nome: str, veredito: criterio_quant.Veredito) -> list[str]:
    situacao = "APROVADA" if veredito.aprovado else "REPROVADA"
    if veredito.reprovados:
        situacao += f" (falhou em {', '.join(veredito.reprovados)})"
    if veredito.inconclusivo:
        situacao += f"; inconclusivo: {veredito.motivo_inconclusivo}"
    return [
        f"### {nome}: {situacao}",
        "",
        "| Item | O quê | Valor | Limite | Passou |",
        "|---|---|---|---|---|",
        *(
            f"| {i.codigo} | {i.descricao} | {'-' if i.valor is None else f'{i.valor:.3f}'} | {i.limite} | {'sim' if i.passou else 'NÃO'} |"
            for i in veredito.itens
        ),
        "",
    ]


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    cabecalho = (
        "| Versão | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | "
        "Maior queda com freio 40% | Custo de rolagem/ano | Dias com margem > 30% | Exposição média |\n"
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    inicio, fim = saida["periodo"]
    versao = saida["versao_que_entra"]
    linhas = [
        f"# Núcleo (ficha P0-3) a 1,0x e 1,3x: rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Dados de {inicio} a {fim} (desenvolvimento; holdout lacrado).",
        f"Tentativas contadas no DSR: {saida['tentativas_totais']}.",
        "",
        f"**Versão que entra: {'nenhuma' if versao is None else f'{versao:.1f}x'.replace('.', ',')}**"
        + (
            f" (1,3x aprovada via {', '.join(saida['aprovadas_1_3'])})"
            if saida["aprovadas_1_3"]
            else ""
        ),
        "",
        "## Veredito de cada versão (seção 5 do pré-registro)",
        "",
        *(
            linha
            for nome, veredito in saida["vereditos"].items()
            for linha in _veredito_em_linhas(nome, veredito)
        ),
        "## As versões (custos base)",
        "",
        cabecalho,
        *(_linha(nome, r) for nome, r in saida["resumos"].items()),
        "",
        "## Estresse (custos × 2, impacto Y = 2, spread × 2)",
        "",
        cabecalho,
        *(_linha(nome, r) for nome, r in saida["estresse"].items()),
        "",
        "## Freio por camada (40%)",
        "",
        *(
            f"- {nome}: disparos {r['disparos_do_freio'] or 'nenhum'}; voltas {r['voltas_do_freio'] or 'nenhuma'}"
            for nome, r in saida["resumos"].items()
        ),
        "",
        "## Réguas, platô e bruto",
        "",
        "| Régua | Sharpe | Retorno anual | Maior queda |",
        "|---|---|---|---|",
        *(
            f"| {n} | {'-' if n == 'CDI' else f'{r['sharpe']:.2f}'} | {r['retorno_anual']:.1%} | {r['maior_queda']:.1%} |"
            for n, r in saida["reguas"].items()
        ),
        "",
        "| Versão | Vizinho | Sharpe do excesso |",
        "|---|---|---|",
        *(
            f"| {nome} | {v} | {s:.2f} |"
            for nome, vizinhos in saida["vizinhos"].items()
            for v, s in vizinhos.items()
        ),
        *(f"| {nome} | bruto | {s:.2f} |" for nome, s in saida["brutos"].items()),
        "",
        "## Limites e cuidados",
        "",
        "- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.",
        (
            "- Não há histórico do WIN nem do DI1 na base: o WIN é o BOVA11 menos o CDI e o DI1 é "
            "um prefixado de 2 anos marcado na curva do Tesouro menos o CDI (sem a base de mercado)."
        ),
        "- Margem exigida, valor do contrato e spread são aproximações marcadas 'a confirmar'; contratos fracionários.",
        "- O caixa de margem pode ficar negativo dentro do mês (empréstimo ao CDI) até o ajuste do primeiro pregão.",
        "- O item A6 (contra o acaso) é o da base: a alavancagem não tem sinal próprio.",
        "- A 1,3x só entra se passar o critério inteiro, inclusive F1; nada entre 1,0x e 1,3x.",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_alavancagem_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    precos, cdi, volumes, excessos = carregar_tabelas()
    saida = executar(precos, cdi, volumes, excessos, abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
