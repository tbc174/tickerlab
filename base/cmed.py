"""Preços máximos de medicamentos da CMED por apresentação (Ficha Clara; pesquisa de 04/11/2026): as duas
listas que a coleta guarda (`anvisa-cmed` em `base/arquivo/fontes.py`) numa tabela, `cmed_precos`, com um
Parquet por lista: `consumidor` (PF e PMC) e `governo` (PF e PMVG, o teto das compras públicas).

Lê os arquivos que o arquivista já guardou (não baixa nada); cada um é um **retrato** da lista no dia em
que foi baixado, e o motor de `base/retratos.py` os junta numa tabela que só cresce: uma linha por valor
diferente de cada apresentação (o CNPJ inteiro + o código GGREM), e a que some da lista ganha
`consta=False`. Retrato de layout novo (sem o CNPJ, o GGREM, o registro ou uma coluna de preço) é
pulado, e a tabela fica com a última versão boa (`retratos_com_layout_novo` no resumo).

- **Preço exato:** decimal de 2 casas, como a lista escreve ("2123,68" → 2123.68), nunca arredondado nem
  somado. Vazio fica nulo, nunca zero (o PMC das apresentações de uso restrito a hospitais vem vazio);
  zero é zero. O asterisco que a lista põe ao lado de alguns preços sai do número e fica em
  `precos_com_asterisco`; texto que não é um preço fica nulo, com o texto da fonte em
  `precos_ilegiveis` (o arquivo inteiro continua no acervo, pelo `origem_sha256`).
- **Registro:** o texto da fonte; o do produto (`registro_produto`, os 9 primeiros dígitos) só quando o
  registro tem os 13 dígitos. O marcador da lista ("    -     ", o do EVRYSDI) não vira número.
- **Sem olhar o futuro** (`disponivel_em`): o dia do retrato, também no primeiro. A data em que a
  Anvisa publicou o arquivo (o Last-Modified da coleta) fica em `lista_publicada_em`, para ler.
- **Contagens** são de apresentações diferentes, nunca de linhas de preço.
- **Sem pessoa física:** o nome do laboratório nem chega ao acervo; empresário individual e MEI ficam
  com `trata_como_pessoa` (ADR 0075).

A ponte com os produtos registrados (`ponte`) usa só o CNPJ e o registro do produto, e só os
medicamentos de tipo REGISTRADO de `anvisa_registros`: nunca o nome, a raiz do CNPJ ou o ID cru. Ela não
diz a situação de cada apresentação (o arquivo dos registros não a tem): "vigente na lista de preços"
não quer dizer "ativo na Anvisa".
"""

import io
import re
from collections.abc import Collection, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import licencas
from base import retratos as motor
from base.arquivo.fontes import (
    ARQUIVOS_DA_CMED,
    LISTAS_DA_CMED,
    colunas_de_preco_da_cmed,
)
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.banco.coletas import coletas
from src.versao_do_codigo import versao_do_codigo

FONTE = "anvisa-cmed"
TABELA = "cmed_precos"
SEPARADOR = ";"
CODIFICACAO = "utf-8-sig"  # a coleta grava sem o BOM, e o arquivo da fonte vem com ele
REFERENCIAS = ("PF", "PMC", "PMVG")
TIPO_DO_PRECO = pa.decimal128(18, 2)
CENTAVOS = Decimal("0.01")
# "2123,68" ou "25614,71*": inteiro, até 2 casas e o asterisco da lista; o resto não é um preço
PRECO = re.compile(r"^(\d+)(?:,(\d{1,2}))?(\*)?$")
TAMANHO_DO_REGISTRO = 13
TAMANHO_DO_REGISTRO_DO_PRODUTO = 9
SEPARADOR_DA_LISTA = " / "
SIM, NAO = "SIM", "NAO"  # "Sim" e "Não" depois de `motor.nome_da_coluna`
VAZIO = re.compile(r"^[\s-]*$")  # a lista escreve "-" e "    -     " onde não há valor
LAST_MODIFIED = re.compile(r"Last-Modified=([^;|]*)")
JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum retrato novo desde a última montagem
TIPO_REGISTRADO = "REGISTRADO"


