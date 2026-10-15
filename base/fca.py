"""Código permanente da ação pelo FCA da CVM (série 3 da base de ML, PR 3; pedido 1 da sessão "FactSet").

O FCA (formulário cadastral) traz, por companhia e ano, os valores mobiliários: espécie, classe,
código de negociação, mercado, segmento e datas de negociação e listagem. O inventário de 14/10/2026
mudou o desenho:

- **até 2017 o FCA não traz ticker** (só as ações ON, sem código de negociação); de 2018 em diante,
  ~96% das linhas da bolsa têm ticker;
- a **troca de ticker regrava a mesma linha** com a mesma data de início (a Via foi VVAR3, VIIA3 e
  BHIA3 desde 2018-11-26): a validade de cada ticker vem do **ano do FCA** em que foi informado;
- há código fora do formato (a CSN informa "4030"): não vira ticker e vai para a lista de inválidos.

Por isso o código permanente é o **ISIN** (o CDA o traz desde 2005), e a ligação ao CNPJ passa pelo
**emissor** (as 4 letras depois de "BR"). Um emissor com mais de um CNPJ é conflito e fica sem
resposta: nada é casado no escuro.

Algumas empresas da bolsa informam o código fora do formato (o BTG põe "000000" nas units): sem
ticker, ficavam sem emissor e sem ligação com os fundos e com o IF.data. A **tabela conferida**
`base/conferidas/codigos_fora_do_fca.csv` (série 3, PR 8) traz esses códigos, um a um: o CNPJ vem do
próprio FCA e o código e o ISIN, das carteiras dos fundos (CDA). `com_codigos_conferidos` junta a
tabela aos tickers e aos emissores do FCA, com a origem de cada linha.

**Data de entrega** (série 4, PR 1): o FCA de um ano chega meses depois da data de referência
(mediana de 138 dias de 2010 a 2026). Cada linha leva o `DT_RECEB` do documento dela (arquivo
principal do zip, pelo `ID_Documento`), e um ticker vale da entrega do formulário que o trouxe até a
entrega do que veio sem ele. A CVM publica os valores mobiliários **só da versão mais nova** de cada
formulário (o arquivo principal lista todas): a data que vale é a dessa versão.
"""

import io
import re
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

CODIFICACAO_DA_CVM = "latin-1"
# o emissor tem 4 posições começando por letra e pode ter número (B3SA, da B3); o ticker é o emissor
# mais o número da classe. O código informado no FCA às vezes vem sem o número (NEOE) ou com o
# sufixo do balcão (LTEL3B): dá o emissor, mas não é ticker de bolsa (série 3, PR 5)
EMISSOR = r"[A-Z][A-Z0-9]{3}"
TICKER = re.compile(rf"{EMISSOR}\d{{1,2}}")
CODIGO_COM_EMISSOR = re.compile(rf"({EMISSOR})(?:\d{{1,2}}[A-Z]?)?")
ISIN = re.compile(r"BR([A-Z0-9]{4})[A-Z0-9]{5}\d")
COLUNAS = (
    "cnpj", "empresa", "referencia", "versao", "id_documento", "recebido_em", "valor_mobiliario",
    "classe", "codigo_informado",
    "ticker", "emissor", "mercado", "administradora", "inicio_negociacao", "fim_negociacao",
    "segmento", "inicio_listagem", "fim_listagem",
)  # fmt: skip
DOCUMENTO = ["cnpj", "referencia"]
ARQUIVO_PRINCIPAL = re.compile(r"fca_cia_aberta_\d{4}\.csv")
CODIGOS_CONFERIDOS = (
    Path(__file__).resolve().parent / "conferidas" / "codigos_fora_do_fca.csv"
)
PELO_FCA, PELOS_CODIGOS_CONFERIDOS = "fca", "códigos conferidos"


def _texto(serie: pd.Series) -> pd.Series:
    return serie.str.strip().replace("", None)


