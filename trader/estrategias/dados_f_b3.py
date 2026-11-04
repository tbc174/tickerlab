"""Dados da ficha F-B3: COTAHIST anual da B3, FCA (cadastro) e balanços ponto no tempo do acervo.

De onde vem cada tabela de `fatores_b3.Dados`:

| Tabela | Fonte | Situação em 03/11/2026 |
|---|---|---|
| fechamento, abertura, volume | COTAHIST anual (`COTAHIST_A<ano>.ZIP`, mercado à vista) de 2009 a 2023, na pasta da ficha | **falta**: o acervo só tem o COTAHIST diário desde 09/2026 e o lote anual de 1986 a 2009 |
| preços ajustados | `precos_ajustados.parquet` (fechamento ajustado por desdobramentos e proventos, mesmas datas e tickers) | **falta**: não há base de preços ajustados; `eventos_de_capital` e `proventos` do acervo vão até 2023 e permitem construí-la |
| cadastro | ISIN do COTAHIST (posições 3 a 6 = emissor) → `fca/emissores.parquet` e, para quem saiu antes de 2018, `emissores_antigos.csv` (ligação pelo nome, conferida por dois modelos); classe pela especificação; datas do FCA quando houver | pronto (emissores do FCA desde 2018 e 77 antigos) |
| fundamentos | `demonstracoes/<ano>.parquet` do acervo, consolidado, com `divulgado_em` e `ate` | pronto (2010 em diante) |
| acoes | `acoes_em_circulacao.parquet` (CNPJ, quantidade, data em que ficou pública), montada por `gravar_acoes` | o capital integralizado do Formulário de Referência (`bruto/cvm-hist-fre` do acervo, desde 2010) e, desde 2020, da composição do capital da DFP e do ITR (`cvm/` na pasta da ficha); cada número vale do dia em que a CVM recebeu o documento; o erro de unidade (milhares) sai em `corrigir_quantidade`, pelo preço e pelo volume |
| recuperacao_judicial | `insolvencia/<ano>.parquet` do acervo: episódios de `episodios_de_recuperacao_judicial` | pronto |
| preco_por_acao | o COTAHIST bruto: o fechamento da ON ou da PN com mais volume no dia | pronto |
| cdi, ibovespa | SGS 12 (cache da pesquisa) e BOVA11 do export do MT5 | pronto |

`conferir_base` lista o que falta; com faltas, a rodada da ficha para antes de registrar qualquer
tentativa (pré-registro v0.1, seção 2: sem as deslistadas não há resultado honesto). Nada aqui
baixa nada da internet; os ZIPs da CVM e da B3 são lidos como dados (rode com `python -I`). `carregar_tabelas` monta tudo quando a base existir e ainda não foi
exercitada com dados reais (limitação declarada no relatório).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from trader.estrategias import dados_p0_3
from trader.estrategias.fatores_b3 import (
    CLASSES_DE_ACAO,
    COLUNAS_DAS_ACOES,
    COLUNAS_DO_CADASTRO,
    COLUNAS_DOS_FUNDAMENTOS,
    CONTAS_USADAS,
    PREGOES_DA_LIQUIDEZ,
    Dados,
)
from trader.holdout import (
    FIM_DO_DESENVOLVIMENTO,
    exigir_sem_holdout,
    recortar_desenvolvimento,
)

PASTA_DA_PESQUISA = dados_p0_3.PASTA_DA_PESQUISA
PASTA_DA_FICHA = PASTA_DA_PESQUISA / "f_b3"
PASTA_DO_ACERVO = (
    dados_p0_3.PASTA_DA_CURVA.parent
)  # a cópia local do acervo (`acervo/base`)
PRIMEIRO_ANO = (
    2009  # 12 meses de pregão e de balanço antes da primeira decisão, em 2010
)
ULTIMO_ANO = 2023  # o desenvolvimento acaba em 08/09/2023
ARQUIVO_DE_PRECOS_AJUSTADOS = "precos_ajustados.parquet"
ARQUIVO_DE_ACOES = "acoes_em_circulacao.parquet"
PASTA_DO_FRE = PASTA_DO_ACERVO.parent / "bruto" / "cvm-hist-fre"
PASTA_DA_CVM = (
    PASTA_DA_FICHA / "cvm"
)  # DFP e ITR baixados da CVM (SHA256SUMS.txt ao lado)
CODIFICACAO_DA_CVM = "latin-1"
# Quantidade de ações: o capital integralizado (ON + PN), sem descontar a tesouraria, a mesma
# medida nas duas fontes (o FRE não traz a tesouraria). A DFP e o ITR só têm a composição do
# capital desde 2020; antes, só o Formulário de Referência.
CAPITAL_INTEGRALIZADO = "Capital Integralizado"
# A CVM não diz se a quantidade de ações está em unidades ou em milhares, e as empresas usam as
# duas, no FRE e na DFP e no ITR. Um número que difere do anterior por uma potência de 10 (com
# esta folga) é erro de unidade, a não ser que o preço bruto confirme um desdobramento.
FOLGA_DA_ESCALA = 0.05
# A série inteira pode vir em milhares desde o primeiro documento. Dois limites que nenhuma ação
# da B3 atinge denunciam o nível errado (em potências de mil): o volume médio de 21 pregões
# acima de 20% do valor de mercado por dia, ou um valor de mercado acima de R$ 2 trilhões.
GIRO_MAXIMO = 0.20
VALOR_DE_MERCADO_MAXIMO = 2e12
MIL = 1000.0
VEZES_DO_NIVEL = 2  # milhares de milhares, no máximo
CLASSES_DO_PRECO_POR_ACAO = (
    "ON",
    "PN",
)  # a unit junta várias ações: o preço dela não é o de uma
# Recuperação judicial (seção 8): a CVM não tem um evento de "encerrada", e quem está em
# recuperação manda documento todo mês (relatório do administrador judicial). Um episódio vai do
# primeiro documento até 12 meses depois do último; 12 meses sem documento fecham o episódio (a
# mesma regra de `trader/agentes/dados.py`). O rótulo ambíguo conta, para não deixar entrar quem
# pode estar em recuperação; extrajudicial e falência ficam fora (a ficha diz "judicial").
ROTULOS_DE_RECUPERACAO_JUDICIAL = (
    "recuperacao_judicial",
    "recuperacao_judicial_ou_extrajudicial",
)
MESES_SEM_DOCUMENTO = 12
COLUNAS_DA_RECUPERACAO = ("cnpj", "inicio", "fim")
TIPO_DE_REGISTRO = "01"
MERCADO_A_VISTA = "010"
CENTAVOS = 100
GRUPO_CONSOLIDADO = "con"
POSICOES_DO_EMISSOR_NO_ISIN = slice(2, 6)
# Posições do layout COTAHIST (registro 01, 245 posições), as mesmas de base/intradiario_b3.py.
CAMPOS = {
    "tipo": (0, 2),
    "data": (2, 10),
    "ticker": (12, 24),
    "mercado": (24, 27),
    "especificacao": (39, 49),
    "abertura": (56, 69),
    "fechamento": (108, 121),
    "volume": (170, 188),
    "fator_de_cotacao": (210, 217),
    "isin": (230, 242),
    "distribuicao": (242, 245),  # DISMES: muda no dia ex de desdobramento e de provento
}
# Emissores que saíram antes de 2018 (o FCA do acervo só liga ticker a CNPJ desde então): o CNPJ
# pelo nome de pregão, escolhido às cegas por dois modelos nos nomes da CVM do acervo; quem
# discordou ou não achou fica sem CNPJ (conferência automática, sem o Tiago).
ARQUIVO_DOS_EMISSORES_ANTIGOS = Path(__file__).with_name("emissores_antigos.csv")
COLUNAS_DOS_EMISSORES_ANTIGOS = (
    "emissor",
    "cnpj",
    "nome_no_pregao",
    "empresa_na_cvm",
    "conferencia",
)


def nome_do_cotahist(ano: int) -> str:
    return f"COTAHIST_A{ano}.ZIP"


def conferir_base(pasta: Path = PASTA_DA_FICHA, *, com_acoes: bool = True) -> list[str]:
    """Os arquivos que faltam para a ficha rodar; lista vazia quando dá para rodar.

    `com_acoes=False` serve às fichas que não usam a quantidade de ações (P0-4, pares).
    """
    esperados = [nome_do_cotahist(ano) for ano in range(PRIMEIRO_ANO, ULTIMO_ANO + 1)]
    esperados.append(ARQUIVO_DE_PRECOS_AJUSTADOS)
    if com_acoes:
        esperados.append(ARQUIVO_DE_ACOES)
    return [nome for nome in esperados if not (pasta / nome).exists()]


def ler_cotahist_anual(caminho: Path) -> pd.DataFrame:
    """Um ZIP anual da B3 em formato longo: data, ticker, isin, especificação, preços e volume.

    Só o mercado à vista em lote padrão (010); preços e volume vêm em centavos no arquivo. Até
    2023 há papéis cotados por lote de mil (fator de cotação 1000): o preço é dividido pelo fator
    para ficar por ação (o volume já vem em reais). Campo vazio vale 1.
    """
    with zipfile.ZipFile(caminho) as pacote:
        nome = next(n for n in pacote.namelist() if n.upper().endswith(".TXT"))
        with pacote.open(nome) as bruto:
            tabela = pd.read_fwf(
                io.TextIOWrapper(bruto, encoding="latin-1"),
                colspecs=list(CAMPOS.values()),
                names=list(CAMPOS),
                dtype=str,
                header=None,
            )
    cotacoes = tabela[
        (tabela["tipo"] == TIPO_DE_REGISTRO) & (tabela["mercado"] == MERCADO_A_VISTA)
    ]
    divisor = CENTAVOS * pd.to_numeric(cotacoes["fator_de_cotacao"]).fillna(1.0)
    return pd.DataFrame(
        {
            "data": pd.to_datetime(cotacoes["data"], format="%Y%m%d"),
            "ticker": cotacoes["ticker"].str.strip(),
            "isin": cotacoes["isin"].str.strip(),
            "especificacao": cotacoes["especificacao"].str.strip(),
            "abertura": _preco(cotacoes["abertura"], divisor),
            "fechamento": _preco(cotacoes["fechamento"], divisor),
            "volume": cotacoes["volume"].astype(float) / CENTAVOS,
            "distribuicao": cotacoes["distribuicao"].str.strip(),
        }
    ).reset_index(drop=True)


def _preco(campo: pd.Series, divisor: pd.Series) -> pd.Series:
    """Preço por ação; zero no arquivo é dia sem preço (viraria retorno infinito no dia seguinte)."""
    preco = campo.astype(float) / divisor
    return preco.where(preco > 0)


def paineis(longo: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fechamento, abertura e volume em tabelas largas (data × ticker), NaN sem pregão."""

    def painel(coluna: str) -> pd.DataFrame:
        return longo.pivot_table(
            index="data", columns="ticker", values=coluna, aggfunc="last"
        ).sort_index()

    fechamento = painel("fechamento")
    return (
        fechamento,
        painel("abertura").reindex_like(fechamento),
        painel("volume").reindex_like(fechamento),
    )