def _nosso_nome(referencia: str, coluna: str) -> str:
    """ "PF 17,5 %  ALC" → "pf_17_5_alc"; "PMC Sem Impostos" → "pmc_sem_impostos"; "PF 0%" → "pf_0"."""
    resto = coluna.removeprefix(referencia).replace("%", "").replace(",", "_")
    return "_".join([referencia.lower(), *resto.lower().split()])


# nossa coluna -> a da fonte (com `motor.nome_da_coluna`), na ordem do arquivo
PRECOS = {
    _nosso_nome(r, c): motor.nome_da_coluna(c)
    for r in REFERENCIAS
    for c in colunas_de_preco_da_cmed(r)
}
TEXTOS = {
    "produto": "PRODUTO",
    "apresentacao": "APRESENTAÇÃO",
    "substancia": "SUBSTÂNCIA",
    "classe_terapeutica": "CLASSE TERAPÊUTICA",
    "tipo_de_produto": "TIPO DE PRODUTO (STATUS DO PRODUTO)",
    "regime_de_preco": "REGIME DE PREÇO",
}
MARCAS = {
    "restricao_hospitalar": "RESTRIÇÃO HOSPITALAR",
    "cap": "CAP",
    "confaz_87": "CONFAZ 87",
    "icms_0": "ICMS 0%",
}
NOTAS = {
    "analise_recursal": "ANÁLISE RECURSAL",
    "lista_pis_cofins": "LISTA DE CONCESSÃO DE CRÉDITO TRIBUTÁRIO (PIS/COFINS)",
    "tarja": "TARJA",
}
EANS = ("EAN 1", "EAN 2", "EAN 3")
CNPJ, GGREM, REGISTRO = "CNPJ", "CODIGOGGREM", "REGISTRO"

IDENTIDADE = ["cnpj", "ggrem", "registro", "registro_produto", "eans", *TEXTOS]
AVISOS_DO_PRECO = ["precos_com_asterisco", "precos_ilegiveis"]
VALORES = [*IDENTIDADE, *PRECOS, *AVISOS_DO_PRECO, *MARCAS, *NOTAS, "consta"]
COLUNAS = [
    "lista",
    "id_na_fonte",
    "cnpj",
    "cnpj_basico",
    *IDENTIDADE[1:],
    *PRECOS,
    *AVISOS_DO_PRECO,
    *MARCAS,
    *NOTAS,
    "lista_publicada_em",
    "consta",
    "trata_como_pessoa",
    "visto_em",
    "disponivel_em",
]
ORDEM = ["id_na_fonte", "visto_em"]


class LayoutNovo(ValueError):
    """O arquivo não tem uma coluna de que a leitura precisa: a fonte mudou o layout."""


def _obrigatorias(lista: str) -> list[str]:
    maximo = LISTAS_DA_CMED[lista]
    return [
        CNPJ,
        GGREM,
        REGISTRO,
        *(v for k, v in PRECOS.items() if k.startswith(("pf_", f"{maximo.lower()}_"))),
    ]


def _ler_csv(caminho: Path) -> pd.DataFrame:
    """Só as colunas que a tabela usa, como texto, com o nome da fonte sem acento."""
    lidas = {
        CNPJ,
        GGREM,
        REGISTRO,
        *PRECOS.values(),
        *map(motor.nome_da_coluna, [*TEXTOS.values(), *MARCAS.values()]),
        *map(motor.nome_da_coluna, [*NOTAS.values(), *EANS]),
    }
    tabela = pd.read_csv(
        io.BytesIO(motor.original(caminho)),
        sep=SEPARADOR,
        encoding=CODIFICACAO,
        dtype=str,
        keep_default_na=False,
        usecols=lambda coluna: motor.nome_da_coluna(coluna) in lidas,
    )  # type: ignore[call-overload]
    tabela = tabela.rename(columns=motor.nome_da_coluna)
    return tabela.apply(lambda serie: serie.str.strip())


def _texto(serie: pd.Series) -> pd.Series:
    """O texto da fonte; vazio e só-traço ("-") ficam nulos (`object`: o nulo é `None`)."""
    return serie.astype(object).where(~serie.str.fullmatch(VAZIO), None)


