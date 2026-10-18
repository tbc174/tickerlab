"""Release × documento oficial: o que a empresa disse no press-release contra o que entregou à CVM.

Vitrine, ideia 2 (ADR 0090; plano de 17/10/2026). Cada linha lida do release e **conferida por código**
(`base/leitor_release.py`) é comparada com o mesmo número no ITR ou na DFP daquele período, na versão
que valia no dia do release (`demonstracoes_como_era`). O modelo só copiou o número e o trecho; quem
compara é este módulo, em Python puro, e a tabela guarda **só números** (nenhum texto do modelo).

Classes (`classe`):
- `igual`: bate ao real;
- `igual (arredondamento)`: a diferença cabe em 1 unidade do que o release mostra (R$ 1.234,5
  milhões cobre qualquer valor de 1.234.400.000 a 1.234.600.000): o release soma parcelas já
  arredondadas, então o total pode escapar de meia unidade;
- `diferente`: não bate; vão a diferença em R$ e em % do valor oficial (sem juízo: pode ser ajuste,
  pode ser outro critério da empresa);
- `release não mostra`: o documento oficial tem a linha e o release não a traz;
- `sem ITR`: não há valor oficial do período para comparar (sem ITR/DFP, ou o plano de contas da
  empresa, como o de banco, não tem a conta).

`disponivel_em` é a data mais nova entre o release e o documento oficial: a tabela só "existe" quando
as duas pontas existem (regra de não olhar o futuro). O corte do holdout fica no treino, não aqui.
"""

import unicodedata
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from base.parquet import gravar_se_mudou
from src.versao_do_codigo import versao_do_codigo

TABELA = "release_x_oficial"
IGUAL = "igual"
IGUAL_ARREDONDADO = "igual (arredondamento)"
DIFERENTE = "diferente"
RELEASE_NAO_MOSTRA = "release não mostra"
SEM_ITR = "sem ITR"
CLASSES = (IGUAL, IGUAL_ARREDONDADO, DIFERENTE, RELEASE_NAO_MOSTRA, SEM_ITR)

REAIS_POR_UNIDADE = {
    "unidade": 1,
    "mil": 1_000,
    "milhoes": 1_000_000,
    "bilhoes": 1_000_000_000,
}
CONSOLIDADO, INDIVIDUAL = "con", "ind"
# linha do release -> (contas aceitas, começos aceitos da descrição, em minúsculas e sem acento)
CONTAS = {
    "receita_liquida": (
        ("3.01",),
        ("receita de venda", "receitas de venda", "receitas da intermediacao"),
    ),
    "lucro_liquido_controladores": (
        ("3.11.01", "3.13.01", "3.09.01"),
        ("atribuido a socios da empresa controladora", "atribuido a controladores"),
    ),
    "resultado_operacional": (("3.05",), ("resultado antes do resultado financeiro",)),
}  # fmt: skip
LINHAS = tuple(CONTAS)
TRIMESTRE_EM_DIAS = (80, 100)
ANO_EM_DIAS = (350, 380)
NOVE_MESES_EM_DIAS = (260, 280)
DIAS_MINIMOS_DO_ACUMULADO = 150

COLUNAS = (
    "cnpj", "protocolo", "versao", "periodo", "referencia", "data_entrega", "link",
    "linha", "periodo_lido", "leitura", "valor_release_reais", "unidade_release",
    "grupo", "documento", "documento_versao", "documento_entregue_em", "valor_oficial_reais",
    "tolerancia_reais", "diferenca_reais", "diferenca_pct", "classe",
    "disponivel_em", "publico_em", "modelo", "versao_do_guia", "sha256_do_documento",
    "montado_em", "versao_do_codigo",
)  # fmt: skip
COMPARADAS = tuple(
    c for c in COLUNAS if c not in ("publico_em", "montado_em", "versao_do_codigo")
)
CHAVE = ["protocolo", "linha", "periodo_lido", "leitura"]
DA_LEITURA = (
    "cnpj", "protocolo", "versao", "periodo", "referencia", "data_entrega", "link",
    "modelo", "versao_do_guia", "sha256_do_documento",
)  # fmt: skip