def trocas_de_distribuicao(longo: pd.DataFrame) -> pd.DataFrame:
    """Tabela larga (data × ticker): verdadeiro no pregão em que o número de distribuição mudou.

    O primeiro pregão de cada papel não conta como troca; dia sem pregão é falso.
    """
    ordenado = longo.sort_values(["ticker", "data"], kind="stable")
    anterior = ordenado.groupby("ticker")["distribuicao"].shift()
    troca = anterior.notna() & (ordenado["distribuicao"] != anterior)
    largo = ordenado.assign(troca=troca).pivot_table(
        index="data", columns="ticker", values="troca", aggfunc="max"
    )
    return largo.sort_index().eq(True)


def emissores_com_antigos(
    emissores: pd.DataFrame, antigos: pd.DataFrame
) -> pd.DataFrame:
    """Os emissores do FCA mais os antigos com CNPJ; no mesmo emissor vale o FCA."""
    com_cnpj = antigos.loc[antigos["cnpj"].notna(), ["emissor", "cnpj"]]
    juntos = pd.concat([emissores[["emissor", "cnpj"]], com_cnpj], ignore_index=True)
    return juntos.drop_duplicates("emissor", keep="first").reset_index(drop=True)


def ler_emissores(pasta_do_acervo: Path) -> pd.DataFrame:
    """`fca/emissores.parquet` do acervo completado por `emissores_antigos.csv`."""
    return emissores_com_antigos(
        pd.read_parquet(pasta_do_acervo / "fca" / "emissores.parquet"),
        pd.read_csv(ARQUIVO_DOS_EMISSORES_ANTIGOS, dtype=str),
    )