def _marca(serie: pd.Series) -> pd.Series:
    """ "Sim" → True, "Não" → False; outro texto fica nulo, nunca adivinhado."""
    normal = serie.map(motor.nome_da_coluna)
    return pd.Series(
        np.select([normal.eq(SIM), normal.eq(NAO)], [True, False], None),
        index=serie.index,
        dtype=object,
    )


def _registro_do_produto(registro: pd.Series) -> pd.Series:
    inteiro = registro.str.fullmatch(rf"\d{{{TAMANHO_DO_REGISTRO}}}")
    return (
        registro.str[:TAMANHO_DO_REGISTRO_DO_PRODUTO]
        .astype(object)
        .where(inteiro, None)
    )


def _eans(bruta: pd.DataFrame) -> pd.Series:
    colunas = [
        motor.nome_da_coluna(c) for c in EANS if motor.nome_da_coluna(c) in bruta
    ]
    validos = bruta[colunas].where(
        ~bruta[colunas].apply(lambda s: s.str.fullmatch(VAZIO)), ""
    )
    juntos = validos.agg(
        lambda linha: SEPARADOR_DA_LISTA.join(v for v in linha if v), axis=1
    )
    return _texto(juntos.astype(str)) if len(bruta) else pd.Series(dtype=object)


def _preco(texto: str) -> tuple[Decimal | None, bool, bool]:
    """(o preço, tem asterisco, é ilegível) de uma célula; vazia: (None, False, False)."""
    if not texto:
        return None, False, False
    achado = PRECO.fullmatch(texto)
    if achado is None:
        return None, False, True
    inteiro, casas, asterisco = achado.groups()
    return (
        Decimal(f"{inteiro}.{casas or '0'}").quantize(CENTAVOS),
        bool(asterisco),
        False,
    )


def _avisos(marcadas: dict[str, list[str]], indice: pd.Index) -> pd.Series:
    """Por linha, os textos de `marcadas` (coluna -> texto ou "" por linha) juntos, na ordem das colunas."""
    if not marcadas:
        return pd.Series(None, index=indice, dtype=object)
    por_linha = zip(*marcadas.values(), strict=True)
    juntos = [
        SEPARADOR_DA_LISTA.join(t for t in linha if t) or None for linha in por_linha
    ]
    return pd.Series(juntos, index=indice, dtype=object)


def _precos(bruta: pd.DataFrame) -> pd.DataFrame:
    """As colunas de preço em `Decimal` (a que a lista não tem fica nula) e os dois avisos."""
    precos: dict[str, list[Decimal | None]] = {}
    asteriscos: dict[str, list[str]] = {}
    ilegiveis: dict[str, list[str]] = {}
    for nossa, da_fonte in PRECOS.items():
        if da_fonte not in bruta:
            precos[nossa] = [None] * len(bruta)
            continue
        lidos = [_preco(t) for t in bruta[da_fonte]]
        precos[nossa] = [valor for valor, _, _ in lidos]
        asteriscos[nossa] = [nossa if marcado else "" for _, marcado, _ in lidos]
        ilegiveis[nossa] = [
            f"{nossa}={t}" if ilegivel else ""
            for t, (_, _, ilegivel) in zip(bruta[da_fonte], lidos, strict=True)
        ]
    tabela = pd.DataFrame(
        {c: pd.Series(v, index=bruta.index, dtype=object) for c, v in precos.items()}
    )
    tabela["precos_com_asterisco"] = _avisos(asteriscos, bruta.index)
    tabela["precos_ilegiveis"] = _avisos(ilegiveis, bruta.index)
    return tabela