def _sem_acento(texto: object) -> str:
    base = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in base if not unicodedata.combining(c)).lower().strip()


def _linha_da_conta(conta: object, descricao: object) -> str | None:
    descrito = _sem_acento(descricao)
    for linha, (contas, comecos) in CONTAS.items():
        if conta in contas and descrito.startswith(comecos):
            return linha
    return None


def _serve(escopo: str, inicio: pd.Timestamp, fim: pd.Timestamp) -> bool:
    """O período do documento é o do que o release disse? Trimestre = 3 meses; acumulado = do 1º de
    janeiro até o fim do trimestre; ano = o exercício inteiro."""
    dias = (fim - inicio).days
    if escopo == "trimestre":
        return TRIMESTRE_EM_DIAS[0] <= dias <= TRIMESTRE_EM_DIAS[1]
    if escopo == "ano":
        return ANO_EM_DIAS[0] <= dias <= ANO_EM_DIAS[1]
    comeca_no_ano = inicio.month == 1 and inicio.day == 1
    return comeca_no_ano and dias >= DIAS_MINIMOS_DO_ACUMULADO


def _casas_do_release(valor: float) -> int:
    """Quantas casas decimais o release mostrou (1.234,5 → 1; 1.235 → 0). Zeros no fim não contam."""
    expoente = Decimal(repr(float(valor))).normalize().as_tuple().exponent
    return min(int(expoente), 0) if isinstance(expoente, int) else 0


def _oficiais_por_linha(
    como_era: pd.DataFrame,
) -> dict[tuple[str, str, pd.Timestamp], pd.DataFrame]:
    """A DRE de cada documento, só as três linhas, só o período do próprio documento."""
    if como_era.empty:
        return {}
    dre = como_era[
        (como_era["demonstracao"] == "DRE") & (como_era["ordem"] == "ultimo")
    ]
    nomeadas = dre.assign(
        linha=[
            _linha_da_conta(c, d)
            for c, d in zip(dre["conta"], dre["descricao"], strict=True)
        ]
    )
    nomeadas = nomeadas[nomeadas["linha"].notna() & nomeadas["valor"].notna()]
    nomeadas = pd.concat([nomeadas, _quartos_trimestres(nomeadas)], ignore_index=True)
    return {
        (str(cnpj), str(linha), pd.Timestamp(fim)): grupo
        for (cnpj, linha, fim), grupo in nomeadas.groupby(["cnpj", "linha", "fim"])
    }


def _quartos_trimestres(nomeadas: pd.DataFrame) -> pd.DataFrame:
    """O 4º trimestre não vem pronto: é o ano da DFP menos os nove meses do ITR do 3º trimestre
    (mesma empresa, mesma linha, mesmo grupo). Usa o ITR mais novo entregue até o dia da DFP; sem ele,
    não há linha. Vale desde o dia em que as duas pontas existiam e até a primeira das duas trocas."""
    dias = (nomeadas["fim"] - nomeadas["inicio"]).dt.days
    anos = nomeadas[dias.between(*ANO_EM_DIAS)]
    nove = nomeadas[
        dias.between(*NOVE_MESES_EM_DIAS) & (nomeadas["inicio"].dt.month == 1)
    ]
    if anos.empty or nove.empty:
        return nomeadas.iloc[0:0]
    chave = ["cnpj", "linha", "grupo", "inicio"]
    par = anos.merge(nove, on=chave, suffixes=("", "_9m"))
    par = par[par["divulgado_em_9m"] <= par["divulgado_em"]]
    par = (
        par.sort_values(["divulgado_em_9m", "versao_9m"])
        .groupby(
            ["cnpj", "linha", "grupo", "fim", "versao", "divulgado_em"], as_index=False
        )
        .last()
    )
    quarto = par.assign(
        valor=par["valor"] - par["valor_9m"],
        inicio=par["fim_9m"] + pd.Timedelta(days=1),
        documento="DFP-ITR",
        ate=par[["ate", "ate_9m"]].min(axis=1),
    )
    return pd.DataFrame(quarto[list(nomeadas.columns)])