def _data(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce")


def ticker_do_codigo(codigo: object) -> str | None:
    """O código, se for ticker de bolsa (PETR4, B3SA3, TAEE11); senão None."""
    if not isinstance(codigo, str):
        return None
    codigo = codigo.strip().upper()
    return codigo if TICKER.fullmatch(codigo) else None


def emissor_do_codigo(codigo: object) -> str | None:
    """As 4 posições do emissor num código informado (PETR4, NEOE, LTEL3B); None se não tiver."""
    if not isinstance(codigo, str):
        return None
    achado = CODIGO_COM_EMISSOR.fullmatch(codigo.strip().upper())
    return achado.group(1) if achado else None


def mais_novas(tabela: pd.DataFrame) -> pd.DataFrame:
    """Só a versão mais nova de cada documento (companhia + data de referência)."""
    if tabela.empty:
        return tabela
    maior = tabela.groupby(DOCUMENTO)["versao"].transform("max")
    return tabela[tabela["versao"] == maior].reset_index(drop=True)


def _ler_csv(arquivo: zipfile.ZipFile, nome: str) -> pd.DataFrame:
    return pd.read_csv(
        arquivo.open(nome), sep=";", encoding=CODIFICACAO_DA_CVM, dtype=str,
        keep_default_na=False,
    )  # fmt: skip


def _entregas(arquivo: zipfile.ZipFile) -> pd.Series:
    """Data de entrega (`DT_RECEB`) de cada documento do zip, pelo número (`ID_DOC`)."""
    nome = next((n for n in arquivo.namelist() if ARQUIVO_PRINCIPAL.fullmatch(n)), None)
    if nome is None:
        raise ValueError(
            "FCA sem o arquivo principal (fca_cia_aberta_<ano>.csv): sem a data de entrega"
        )
    principal = _ler_csv(arquivo, nome)
    return _data(principal.set_index(principal["ID_DOC"].str.strip())["DT_RECEB"])


def ler_valores_mobiliarios(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os valores mobiliários de um arquivo anual do FCA, na versão mais nova de cada documento, com
    a data de entrega dela (`recebido_em`). Documento sem data de entrega é erro."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next(n for n in arquivo.namelist() if "_valor_mobiliario_" in n)
        bruto = _ler_csv(arquivo, nome)
        entregas = _entregas(arquivo)
    codigo = _texto(bruto["Codigo_Negociacao"])
    documento = bruto["ID_Documento"].str.strip()
    recebido_em = documento.map(entregas)
    if recebido_em.isna().any():
        sem_data = sorted(set(documento[recebido_em.isna()]))
        raise ValueError(f"FCA com documento sem data de entrega: {sem_data[:5]}")
    tabela = pd.DataFrame(
        {
            "cnpj": bruto["CNPJ_Companhia"].str.strip(),
            "empresa": bruto["Nome_Empresarial"].str.strip(),
            "referencia": _data(bruto["Data_Referencia"]),
            "versao": pd.to_numeric(bruto["Versao"], errors="coerce")
            .fillna(1)
            .astype(int),
            "id_documento": documento,
            "recebido_em": recebido_em,
            "valor_mobiliario": _texto(bruto["Valor_Mobiliario"]),
            "classe": _texto(bruto["Classe_Acao_Preferencial"]),
            "codigo_informado": codigo,
            "ticker": codigo.map(ticker_do_codigo),
            "emissor": codigo.map(emissor_do_codigo),
            "mercado": _texto(bruto["Mercado"]),
            "administradora": _texto(bruto["Sigla_Entidade_Administradora"]),
            "inicio_negociacao": _data(bruto["Data_Inicio_Negociacao"]),
            "fim_negociacao": _data(bruto["Data_Fim_Negociacao"]),
            "segmento": _texto(bruto["Segmento"]),
            "inicio_listagem": _data(bruto["Data_Inicio_Listagem"]),
            "fim_listagem": _data(bruto["Data_Fim_Listagem"]),
        }
    )
    return mais_novas(tabela)[list(COLUNAS)]


def codigos_invalidos(valores: pd.DataFrame) -> pd.DataFrame:
    """Linhas com código informado que não dá nem o emissor ("4030", "NÃO HÁ"), para o relatório."""
    ruins = valores[valores["codigo_informado"].notna() & valores["emissor"].isna()]
    return ruins[
        [
            "cnpj", "empresa", "referencia", "recebido_em", "valor_mobiliario",
            "codigo_informado",
        ]
    ]  # fmt: skip


def emissor_do_isin(isin: object) -> str | None:
    """As 4 letras do emissor num ISIN brasileiro ("BRMAGSACNPC8" → "MAGS"); None se não for ISIN."""
    if not isinstance(isin, str):
        return None
    achado = ISIN.fullmatch(isin.strip())
    return achado.group(1) if achado else None


def emissores(valores: pd.DataFrame) -> pd.DataFrame:
    """Emissor → CNPJ, com o primeiro e o último ano do FCA em que apareceu, a entrega do primeiro
    (desde quando a ligação é conhecida) e se há conflito."""
    com_emissor = valores[valores["emissor"].notna()].assign(
        ano=lambda t: t["referencia"].dt.year
    )
    tabela = (
        com_emissor.groupby(["emissor", "cnpj"])
        .agg(
            empresa=("empresa", "last"),
            primeiro_ano=("ano", "min"),
            ultimo_ano=("ano", "max"),
            primeiro_recebido_em=("recebido_em", "min"),
        )
        .reset_index()
    )
    return _com_conflito(tabela)


def resolver_emissor(tabela_de_emissores: pd.DataFrame, emissor: str) -> str | None:
    """O CNPJ do emissor, ou None se não há ligação ou se ela é conflito."""
    linhas = tabela_de_emissores[tabela_de_emissores["emissor"] == emissor]
    if len(linhas) != 1 or bool(linhas["conflito"].iloc[0]):
        return None
    return str(linhas["cnpj"].iloc[0])


def vale_na_data(tickers: pd.DataFrame, data: object) -> pd.Series:
    """Quais linhas de `tickers` valem na data (uma só, ou uma por linha): da entrega do formulário
    que trouxe o código (`primeiro_visto`, inclusive) até a do que veio sem ele (`valido_ate`,
    exclusive; vazio = ainda no formulário mais recente)."""
    quando = data if isinstance(data, pd.Series) else pd.Timestamp(data)  # type: ignore[arg-type]
    return (tickers["primeiro_visto"] <= quando) & (
        tickers["valido_ate"].isna() | (quando < tickers["valido_ate"])
    )


def resolver_ticker(tickers: pd.DataFrame, ticker: str, data: date) -> str | None:
    """O CNPJ dono do ticker na data; None se ninguém (ou mais de um) o tinha.

    `tickers` é a tabela de `base/cadastro.py::tickers_no_tempo`: só vale o que já tinha sido
    entregue à CVM na data (série 4, PR 1; antes valia o ano do FCA, que chega meses depois).
    """
    vigentes = tickers[(tickers["codigo"] == ticker) & vale_na_data(tickers, data)]
    return str(vigentes["cnpj"].iloc[0]) if vigentes["cnpj"].nunique() == 1 else None


def formularios_vigentes(valores: pd.DataFrame) -> pd.DataFrame:
    """A linha do tempo dos formulários de cada companhia: qual valia de quando até quando.

    Numa data, vale o FCA de referência mais nova entre os já entregues (a reentrega de um ano antigo
    depois de um mais novo não volta no tempo). Só entram os formulários com valores mobiliários: o
    vazio é falta de dado, não saída da bolsa (264 FCA de empresas listadas, de 2010 a 2026, vêm
    vazios entre anos com ação). Colunas: cnpj, id_documento, recebido_em, ate (entrega do seguinte;
    vazio = o mais recente) e ordem (0, 1, 2... por companhia).
    """
    documentos = (
        valores[["cnpj", "id_documento", "referencia", "versao", "recebido_em"]]
        .drop_duplicates("id_documento")
        .sort_values(["cnpj", "recebido_em", "referencia", "versao"])
    )
    # (referência, versão) num número só, para comparar com o maior já entregue: as referências
    # distam dias (em nanossegundos) e a versão é pequena
    chave = documentos["referencia"].astype("int64") + documentos["versao"]
    maior_antes = chave.groupby(documentos["cnpj"]).transform(
        lambda c: c.cummax().shift()
    )
    vigentes = documentos[maior_antes.isna() | (chave > maior_antes)].copy()
    vigentes["ate"] = vigentes.groupby("cnpj")["recebido_em"].shift(-1)
    # trocado no mesmo dia em que chegou: nunca valeu
    vigentes = vigentes[~(vigentes["ate"] <= vigentes["recebido_em"])].copy()
    vigentes["ate"] = vigentes.groupby("cnpj")["recebido_em"].shift(-1)
    vigentes["ordem"] = vigentes.groupby("cnpj").cumcount()
    return vigentes[["cnpj", "id_documento", "recebido_em", "ate", "ordem"]]


def codigos_conferidos(caminho: Path = CODIGOS_CONFERIDOS) -> pd.DataFrame:
    """A tabela de códigos que o FCA traz fora do formato, conferida linha a linha (com a fonte)."""
    tabela = pd.read_csv(
        caminho, sep=";", dtype=str, keep_default_na=False, encoding="utf-8"
    )
    for coluna in ("primeiro_no_cda", "ultimo_no_cda", "conferido_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela


def _com_conflito(emissores: pd.DataFrame) -> pd.DataFrame:
    conflito = emissores.groupby("emissor")["cnpj"].transform("nunique") > 1
    return emissores.assign(conflito=conflito).reset_index(drop=True)


def com_codigos_conferidos(
    tickers: pd.DataFrame, emissores: pd.DataFrame, conferidos: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Os tickers e os emissores do FCA mais os da tabela conferida, com a coluna `origem`.

    O código conferido vale do 1º mês em que aparece nas carteiras dos fundos até o fim do ano do
    último (como valia antes da data de entrega do FCA). O que o FCA já traz com o mesmo CNPJ fica
    como está; com outro CNPJ, vira conflito (ninguém fica com ele).
    """
    novos = pd.DataFrame(
        {
            "codigo": conferidos["codigo"],
            "cnpj": conferidos["cnpj"],
            "empresa": conferidos["empresa"],
            "valor_mobiliario": conferidos["valor_mobiliario"],
            "primeiro_visto": conferidos["primeiro_no_cda"],
            "ultimo_visto": conferidos["ultimo_no_cda"],
            "valido_ate": conferidos["ultimo_no_cda"] + pd.offsets.YearBegin(),
            "inicio_negociacao": pd.NaT,
            "fim_negociacao": pd.NaT,
            "origem": PELOS_CODIGOS_CONFERIDOS,
        }
    )
    do_fca = set(zip(tickers["codigo"], tickers["cnpj"], strict=True))
    novos = novos[
        [par not in do_fca for par in zip(novos["codigo"], novos["cnpj"], strict=True)]
    ]
    todos_os_tickers = pd.concat(
        [tickers.assign(origem=PELO_FCA), novos], ignore_index=True
    )
    emissores_novos = (
        novos.assign(emissor=novos["codigo"].map(emissor_do_codigo))
        .groupby(["emissor", "cnpj"])
        .agg(
            empresa=("empresa", "last"),
            primeiro_ano=("primeiro_visto", lambda d: d.dt.year.min()),
            ultimo_ano=("ultimo_visto", lambda d: d.dt.year.max()),
            primeiro_recebido_em=("primeiro_visto", "min"),
        )
        .reset_index()
        .assign(origem=PELOS_CODIGOS_CONFERIDOS)
    )
    ja_tem = set(zip(emissores["emissor"], emissores["cnpj"], strict=True))
    emissores_novos = emissores_novos[
        [
            par not in ja_tem
            for par in zip(
                emissores_novos["emissor"], emissores_novos["cnpj"], strict=True
            )
        ]
    ]
    todos_os_emissores = pd.concat(
        [emissores.drop(columns="conflito").assign(origem=PELO_FCA), emissores_novos],
        ignore_index=True,
    )
    return todos_os_tickers, _com_conflito(todos_os_emissores)
