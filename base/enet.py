"""Leitor do XML do ENET da CVM: as contas de cada versão de DFP e ITR (série 1, PR 5).

Os dados abertos da CVM (`base/contas_cvm.py`) só trazem a versão mais nova de cada documento. O
ENET entrega cada versão como um pacote zip com um XML; aqui o XML vira contas **no mesmo formato
dos dados abertos** (`COLUNAS`), para as regras compararem versões (R5) e para a base "como era na
data" (PR 6). Formato conferido em 13/10/2026 com o DFP 2022 v1 e o DFP 2024 v2 do BRB e o ITR 1T26
do Banco do Brasil:

- **Escala:** `EscalaMoeda` 1 = unidade, 2 = mil; outra é recusada (o pior erro é o de mil vezes).
- **Números em dois formatos:** "40.090.803" (ponto de milhar) e "31751760,0000000000" (vírgula
  decimal), às vezes no mesmo documento. Em branco fica vazio, nunca zero.
- **Datas:** o ENET informa o começo do ano do DFP com o dia errado (01/12 em vez de 01/01); o
  começo do resultado anual é calculado (um ano antes do fim), como nos dados abertos. Balanço é um
  saldo numa data: sem início.
- **Demonstrações:** BPA, BPP, DRE, DRA, DFC e DVA, individual e consolidado, em `contas` (série
  T1). A DFC vem num quadro só, com o método em cada conta (`Metodo`: "Indireto" ou "Direto"): vira
  DFC_MI ou DFC_MD, como os dois arquivos dos dados abertos; método desconhecido fica de fora (no
  acervo de 19/10/2026 só havia os dois). A DMPL tem uma coluna a mais (capital social, reservas...)
  e vai para `dmpl` (`base/dmpl.py`): um bloco por período, com a coluna numa tag própria
  (`PatrimonioLiquido`) ou numa lista de campos com a descrição; o antepenúltimo exercício do DFP
  fica de fora, como nos dados abertos, e o valor em branco também (os dados abertos o omitem).
- **Plano de contas inteiro:** o ENET traz todas as contas do modelo, e as que a empresa não usa vêm
  zeradas; os dados abertos as omitem. No ITR 1T26 do Banco do Brasil, 4.260 das 4.772 linhas
  eram esses zeros; as outras 512 bateram, uma a uma, com os dados abertos (conferido em 13/10/2026).
- **Nada pessoal, nada de PDF:** o XML traz o PDF do documento em base64 (quase todo o tamanho) e o
  nome, e-mail e telefone de quem entregou. A leitura ignora os dois; `limpar_xml` os tira antes de o
  XML ir para o acervo. Leitura em fluxo (`iterparse`), soltando cada elemento já lido.
"""

import io
import re
from dataclasses import dataclass, field

import pandas as pd
from defusedxml.ElementTree import iterparse

from base.cnpj import formatar, normalizar_cnpj
from base.contas_cvm import COLUNAS
from base.dmpl import COLUNAS_DA_DMPL, coluna_canonica