def _escolher(
    candidatas: pd.DataFrame | None, escopo: str, entrega: pd.Timestamp
) -> pd.Series | None:
    """O valor oficial do período: consolidado (senão o individual), na versão que valia no dia do
    release; se o documento só foi entregue depois, a primeira versão entregue."""
    if candidatas is None:
        return None
    servem = [
        _serve(escopo, i, f)
        for i, f in zip(candidatas["inicio"], candidatas["fim"], strict=True)
    ]
    do_periodo = pd.DataFrame(candidatas[servem])
    if do_periodo.empty:
        return None
    grupo = CONSOLIDADO if (do_periodo["grupo"] == CONSOLIDADO).any() else INDIVIDUAL
    do_grupo = pd.DataFrame(do_periodo[do_periodo["grupo"] == grupo])
    valiam = do_grupo[
        (do_grupo["divulgado_em"] <= entrega)
        & (do_grupo["ate"].isna() | (do_grupo["ate"] > entrega))
    ]
    if not valiam.empty:
        return valiam.sort_values(["divulgado_em", "versao"]).iloc[-1]
    return do_grupo.sort_values(["divulgado_em", "versao"]).iloc[0]


def _classe(diferenca: float, tolerancia: float) -> str:
    if abs(diferenca) < 1e-6:
        return IGUAL
    return IGUAL_ARREDONDADO if abs(diferenca) <= tolerancia * (1 + 1e-9) else DIFERENTE


def _linha_da_tabela(
    base: dict, oficial: pd.Series | None, leitura: pd.Series | None
) -> dict:
    """Uma linha da comparação; `leitura` vazia = o release não mostra a linha."""
    entrega = pd.Timestamp(base["data_entrega"])
    saida = base | {
        "valor_release_reais": None, "unidade_release": None, "grupo": None, "documento": None,
        "documento_versao": None, "documento_entregue_em": pd.NaT, "valor_oficial_reais": None,
        "tolerancia_reais": None, "diferenca_reais": None, "diferenca_pct": None,
        "disponivel_em": entrega,
    }  # fmt: skip
    if oficial is not None:
        saida |= {
            "grupo": oficial["grupo"], "documento": oficial["documento"],
            "documento_versao": int(oficial["versao"]),
            "documento_entregue_em": pd.Timestamp(oficial["divulgado_em"]),
            "valor_oficial_reais": float(oficial["valor"]),
            "disponivel_em": max(entrega, pd.Timestamp(oficial["divulgado_em"])),
        }  # fmt: skip
    if leitura is None:
        saida["classe"] = RELEASE_NAO_MOSTRA if oficial is not None else SEM_ITR
        return saida
    reais = REAIS_POR_UNIDADE[str(leitura["unidade"])]
    valor = float(leitura["valor"]) * reais
    saida |= {"valor_release_reais": valor, "unidade_release": leitura["unidade"]}
    if oficial is None:
        saida["classe"] = SEM_ITR
        return saida
    tolerancia = 10 ** _casas_do_release(float(leitura["valor"])) * reais
    diferenca = valor - float(oficial["valor"])
    saida |= {
        "tolerancia_reais": tolerancia,
        "diferenca_reais": diferenca,
        "diferenca_pct": diferenca / abs(float(oficial["valor"])) * 100 if oficial["valor"] else None,
        "classe": _classe(diferenca, tolerancia),
    }  # fmt: skip
    return saida