def classe_da_especificacao(especificacao: str) -> str:
    """ON, PN ou UNT pela especificação do papel ("PN N2", "UNT N2"); o resto é "outro"."""
    for classe in CLASSES_DE_ACAO:
        if especificacao.upper().startswith(classe):
            return classe
    return "outro"


def cadastro_dos_tickers(
    longo: pd.DataFrame,
    emissores: pd.DataFrame,
    tickers_do_fca: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Cadastro por ticker: CNPJ pelo emissor do ISIN, classe, primeiro e último pregão.

    O último pregão fica vazio para quem ainda negociava no último dia dos dados. O primeiro é
    o do COTAHIST ou, se o FCA souber de uma data anterior, a do FCA.
    """
    ultimo_dia = longo["data"].max()
    por_ticker = longo.sort_values("data", kind="stable").groupby("ticker")
    tabela = por_ticker.agg(
        isin=("isin", "last"),
        especificacao=("especificacao", "last"),
        inicio_negociacao=("data", "min"),
        ultimo=("data", "max"),
    )
    cnpj_do_emissor = emissores.drop_duplicates("emissor").set_index("emissor")["cnpj"]
    tabela["cnpj"] = (
        tabela["isin"].str[POSICOES_DO_EMISSOR_NO_ISIN].map(cnpj_do_emissor)
    )
    tabela["classe"] = tabela["especificacao"].map(classe_da_especificacao)
    tabela["fim_negociacao"] = tabela["ultimo"].where(tabela["ultimo"] < ultimo_dia)
    if tickers_do_fca is not None:
        do_fca = pd.to_datetime(
            tickers_do_fca.drop_duplicates("codigo").set_index("codigo")[
                "inicio_negociacao"
            ]
        ).reindex(tabela.index)
        tabela["inicio_negociacao"] = tabela["inicio_negociacao"].where(
            do_fca.isna() | (do_fca > tabela["inicio_negociacao"]), do_fca
        )
    return tabela[list(COLUNAS_DO_CADASTRO)]


def fundamentos_do_acervo(demonstracoes: pd.DataFrame) -> pd.DataFrame:
    """Da tabela `demonstracoes/<ano>.parquet` para o formato da ficha.

    Só o consolidado e as contas usadas; as versões ficam em ordem para a última vencer.
    Empresa que só publica o individual fica sem fundamentos (limitação declarada).
    """
    linhas = demonstracoes[
        (demonstracoes["grupo"] == GRUPO_CONSOLIDADO)
        & demonstracoes["conta"].isin(CONTAS_USADAS)
    ]
    linhas = linhas.sort_values(["cnpj", "conta", "fim", "versao"], kind="stable")
    return linhas[list(COLUNAS_DOS_FUNDAMENTOS)].reset_index(drop=True)


# --- ações em circulação (Formulário de Referência, DFP e ITR da CVM) ---------------------------------


def _ler_do_zip(pacote: zipfile.ZipFile, termina_com: str) -> pd.DataFrame | None:
    nomes = [n for n in pacote.namelist() if n.endswith(termina_com)]
    if not nomes:
        return None
    return pd.read_csv(
        pacote.open(nomes[0]), sep=";", encoding=CODIFICACAO_DA_CVM, dtype=str
    )


def _nome_do_indice(pacote: zipfile.ZipFile) -> str:
    """O índice do arquivo anual é `<doc>_cia_aberta_<ano>.csv` (os outros têm mais partes)."""
    return next(
        n for n in pacote.namelist() if n.endswith(".csv") and n.count("_") == 3
    )


def _indice(pacote: zipfile.ZipFile) -> pd.DataFrame:
    """Uma linha por versão entregue, com o dia em que a CVM a recebeu."""
    indice = pd.read_csv(
        pacote.open(_nome_do_indice(pacote)),
        sep=";",
        encoding=CODIFICACAO_DA_CVM,
        dtype=str,
    )
    return indice.assign(recebido_em=pd.to_datetime(indice["DT_RECEB"]))


def _sufixo_do_ano(pacote: zipfile.ZipFile) -> str:
    return _nome_do_indice(pacote).rsplit("_", 1)[1]  # "2015.csv"


def _tabela_das_acoes(
    cnpj: pd.Series, quantidade: pd.Series, recebido_em: pd.Series
) -> pd.DataFrame:
    tabela = pd.DataFrame(
        {
            "cnpj": cnpj.astype(str).str.strip().to_numpy(),
            "quantidade": pd.to_numeric(quantidade, errors="coerce").to_numpy(),
            "disponivel_em": pd.to_datetime(recebido_em).to_numpy(),
        }
    ).dropna()
    return tabela[tabela["quantidade"] > 0].reset_index(drop=True)


def _sem_acoes() -> pd.DataFrame:
    return _tabela_das_acoes(
        pd.Series(dtype=str), pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")
    )


def acoes_do_fre(conteudo: bytes) -> pd.DataFrame:
    """Do ZIP anual do Formulário de Referência: o capital integralizado de cada documento.

    O arquivo aberto da CVM traz só a última versão de cada formulário; o número vale do dia em
    que a CVM recebeu essa versão (o índice liga `ID_Documento` a `DT_RECEB`). Duas aprovações no
    mesmo documento: vale a mais recente.
    """
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        capital = _ler_do_zip(pacote, "_capital_social_" + _sufixo_do_ano(pacote))
        indice = _indice(pacote)
    if capital is None:
        return _sem_acoes()
    capital = capital[capital["Tipo_Capital"] == CAPITAL_INTEGRALIZADO]
    capital = capital.sort_values("Data_Autorizacao_Aprovacao", kind="stable")
    capital = capital.drop_duplicates("ID_Documento", keep="last")
    recebido = indice.drop_duplicates("ID_DOC").set_index("ID_DOC")["recebido_em"]
    return _tabela_das_acoes(
        capital["CNPJ_Companhia"],
        capital["Quantidade_Total_Acoes"],
        capital["ID_Documento"].map(recebido),
    )


def acoes_da_dfp_ou_itr(conteudo: bytes) -> pd.DataFrame:
    """Do ZIP anual da DFP ou do ITR (desde 2020): a composição do capital de cada versão."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        capital = _ler_do_zip(pacote, "_composicao_capital_" + _sufixo_do_ano(pacote))
        indice = _indice(pacote)
    if capital is None:
        return _sem_acoes()
    chave = ["CNPJ_CIA", "DT_REFER", "VERSAO"]
    juntos = capital.merge(
        indice.drop_duplicates(chave)[[*chave, "recebido_em"]], on=chave, how="left"
    )
    return _tabela_das_acoes(
        juntos["CNPJ_CIA"], juntos["QT_ACAO_TOTAL_CAP_INTEGR"], juntos["recebido_em"]
    )


def montar_acoes(fre: Iterable[bytes], dfp_e_itr: Iterable[bytes]) -> pd.DataFrame:
    """A tabela `acoes` da ficha: uma linha por número público, só até o fim do desenvolvimento.

    No mesmo CNPJ e dia, a DFP ou o ITR vence o FRE (é a composição do balanço daquela data).
    """
    partes = [*map(acoes_do_fre, fre), *map(acoes_da_dfp_ou_itr, dfp_e_itr)]
    tabela = pd.concat([_sem_acoes(), *partes], ignore_index=True)
    tabela = tabela[tabela["disponivel_em"] <= FIM_DO_DESENVOLVIMENTO]
    tabela = tabela.drop_duplicates(["cnpj", "disponivel_em"], keep="last")
    tabela = tabela.sort_values(["cnpj", "disponivel_em"], kind="stable")
    return tabela[list(COLUNAS_DAS_ACOES)].reset_index(drop=True)


def _potencia_de_dez(razao: float) -> int:
    """O expoente k quando `razao` está a FOLGA_DA_ESCALA de 10**k (k diferente de 0); senão 0."""
    if not np.isfinite(razao) or razao <= 0:
        return 0
    expoente = np.log10(razao)
    potencia = round(expoente)
    return potencia if abs(expoente - potencia) < np.log10(1 + FOLGA_DA_ESCALA) else 0


def _no_dia(painel: pd.DataFrame, cnpj: str, dia: pd.Timestamp) -> float:
    """O último valor de `painel` (data × CNPJ) até `dia`; NaN se não houver."""
    if cnpj not in painel.columns:
        return np.nan
    posicao = pd.DatetimeIndex(painel.index).searchsorted(dia, side="right") - 1
    return float(painel[cnpj].iloc[posicao]) if posicao >= 0 else np.nan


def _no_nivel_plausivel(quantidade: float, preco: float, negociado: float) -> float:
    """A quantidade em potências de mil até o valor de mercado caber nos dois limites."""
    for _ in range(VEZES_DO_NIVEL):
        valor = quantidade * preco
        if valor > VALOR_DE_MERCADO_MAXIMO:
            quantidade /= MIL
        elif negociado > GIRO_MAXIMO * valor:
            quantidade *= MIL
    return quantidade


def volume_por_empresa(volume: pd.DataFrame, cadastro: pd.DataFrame) -> pd.DataFrame:
    """Volume financeiro médio dos `PREGOES_DA_LIQUIDEZ` pregões até o dia, somando os tickers do CNPJ."""
    cnpj = cadastro["cnpj"].reindex(volume.columns)
    soma = volume.fillna(0.0).T.groupby(cnpj.to_numpy()).sum().T
    return soma.rolling(PREGOES_DA_LIQUIDEZ, min_periods=1).sum() / PREGOES_DA_LIQUIDEZ


def corrigir_quantidade(
    acoes: pd.DataFrame, preco: pd.DataFrame, negociado: pd.DataFrame
) -> pd.DataFrame:
    """Desfaz o erro de unidade da quantidade de ações, olhando só o passado.

    `preco` é o preço bruto de uma ação e `negociado` o volume médio (`volume_por_empresa`),
    os dois por CNPJ. Para cada documento, na ordem em que a CVM os recebeu:

    1. **Nível:** se o valor de mercado no dia passa de `VALOR_DE_MERCADO_MAXIMO`, ou se o volume
       médio passa de `GIRO_MAXIMO` dele, a quantidade veio em milésimos ou em milhares e anda em
       potências de mil até caber. Um documento corrigido aqui vira a referência dos seguintes.
    2. **Escala:** senão, comparado ao anterior da mesma empresa (já corrigido), se a quantidade
       mudou por uma potência de 10 e o valor de mercado mudaria quase o mesmo tanto, é a
       unidade, e o número volta para a escala do anterior. Num desdobramento o preço cai junto,
       o valor de mercado fica parecido e o número fica como veio. Sem preço não há como
       confirmar um desdobramento, e vale a correção.
    """
    tabela = acoes.sort_values(["cnpj", "disponivel_em"], kind="stable").reset_index(
        drop=True
    )
    quantidade = tabela["quantidade"].to_numpy(float).copy()
    for cnpj, posicoes in tabela.groupby("cnpj", sort=False).indices.items():
        anterior, preco_anterior = np.nan, np.nan
        for i in posicoes:
            dia = tabela.at[i, "disponivel_em"]
            no_dia = _no_dia(preco, str(cnpj), dia)
            plausivel = _no_nivel_plausivel(
                quantidade[i], no_dia, _no_dia(negociado, str(cnpj), dia)
            )
            potencia = _potencia_de_dez(quantidade[i] / anterior)
            if plausivel != quantidade[i]:
                quantidade[i] = plausivel
            elif potencia:
                salto = np.log10(quantidade[i] * no_dia / (anterior * preco_anterior))
                desdobramento = abs(salto) < abs(salto - potencia)
                if not desdobramento:
                    quantidade[i] /= 10.0**potencia
            anterior = quantidade[i]
            preco_anterior = no_dia if np.isfinite(no_dia) else preco_anterior
    return tabela.assign(quantidade=quantidade)[list(COLUNAS_DAS_ACOES)]


def gravar_acoes(
    pasta_do_fre: Path = PASTA_DO_FRE,
    pasta_da_cvm: Path = PASTA_DA_CVM,
    destino: Path = PASTA_DA_FICHA / ARQUIVO_DE_ACOES,
) -> Path:
    """Monta e grava `acoes_em_circulacao.parquet` com os ZIPs que estão nas duas pastas."""
    fre = [c.read_bytes() for c in sorted(pasta_do_fre.rglob("*.zip"))]
    dfp_e_itr = [
        c.read_bytes() for c in sorted(pasta_da_cvm.glob("*_cia_aberta_*.zip"))
    ]
    montar_acoes(fre, dfp_e_itr).to_parquet(destino, index=False)
    return destino


# --- recuperação judicial e preço por ação -------------------------------------------------------------


def episodios_de_recuperacao_judicial(
    insolvencia: pd.DataFrame, ate: pd.Timestamp = FIM_DO_DESENVOLVIMENTO
) -> pd.DataFrame:
    """Uma linha por episódio: do primeiro documento até 12 meses depois do último.

    Documentos com mais de 12 meses de distância abrem episódios separados, então a empresa não
    fica "em recuperação" no intervalo por causa de um documento que só viria depois. Só o que a
    CVM recebeu até `ate`.
    """
    insolvencia = insolvencia.reset_index(drop=True)  # anos juntados repetem o índice
    conhecido = pd.to_datetime(insolvencia["conhecido_em"])
    linhas = (
        insolvencia.assign(conhecido_em=conhecido)
        .loc[
            insolvencia["rotulo"].isin(ROTULOS_DE_RECUPERACAO_JUDICIAL)
            & (conhecido <= ate),
            ["cnpj", "conhecido_em"],
        ]
        .dropna()
        .drop_duplicates()
        .sort_values(["cnpj", "conhecido_em"], kind="stable")
    )
    if linhas.empty:
        return pd.DataFrame(columns=list(COLUNAS_DA_RECUPERACAO))
    vence = linhas["conhecido_em"] + pd.DateOffset(months=MESES_SEM_DOCUMENTO)
    anterior = vence.groupby(linhas["cnpj"]).shift()
    episodio = (anterior.isna() | (linhas["conhecido_em"] >= anterior)).cumsum()
    tabela = (
        linhas.assign(fim=vence, episodio=episodio)
        .groupby(["cnpj", "episodio"], sort=True)
        .agg(inicio=("conhecido_em", "min"), fim=("fim", "max"))
    )
    return tabela.reset_index()[list(COLUNAS_DA_RECUPERACAO)]


def ler_insolvencia(
    pasta_do_acervo: Path, ultimo_ano: int = ULTIMO_ANO
) -> pd.DataFrame:
    """Todos os anos de `insolvencia/` até `ultimo_ano` (episódio antigo ainda em curso conta).

    Só `<ano>.parquet`: `<ano>.v1.parquet` é a versão anterior da mesma base.
    """
    caminhos = sorted((pasta_do_acervo / "insolvencia").glob("*.parquet"))
    anos = [c for c in caminhos if c.stem.isdigit() and int(c.stem) <= ultimo_ano]
    tabelas = [pd.read_parquet(c) for c in anos]
    if not tabelas:
        return pd.DataFrame(columns=["cnpj", "rotulo", "conhecido_em"])
    return pd.concat(tabelas, ignore_index=True)


def preco_por_acao(
    longo: pd.DataFrame, cadastro: pd.DataFrame, datas: pd.DatetimeIndex
) -> pd.DataFrame:
    """Preço bruto de uma ação de cada empresa (data × CNPJ), para o valor de mercado.

    O fechamento da ON ou da PN com mais volume no dia; sem negócio, o último conhecido (sem olhar
    o futuro). A unit fica de fora porque junta várias ações.
    """
    classe = longo["ticker"].map(cadastro["classe"])
    cnpj = longo["ticker"].map(cadastro["cnpj"])
    linhas = longo.assign(cnpj=cnpj)[
        classe.isin(CLASSES_DO_PRECO_POR_ACAO)
        & cnpj.notna()
        & longo["fechamento"].notna()
    ]
    linhas = linhas.sort_values(["data", "cnpj", "volume"], kind="stable")
    linhas = linhas.drop_duplicates(["data", "cnpj"], keep="last")
    largo = linhas.pivot(index="data", columns="cnpj", values="fechamento").sort_index()
    return largo.reindex(largo.index.union(datas)).ffill().reindex(datas)


def carregar_tabelas(
    pasta: Path = PASTA_DA_FICHA,
    pasta_do_acervo: Path = PASTA_DO_ACERVO,
    *,
    com_acoes: bool = True,
) -> Dados:
    """Monta `Dados` da ficha só com o desenvolvimento; falha listando o que falta.

    Com `com_acoes=False`, `acoes` vem vazia (com as colunas certas).
    """
    faltas = conferir_base(pasta, com_acoes=com_acoes)
    if faltas:
        raise FileNotFoundError(f"faltam na base da ficha F-B3: {', '.join(faltas)}")
    anos = range(PRIMEIRO_ANO, ULTIMO_ANO + 1)
    longo = pd.concat(
        [ler_cotahist_anual(pasta / nome_do_cotahist(ano)) for ano in anos],
        ignore_index=True,
    )
    bruto, abertura_bruta, volume = paineis(longo)
    ajustado = pd.read_parquet(pasta / ARQUIVO_DE_PRECOS_AJUSTADOS).reindex_like(bruto)
    fator = ajustado / bruto
    fechamento = recortar_desenvolvimento(ajustado)
    datas = pd.DatetimeIndex(fechamento.index)
    emissores = ler_emissores(pasta_do_acervo)
    tickers_do_fca = pd.read_parquet(pasta_do_acervo / "fca" / "tickers.parquet")
    fundamentos = pd.concat(
        [
            fundamentos_do_acervo(
                pd.read_parquet(pasta_do_acervo / "demonstracoes" / f"{ano}.parquet")
            )
            for ano in anos
            if (pasta_do_acervo / "demonstracoes" / f"{ano}.parquet").exists()
        ],
        ignore_index=True,
    )
    bova11 = dados_p0_3.fechamento_do_mt5(
        dados_p0_3.PASTA_DO_MT5 / dados_p0_3.ARQUIVOS_DO_MT5["BOVA11"],
        so_com_negocio=True,
    )
    ibovespa = bova11.reindex(datas).ffill().pct_change(fill_method=None).fillna(0.0)
    cdi = dados_p0_3.carregar_cdi(datas.min(), datas.max()).reindex(datas).ffill()
    cadastro = cadastro_dos_tickers(longo, emissores, tickers_do_fca)
    preco = preco_por_acao(longo, cadastro, datas)
    acoes = (
        corrigir_quantidade(
            pd.read_parquet(pasta / ARQUIVO_DE_ACOES)[list(COLUNAS_DAS_ACOES)],
            preco,
            volume_por_empresa(volume.reindex(datas), cadastro),
        )
        if com_acoes
        else pd.DataFrame(columns=list(COLUNAS_DAS_ACOES))
    )
    dados = Dados(
        fechamento=fechamento,
        abertura=(abertura_bruta * fator).reindex(datas),
        volume=volume.reindex(datas),
        cadastro=cadastro,
        fundamentos=fundamentos,
        acoes=acoes,
        cdi=cdi,
        ibovespa=ibovespa,
        recuperacao_judicial=episodios_de_recuperacao_judicial(
            ler_insolvencia(pasta_do_acervo)
        ),
        preco_por_acao=preco,
    )
    for tabela in (
        dados.fechamento,
        dados.abertura,
        dados.volume,
        dados.cdi,
        dados.preco_por_acao,
    ):
        exigir_sem_holdout(tabela)
    return dados