ESCALAS = {"1": 1.0, "2": 1000.0}
DEMONSTRACOES = {
    "BalancoPatrimonialAtivo": "BPA",
    "BalancoPatrimonialPassivo": "BPP",
    "DemonstracaoResultado": "DRE",
    "DemonstracaoResultadoAbrangente": "DRA",
    "DemonstracaoValorAdicionado": "DVA",
}
QUADRO_DA_DFC = "DemonstracaoFluxoCaixa"
METODOS_DA_DFC = {"Indireto": "DFC_MI", "Direto": "DFC_MD"}
QUADRO_DA_DMPL = (
    "DMPL"  # um por período, dentro de DemonstracaoMutacoesPatrimonioLiquido
)
# as colunas da DMPL que o ENET traz numa tag própria → a coluna canônica de `base/dmpl.py`
TAGS_DA_DMPL = {
    "CapitalSocialIntegralizado": "capital_social",
    "ReservasCapital": "reservas_de_capital",
    "ReservasCapitalOpcoesOutorgAcoesTesour": "reservas_de_capital",
    "ReservasLucro": "reservas_de_lucro",
    "LucroPrejuizoAcumulado": "lucros_acumulados",
    "OutrosResultadosAbrangentes": "outros_resultados_abrangentes",
    "AjustesAvaliacaoPatrimonial": "ajustes_de_avaliacao_patrimonial",
    "ReservasReavaliacao": "reservas_de_reavaliacao",
    "PatrimonioLiquido": "patrimonio_liquido",
    "PatrimonioLiquidoAcionistasControl": "patrimonio_liquido",
    "PatrimonioLiquidoAcionistasNaoControl": "nao_controladores",
    "PatrimonioLiquidoConsolidado": "patrimonio_liquido_consolidado",
}
GRUPOS = {"DfIndividuais": "ind", "DfConsolidadas": "con"}
DOCUMENTOS = {"DadosDFP": "DFP", "DadosITR": "ITR"}
DO_BALANCO = ("BPA", "BPP")
UM_ANO = pd.DateOffset(years=1)
UM_DIA = pd.Timedelta(days=1)
CAMPOS_DA_CONTA = ("CodigoConta", "DescricaoConta", "ContaFixa")
CAMPOS_DO_DOCUMENTO = (
    "CnpjEmpresa",
    "RazaoSocialEmpresa",
    "VersaoDocumento",
    "MotivoReapresentacao",
    "EscalaMoeda",
    "DataReferencia",
    "DtFimUltimoExercicioSocial",
    "DtFimPenultimoExercicioSocial",
    "DtFimTrimestreAtual",
    "DtInicioTrimestreAtual",
    "DtInicioExercicioSocialCurso",
    "DtFimExercicioSocialAnterior",
)
# colunas de valor de cada documento → (ordem nos dados abertos, tipo do período)
COLUNAS_DE_VALOR = {
    "DFP": {
        "UltimoExercicio": ("ultimo", "ano"),
        "PenultimoExercicio": ("penultimo", "ano"),
    },
    "ITR": {
        "TrimestreAtual": ("ultimo", "trimestre"),
        "AcumuladoExercicioAtual": ("ultimo", "acumulado"),
        "TrimestreAnterior": ("penultimo", "trimestre"),
        "AcumuladoExercicioAnterior": ("penultimo", "acumulado"),
        "ExercicioAnterior": ("penultimo", "fim_do_ano"),
    },
}
# o que `limpar_xml` esvazia: o PDF embutido e os dados de quem entregou o documento
TAGS_A_ESVAZIAR = (
    b"ImagemObjetoArquivoPdf",
    b"NomeResponsavel",
    b"EmailResponsavel",
    b"TelefoneResponsavel",
    b"DddResponsavel",
)
_ESVAZIAR = re.compile(
    rb"<(" + b"|".join(TAGS_A_ESVAZIAR) + rb")>.*?</\1>", flags=re.DOTALL
)


@dataclass(frozen=True)
class DocumentoEnet:
    cnpj: str  # 00.000.000/0000-00, como nos dados abertos
    empresa: str
    documento: str  # DFP ou ITR
    referencia: pd.Timestamp
    versao: int
    motivo: str  # o motivo da reapresentação que a empresa escreveu ("" na versão 1)
    contas: pd.DataFrame  # colunas em `COLUNAS`
    dmpl: pd.DataFrame = field(  # colunas em `COLUNAS_DA_DMPL` (vazia no XML sem DMPL)
        default_factory=lambda: pd.DataFrame(columns=list(COLUNAS_DA_DMPL))
    )


@dataclass
class _Lido:
    """O que a leitura em fluxo junta do XML, ainda em texto."""

    campos: dict[str, str] = field(default_factory=dict)
    documento: str = ""
    contas: list[dict[str, str]] = field(default_factory=list)
    dmpl: list["_ContaDaDmpl"] = field(default_factory=list)


@dataclass
class _ContaDaDmpl:
    conta: dict[str, str]  # CodigoConta, DescricaoConta, ContaFixa e as tags de coluna
    campos: list[tuple[str, str]]  # (descrição da coluna, valor) da lista de campos
    grupo: str
    periodo: dict[str, str]  # DtInicio e DtFim do bloco


def limpar_xml(conteudo: bytes) -> bytes:
    """O XML sem o PDF embutido e sem os dados de quem entregou (o resto, byte a byte igual)."""
    return _ESVAZIAR.sub(rb"<\1 />", conteudo)


def _numero(texto: str | None) -> float:
    texto = (texto or "").strip()
    if not texto:
        return float("nan")
    return float(texto.replace(".", "").replace(",", "."))


def _data(texto: str | None) -> pd.Timestamp:
    return pd.to_datetime((texto or "").strip(), format="%d/%m/%Y", errors="coerce")


