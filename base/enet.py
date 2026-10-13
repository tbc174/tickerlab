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
- **Só BPA, BPP e DRE**, individual e consolidado (o que as regras usam). DVA, DMPL e DFC ficam fora.
- **Plano de contas inteiro:** o ENET traz todas as contas do modelo, e as que a empresa não usa vêm
  zeradas; os dados abertos as omitem. No ITR 1T26 do Banco do Brasil, 4.260 das 4.772 linhas
  eram esses zeros; as outras 512 bateram, uma a uma, com os dados abertos (conferido em 13/10/2026).
- **Nada pessoal, nada de PDF:** o XML traz o PDF do documento em base64 (quase todo o tamanho) e o
  nome, e-mail e telefone de quem entregou. A leitura ignora os dois; `limpar_xml` os tira antes de o
  XML ir para o acervo. Leitura em fluxo (`iterparse`), soltando cada elemento já lido.
"""

import io
import re
from dataclasses import dataclass

import pandas as pd
from defusedxml.ElementTree import iterparse

from base.contas_cvm import COLUNAS

ESCALAS = {"1": 1.0, "2": 1000.0}
DEMONSTRACOES = {
    "BalancoPatrimonialAtivo": "BPA",
    "BalancoPatrimonialPassivo": "BPP",
    "DemonstracaoResultado": "DRE",
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


def _cnpj(digitos: str) -> str:
    d = digitos.strip().zfill(14)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _ler(conteudo: bytes) -> tuple[dict[str, str], str, list[dict[str, str]]]:
    """(campos do documento, DFP ou ITR, contas cruas com o grupo e a demonstração)."""
    campos: dict[str, str] = {}
    contas: list[dict[str, str]] = []
    documento = ""
    pilha: list[str] = []
    conta: dict[str, str] = {}
    for evento, elemento in iterparse(io.BytesIO(conteudo), events=("start", "end")):
        tag = elemento.tag
        if evento == "start":
            pilha.append(tag)
            documento = documento or DOCUMENTOS.get(tag, "")
            if tag == "Conta":
                conta = {}
            continue
        pilha.pop()
        texto = (elemento.text or "").strip()
        if tag in CAMPOS_DO_DOCUMENTO:
            campos[tag] = texto
        elif "Conta" in pilha:
            conta[tag] = texto
        elif tag == "Conta":
            grupo = next((GRUPOS[t] for t in pilha if t in GRUPOS), None)
            demonstracao = next(
                (DEMONSTRACOES[t] for t in pilha if t in DEMONSTRACOES), None
            )
            if grupo and demonstracao and conta.get("CodigoConta"):
                contas.append(conta | {"grupo": grupo, "demonstracao": demonstracao})
        elemento.clear()  # o PDF em base64 é quase todo o arquivo: nada fica na memória
    return campos, documento, contas


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


def ler_xml_enet(conteudo: bytes) -> DocumentoEnet:
    """As contas de BPA, BPP e DRE (individual e consolidado) de um XML de DFP ou ITR do ENET."""
    campos, documento, cruas = _ler(conteudo)
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
    linhas = [
        linha for conta in cruas for linha in _linhas(conta, documento, campos, escala)
    ]
    contas = pd.DataFrame(linhas).assign(
        cnpj=cnpj, empresa=empresa, documento=documento, referencia=referencia
    )
    contas["versao"] = pd.Series(versao, index=contas.index, dtype="Int64")
    # no 1º trimestre, o trimestre e o acumulado são o mesmo período: uma linha só
    contas = contas.reindex(columns=list(COLUNAS)).drop_duplicates(ignore_index=True)
    return DocumentoEnet(
        cnpj=cnpj,
        empresa=empresa,
        documento=documento,
        referencia=referencia,
        versao=versao,
        motivo=campos.get("MotivoReapresentacao", ""),
        contas=contas,
    )