def _sem_repetir(tabela: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Uma linha por apresentação, a mesma qualquer que seja a ordem do arquivo; e quantas sobraram."""
    texto = tabela.astype(str)
    ordem = texto.sort_values(list(texto.columns), kind="stable").index
    ordenada = tabela.loc[ordem]
    repetida = ordenada["id_na_fonte"].duplicated(keep="first")
    return ordenada[~repetida], int(repetida.sum())


def ler_retrato(caminho: Path, lista: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """As apresentações de CNPJ inteiro de um arquivo da `lista` e a contagem do que ficou de fora.

    Levanta `LayoutNovo` se faltar uma coluna de que a leitura precisa.
    """
    bruta = _ler_csv(caminho)
    faltam = [c for c in _obrigatorias(lista) if c not in bruta]
    if faltam:
        raise LayoutNovo(f"{caminho.name}: sem as colunas {faltam}")
    cnpj = bruta[CNPJ].map(cnpjs.completo)
    cnpj_valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(
        bool
    )
    com_ggrem = bruta[GGREM].ne("")
    linhas = len(bruta)
    bruta = bruta[cnpj_valido & com_ggrem]
    cnpj = cnpj[cnpj_valido & com_ggrem]
    registro = _texto(bruta[REGISTRO])
    pronta = pd.DataFrame(
        {
            "lista": lista,
            "id_na_fonte": cnpj.str.cat(bruta[GGREM], sep=motor.SEPARADOR_DA_CHAVE),
            "cnpj": cnpj.map(cnpjs.formatar),
            "cnpj_basico": cnpj.str[: cnpjs.TAMANHO_DA_RAIZ],
            "ggrem": bruta[GGREM],
            "registro": registro,
            "registro_produto": _registro_do_produto(bruta[REGISTRO]),
            "eans": _eans(bruta),
            **{c: _texto(bruta[motor.nome_da_coluna(f)]) for c, f in TEXTOS.items()},
            **_precos(bruta),
            **{c: _marca(bruta[motor.nome_da_coluna(f)]) for c, f in MARCAS.items()},
            **{c: _texto(bruta[motor.nome_da_coluna(f)]) for c, f in NOTAS.items()},
        },
        index=bruta.index,
    )
    pronta, repetidas = _sem_repetir(pronta)
    maximo = [c for c in PRECOS if c.startswith(LISTAS_DA_CMED[lista].lower() + "_")]
    contagem = {
        "linhas": linhas,
        "cnpj_invalido": int((~cnpj_valido).sum()),
        "sem_ggrem": int((cnpj_valido & ~com_ggrem).sum()),
        "id_repetido": repetidas,
        "registro_fora_do_padrao": int(pronta["registro_produto"].isna().sum()),
        f"sem_{LISTAS_DA_CMED[lista].lower()}": int(
            pronta[maximo].isna().all(axis=1).sum()
        ),
        "precos_com_asterisco": int(pronta["precos_com_asterisco"].notna().sum()),
        "precos_ilegiveis": int(pronta["precos_ilegiveis"].notna().sum()),
    }
    return pronta.reset_index(drop=True), contagem


def publicada_em(conexao: sa.Connection, retrato: motor.Retrato) -> date | None:
    """O dia (UTC) do Last-Modified que a fonte mandou na primeira coleta deste arquivo, ou None."""
    detalhe = conexao.execute(
        sa.select(coletas.c.detalhe)
        .where(
            coletas.c.url == retrato.url,
            coletas.c.sha256 == retrato.sha256,
            coletas.c.situacao == "ok",
        )
        .order_by(coletas.c.baixado_em)
        .limit(1)
    ).scalar()
    achado = LAST_MODIFIED.search(detalhe or "")
    if achado is None:
        return None
    try:
        return parsedate_to_datetime(achado.group(1).strip()).astimezone(UTC).date()
    except (TypeError, ValueError):
        return None


def _disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do retrato: a lista não diz desde quando vale cada preço."""
    return pd.Series(dia, index=novos.index)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados.

    `lista_publicada_em` é a do arquivo de cada linha: na saída da apresentação o motor copia a linha
    anterior, e a data tem de ser a do arquivo em que ela sumiu."""
    tabela, pulados = motor.juntar(lidos, VALORES, _disponivel_no_primeiro)
    if "lista_publicada_em" in tabela:
        publicada = {
            retrato.sha256: lido["lista_publicada_em"].iloc[0] if len(lido) else None
            for retrato, lido in lidos
        }
        tabela["lista_publicada_em"] = tabela["origem_sha256"].map(publicada)
    return tabela, pulados


def ponte(apresentacoes: pd.DataFrame, medicamentos: pd.DataFrame) -> pd.DataFrame:
    """Para cada apresentação (`id_na_fonte`, `cnpj`, `registro_produto`), o produto registrado dela.

    `medicamentos`: as linhas vigentes de `anvisa_registros` do cadastro de medicamentos (`id_na_fonte`,
    `cnpj`, `registro`, `processo`). Só o tipo REGISTRADO entra, e a ligação é o CNPJ inteiro + o
    registro do produto. Uma linha por apresentação, nunca multiplicada; `correspondencia` diz o que
    houve: "unica", "multipla" (mais de um produto com o mesmo CNPJ e registro: nenhum é escolhido),
    "ausente" (nenhum) ou "sem_registro" (a apresentação não tem os 13 dígitos). Sem situação: o arquivo
    dos registros não a tem por apresentação.
    """
    registrados = medicamentos[
        medicamentos["id_na_fonte"].str.startswith(
            TIPO_REGISTRADO + motor.SEPARADOR_DA_CHAVE
        )
    ]
    pares = pd.DataFrame(
        {
            "cnpj": registrados["cnpj"].map(cnpjs.completo),
            "registro_produto": registrados["registro"],
            "medicamento": registrados["id_na_fonte"],
            "processo": registrados["processo"],
        }
    ).drop_duplicates()
    chave = ["cnpj", "registro_produto"]
    quantos = pares.groupby(chave)["medicamento"].transform("nunique")
    unicos = pares[quantos.eq(1)].drop_duplicates(chave)
    multiplos = pares[quantos.gt(1)][chave].drop_duplicates().assign(multipla=True)
    saida = pd.DataFrame(
        {
            "id_na_fonte": apresentacoes["id_na_fonte"],
            "cnpj": apresentacoes["cnpj"].map(cnpjs.completo),
            "registro_produto": apresentacoes["registro_produto"],
        }
    )
    saida = saida.merge(unicos, how="left", on=chave, validate="many_to_one")
    saida = saida.merge(multiplos, how="left", on=chave, validate="many_to_one")
    saida["correspondencia"] = np.select(
        [
            saida["registro_produto"].isna(),
            saida["multipla"].eq(True),
            saida["medicamento"].notna(),
        ],
        ["sem_registro", "multipla", "unica"],
        "ausente",
    )
    colunas = ["id_na_fonte", "correspondencia", "medicamento", "processo"]
    return saida[colunas].astype(object).where(saida[colunas].notna(), None)


def _como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def _origens(achados: list[motor.Retrato]) -> list[dict[str, str]]:
    return [{"url": r.url, "sha256": r.sha256} for r in achados]


def _para_gravar(
    tabela: pd.DataFrame, pessoas: np.ndarray, agora: datetime
) -> pd.DataFrame:
    """Com os tipos do disco fixos: o mesmo decimal nos dois Parquets, para a porta ler os dois juntos."""
    basico = tabela["cnpj_basico"].astype(str)
    return (
        tabela.assign(
            trata_como_pessoa=cnpjs.contem(pessoas, cnpjs.raizes_em_numeros(basico))
            if len(tabela)
            else pd.Series(dtype=bool),
            **{
                c: pd.to_datetime(tabela[c]).dt.date
                for c in ["lista_publicada_em", "visto_em", "disponivel_em"]
            },
            **{c: tabela[c].astype(pd.ArrowDtype(TIPO_DO_PRECO)) for c in PRECOS},
            **{c: tabela[c].astype("boolean") for c in MARCAS},
            consta=tabela["consta"].astype(bool),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[[*COLUNAS, *LINHAGEM]]
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
    )


def _lidos(
    conexao: sa.Connection,
    achados: list[motor.Retrato],
    lista: str,
    resumo: dict[str, int],
) -> Iterator[tuple[motor.Retrato, pd.DataFrame]]:
    """Os retratos legíveis, com a data de publicação; o de layout novo é pulado e contado."""
    for retrato in achados:
        try:
            tabela, contagem = ler_retrato(retrato.caminho, lista)
        except LayoutNovo:
            resumo["retratos_com_layout_novo"] = (
                resumo.get("retratos_com_layout_novo", 0) + 1
            )
            continue
        resumo.update(
            contagem
        )  # a do retrato mais novo: as contagens são de um arquivo
        yield retrato, tabela.assign(lista_publicada_em=publicada_em(conexao, retrato))


def _destino(pasta: Path, lista: str) -> Path:
    return pasta / TABELA / lista


def _mais_novo(tabela: pd.DataFrame) -> pd.DataFrame:
    """As apresentações que constam no retrato mais novo, uma vez cada."""
    ultimas = tabela.sort_values(ORDEM, kind="stable").drop_duplicates(
        "id_na_fonte", keep="last"
    )
    return ultimas[ultimas["consta"].astype(bool)]


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/cmed_precos/<lista>.parquet` para cada lista com arquivo guardado.

    Lista sem arquivo guardado (ou só com arquivos de layout novo) fica de fora da tabela; sem retrato
    novo desde a última montagem, é pulada (`refazer` relê mesmo assim, para código novo). `pessoas`:
    as raízes de pessoa já sabidas; sem elas, pergunta à Receita guardada (`base/pgfn.py`).
    """
    resumo: dict[str, dict[str, int]] = {}
    for lista, arquivo in ARQUIVOS_DA_CMED.items():
        achados = motor.retratos(conexao, FONTE, "/" + arquivo)
        if not achados:
            continue
        destino = _destino(pasta, lista)
        if not refazer and origens_gravadas(destino) == _origens(achados):
            resumo[lista] = JA_MONTADO
            continue
        contagem: dict[str, int] = {}
        lidos = list(_lidos(conexao, achados, lista, contagem))
        if not lidos:
            resumo[lista] = {**contagem, "retratos": len(achados)}
            continue
        tabela, pulados = juntar_retratos(lidos)
        if pessoas is None:
            raizes = cnpjs.ordenados(
                cnpjs.raizes_em_numeros(
                    tabela["cnpj_basico"].drop_duplicates().astype(str)
                )
            )
            de_pessoa = pessoas_pela_receita(conexao, raizes)
        else:
            de_pessoa = _como_numeros(pessoas)
        gravar_se_mudou(
            _para_gravar(tabela, de_pessoa, agora),
            destino,
            _origens(achados),
            ORDEM,
            carimbos=LINHAGEM,
        )
        vigentes = _mais_novo(tabela)
        resumo[lista] = {
            **contagem,
            "retratos": len(achados),
            "retratos_pulados": pulados,
            "na_tabela": len(tabela),
            "apresentacoes": int(vigentes["id_na_fonte"].nunique()),
            "cnpjs": int(vigentes["cnpj"].nunique()),
            "produtos": int(
                vigentes.dropna(subset=["registro_produto"])[
                    ["cnpj", "registro_produto"]
                ]
                .drop_duplicates()
                .shape[0]
            ),
        }
    return resumo


def _medicamentos_vigentes(pasta: Path) -> pd.DataFrame | None:
    """As linhas de hoje do cadastro de medicamentos em `anvisa_registros`, ou None se não montado."""
    cadastro = licencas.CADASTROS["medicamentos"]
    caminho = pasta / cadastro.tabela / f"{cadastro.nome}.parquet"
    if not caminho.exists():
        return None
    tabela = pd.read_parquet(caminho)
    ultimas = tabela.sort_values("visto_em", kind="stable").drop_duplicates(
        "id_na_fonte", keep="last"
    )
    return ultimas[ultimas["consta"].astype(bool)]


def resumo_da_ponte(pasta: Path) -> dict[str, dict[str, int]]:
    """Para cada lista montada, quantas apresentações de hoje acham o produto registrado (`ponte`).

    Vazio quando os medicamentos de `anvisa_registros` ainda não foram montados na `pasta`.
    """
    medicamentos = _medicamentos_vigentes(pasta)
    if medicamentos is None:
        return {}
    resumo: dict[str, dict[str, int]] = {}
    for lista in ARQUIVOS_DA_CMED:
        caminho = _destino(pasta, lista).with_suffix(".parquet")
        if not caminho.exists():
            continue
        ligadas = ponte(_mais_novo(pd.read_parquet(caminho)), medicamentos)
        resumo[lista] = {
            **ligadas["correspondencia"].value_counts().to_dict(),
            "produtos": int(ligadas["medicamento"].nunique()),
        }
    return resumo