def _cnpj(texto: str) -> str:
    """O CNPJ formatado (com letras, se tiver); vazio se o XML não trouxer um CNPJ."""
    completo = normalizar_cnpj(texto)
    return formatar(completo) if completo else ""


def _demonstracao(pilha: list[str], conta: dict[str, str]) -> str | None:
    if QUADRO_DA_DFC in pilha:
        return METODOS_DA_DFC.get(conta.get("Metodo", ""))
    return next((DEMONSTRACOES[t] for t in pilha if t in DEMONSTRACOES), None)


def _ler(conteudo: bytes) -> _Lido:
    """Os campos do documento, DFP ou ITR e as contas cruas com o grupo e a demonstração."""
    lido = _Lido()
    pilha: list[str] = []
    conta: dict[str, str] = {}
    campos_da_conta: list[tuple[str, str]] = []
    campo: dict[str, str] = {}
    periodo: dict[str, str] = {}
    for evento, elemento in iterparse(io.BytesIO(conteudo), events=("start", "end")):
        tag = elemento.tag
        if evento == "start":
            pilha.append(tag)
            lido.documento = lido.documento or DOCUMENTOS.get(tag, "")
            if tag == "Conta":
                conta, campos_da_conta = {}, []
            elif tag == QUADRO_DA_DMPL:
                periodo = {}
            continue
        pilha.pop()
        texto = (elemento.text or "").strip()
        if tag in CAMPOS_DO_DOCUMENTO:
            lido.campos[tag] = texto
        elif "CamposDadosContas" in pilha:
            campo[tag] = texto
        elif tag == "CamposDadosContas":
            campos_da_conta.append((campo.get("Descricao", ""), campo.get("Valor", "")))
            campo = {}
        elif "Conta" in pilha:
            conta[tag] = texto
        elif tag == "Conta":
            _guardar_conta(lido, pilha, conta, campos_da_conta, periodo)
        elif QUADRO_DA_DMPL in pilha and tag in ("DtInicio", "DtFim"):
            periodo[tag] = texto
        elemento.clear()  # o PDF em base64 é quase todo o arquivo: nada fica na memória
    return lido


def _guardar_conta(
    lido: _Lido,
    pilha: list[str],
    conta: dict[str, str],
    campos_da_conta: list[tuple[str, str]],
    periodo: dict[str, str],
) -> None:
    grupo = next((GRUPOS[t] for t in pilha if t in GRUPOS), None)
    if not grupo or not conta.get("CodigoConta"):
        return
    if QUADRO_DA_DMPL in pilha:
        lido.dmpl.append(_ContaDaDmpl(conta, campos_da_conta, grupo, dict(periodo)))
        return
    demonstracao = _demonstracao(pilha, conta)
    if demonstracao:
        lido.contas.append(conta | {"grupo": grupo, "demonstracao": demonstracao})