def comparar(conferidas: pd.DataFrame, como_era: pd.DataFrame) -> pd.DataFrame:
    """Compara cada linha lida e conferida do release com o documento oficial do período.

    `conferidas`: uma linha por valor aceito pelo código, com `DA_LEITURA` (a identidade do release
    e a linhagem da leitura) mais `linha`, `valor`, `unidade` e `periodo_lido` (trimestre,
    acumulado_no_ano ou ano). `como_era`: `demonstracoes_como_era` (com `divulgado_em` e `ate`).
    Linha da lista fechada que o release não trouxe e o documento oficial tem vira "release não mostra".
    """
    if conferidas.empty:
        return pd.DataFrame(columns=list(COMPARADAS))
    oficiais = _oficiais_por_linha(como_era)
    linhas: list[dict] = []
    for _, release in conferidas.groupby("protocolo", sort=False):
        identidade = {c: release.iloc[0][c] for c in DA_LEITURA}
        referencia = pd.Timestamp(identidade["referencia"])
        entrega = pd.Timestamp(identidade["data_entrega"])
        contador: dict[tuple[str, str], int] = {}
        for leitura in release.itertuples(index=False):
            serie = pd.Series(leitura._asdict())
            escopo = str(serie["periodo_lido"])
            oficial = _escolher(
                oficiais.get((str(identidade["cnpj"]), str(serie["linha"]), referencia)),
                escopo, entrega,
            )  # fmt: skip
            ordem = contador.get((serie["linha"], escopo), 0)
            contador[(serie["linha"], escopo)] = ordem + 1
            base = identidade | {
                "linha": serie["linha"],
                "periodo_lido": escopo,
                "leitura": ordem,
            }
            linhas.append(_linha_da_tabela(base, oficial, serie))
        lidas = set(release["linha"])
        for linha in LINHAS:
            if linha in lidas:
                continue
            oficial = _escolher(
                oficiais.get((str(identidade["cnpj"]), linha, referencia)),
                "trimestre",
                entrega,
            )
            if oficial is not None:
                base = identidade | {
                    "linha": linha,
                    "periodo_lido": "trimestre",
                    "leitura": 0,
                }
                linhas.append(_linha_da_tabela(base, oficial, None))
    tabela = pd.DataFrame(linhas)
    tabela["documento_versao"] = tabela["documento_versao"].astype("Int64")
    return tabela.reindex(columns=list(COMPARADAS))


def montar(
    conferidas: pd.DataFrame, como_era: pd.DataFrame, agora: pd.Timestamp
) -> pd.DataFrame:
    """A tabela pronta: a comparação mais `publico_em` (= `disponivel_em`) e a linhagem da montagem."""
    comparada = comparar(conferidas, como_era)
    if comparada.empty:
        return pd.DataFrame(columns=list(COLUNAS))
    comparada["publico_em"] = comparada["disponivel_em"]
    comparada["montado_em"] = pd.Timestamp(agora).isoformat()
    comparada["versao_do_codigo"] = versao_do_codigo()
    return (
        comparada.sort_values(CHAVE)
        .reset_index(drop=True)
        .reindex(columns=list(COLUNAS))
    )


def gravar(
    conferidas: pd.DataFrame,
    como_era: pd.DataFrame,
    pasta: Path,
    agora: datetime | pd.Timestamp,
) -> int:
    """`<pasta>/release_x_oficial/release_x_oficial.parquet` com manifesto (um original por PDF lido,
    com o SHA-256 dele); devolve as linhas gravadas."""
    tabela = montar(conferidas, como_era, pd.Timestamp(agora))
    if tabela.empty:
        return 0
    originais = tabela.drop_duplicates("protocolo")
    origens = [
        {"url": str(link), "sha256": str(sha)}
        for link, sha in zip(
            originais["link"], originais["sha256_do_documento"], strict=True
        )
    ]
    gravar_se_mudou(
        tabela,
        pasta / TABELA / TABELA,
        origens,
        CHAVE,
        carimbos=("montado_em", "versao_do_codigo"),
    )
    return len(tabela)