def _periodo(
    documento: str, tipo: str, ordem: str, demonstracao: str, campos: dict[str, str]
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """(início, fim) de uma coluna de valor; balanço sem início."""
    if documento == "DFP":
        nome = "Ultimo" if ordem == "ultimo" else "Penultimo"
        fim = _data(campos.get(f"DtFim{nome}ExercicioSocial"))
        inicio = fim - UM_ANO + UM_DIA
    elif tipo == "fim_do_ano":
        return pd.NaT, _data(campos.get("DtFimExercicioSocialAnterior"))
    else:
        fim = _data(campos.get("DtFimTrimestreAtual"))
        comeco = (
            "DtInicioTrimestreAtual"
            if tipo == "trimestre"
            else "DtInicioExercicioSocialCurso"
        )
        inicio = _data(campos.get(comeco))
        if ordem == "penultimo":
            inicio, fim = inicio - UM_ANO, fim - UM_ANO
    if demonstracao in DO_BALANCO:
        return pd.NaT, fim
    return inicio, fim


def _linhas(
    conta: dict[str, str], documento: str, campos: dict[str, str], escala: float
) -> list[dict[str, object]]:
    linhas = []
    for coluna, (ordem, tipo) in COLUNAS_DE_VALOR[documento].items():
        if coluna not in conta:
            continue
        demonstracao = conta["demonstracao"]
        inicio, fim = _periodo(documento, tipo, ordem, demonstracao, campos)
        linhas.append(
            {
                "demonstracao": demonstracao,
                "grupo": conta["grupo"],
                "ordem": ordem,
                "inicio": inicio,
                "fim": fim,
                "conta": conta["CodigoConta"],
                "descricao": conta.get("DescricaoConta", ""),
                "conta_fixa": conta.get("ContaFixa", "").lower() == "true",
                "valor": _numero(conta[coluna]) * escala,
            }
        )
    return linhas


def _ordem_da_dmpl(
    documento: str, fim: pd.Timestamp, campos: dict[str, str]
) -> str | None:
    """ "ultimo" ou "penultimo" pelo fim do período do bloco; None no antepenúltimo do DFP."""
    if documento == "DFP":
        ultimo = _data(campos.get("DtFimUltimoExercicioSocial"))
        penultimo = _data(campos.get("DtFimPenultimoExercicioSocial"))
    else:
        ultimo = _data(campos.get("DtFimTrimestreAtual"))
        penultimo = ultimo - UM_ANO
    if fim == ultimo:
        return "ultimo"
    return "penultimo" if fim == penultimo else None


def _linhas_da_dmpl(
    crua: _ContaDaDmpl, documento: str, campos: dict[str, str], escala: float
) -> list[dict[str, object]]:
    fim = _data(crua.periodo.get("DtFim"))
    ordem = _ordem_da_dmpl(documento, fim, campos)
    if ordem is None:
        return []
    # o começo do ano do DFP vem com o dia errado em outros quadros: calculado, como no resultado
    inicio = (
        fim - UM_ANO + UM_DIA
        if documento == "DFP"
        else _data(crua.periodo.get("DtInicio"))
    )
    valores = [
        (coluna, crua.conta[tag])
        for tag, coluna in TAGS_DA_DMPL.items()
        if tag in crua.conta
    ] + [(coluna_canonica(descricao), texto) for descricao, texto in crua.campos]
    linhas = []
    for coluna, texto in valores:
        valor = _numero(texto)
        if pd.isna(valor):
            continue
        linhas.append(
            {
                "demonstracao": "DMPL",
                "grupo": crua.grupo,
                "ordem": ordem,
                "inicio": inicio,
                "fim": fim,
                "conta": crua.conta["CodigoConta"],
                "descricao": crua.conta.get("DescricaoConta", ""),
                "conta_fixa": crua.conta.get("ContaFixa", "").lower() == "true",
                "valor": valor * escala,
                "coluna": coluna,
            }
        )
    return linhas


def montar_tabela(
    linhas: list[dict[str, object]],
    colunas: tuple[str, ...],
    identidade: dict[str, object],
    versao: int,
) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas, columns=list(colunas)).assign(**identidade)
    tabela["versao"] = pd.Series(versao, index=tabela.index, dtype="Int64")
    # no 1º trimestre, o trimestre e o acumulado são o mesmo período: uma linha só
    return tabela.reindex(columns=list(colunas)).drop_duplicates(ignore_index=True)


def ler_xml_enet(conteudo: bytes) -> DocumentoEnet:
    """As contas (individual e consolidado) de um XML de DFP ou ITR do ENET; a DMPL à parte."""
    lido = _ler(conteudo)
    campos, documento = lido.campos, lido.documento
    if documento not in COLUNAS_DE_VALOR:
        raise ValueError("o XML não é de DFP nem de ITR do ENET")
    escala = ESCALAS.get(campos.get("EscalaMoeda", ""))
    if escala is None:
        raise ValueError(
            f"escala desconhecida no XML do ENET: {campos.get('EscalaMoeda')!r}"
        )
    cnpj = _cnpj(campos.get("CnpjEmpresa", ""))
    empresa = campos.get("RazaoSocialEmpresa", "")
    referencia = _data(campos.get("DataReferencia"))
    versao = int(campos.get("VersaoDocumento") or 0)
    identidade: dict[str, object] = {
        "cnpj": cnpj,
        "empresa": empresa,
        "documento": documento,
        "referencia": referencia,
    }
    linhas = [
        linha
        for conta in lido.contas
        for linha in _linhas(conta, documento, campos, escala)
    ]
    linhas_da_dmpl = [
        linha
        for crua in lido.dmpl
        for linha in _linhas_da_dmpl(crua, documento, campos, escala)
    ]
    return DocumentoEnet(
        cnpj=cnpj,
        empresa=empresa,
        documento=documento,
        referencia=referencia,
        versao=versao,
        motivo=campos.get("MotivoReapresentacao", ""),
        contas=montar_tabela(linhas, COLUNAS, identidade, versao),
        dmpl=montar_tabela(linhas_da_dmpl, COLUNAS_DA_DMPL, identidade, versao),
    )
