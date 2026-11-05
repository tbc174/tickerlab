"""Totais do SUS por estabelecimento e mês: internações (SIH RD) e produção ambulatorial (SIA PA).

Os microdados do DATASUS têm uma linha por internação ou procedimento. Aqui eles **só existem na memória**:
o DBC é baixado do FTP para a memória, lido em fluxo (`base/dbc.py`), somado por estabelecimento e
descartado. Nada da linha do paciente é gravado; o que sai é o total do mês e o sha256 do arquivo.

Regras (ADR 0081 itens 3 e 4; ADR 0088 Emenda 1, Tiago em 05/11/2026; licença na ADR 0122):
- **colunas numa lista fechada**: só as que dizem de qual estabelecimento é a linha e os números que se
  somam. `COLUNAS_PROIBIDAS` lista o que identifica ou descreve uma pessoa e há teste que impede a mistura;
- **supressão antes de devolver**: menos de `MINIMO_PARA_PUBLICAR` (10) no mês, a linha sai com os números
  vazios e `suprimida`; óbito com menos de `MINIMO_PARA_OBITOS` (20) sai vazio. O acervo nunca recebe a
  célula pequena, então nenhuma soma posterior a reconstrói;
- **pessoa física fora**: o estabelecimento cujo documento próprio é um CPF (consultório) não entra, nem o
  que não tem CNPJ nenhum (nem o próprio nem o da mantenedora). A situação conta quantos saíram;
- **competência** é a do arquivo (mês de processamento do DATASUS), não o mês da alta ou do atendimento.

Internações seguem o TabNet: AIH de longa permanência (`IDENT` 5) não conta como internação nem como
óbito; valores e dias de permanência somam todas as AIH. Treino de modelo com este dado está barrado
(a resposta do MS não o cobre). Sem Streamlit; a rede fica atrás de `listar`/`baixar` injetáveis.
"""

import ftplib
import hashlib
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd
import pyarrow as pa

from base import cnes, cnpj, dbc

SERVIDOR_FTP = cnes.SERVIDOR_FTP
TEMPO_LIMITE_DO_FTP = 300  # o SIA de SP tem partes de mais de 100 MB comprimidas
UFS = cnes.UFS
MINIMO_PARA_PUBLICAR = 10
MINIMO_PARA_OBITOS = 20
LONGA_PERMANENCIA = (
    "5"  # IDENT da AIH de longa permanência (continuação de uma internação)
)
OBITO = "1"
COMPETENCIA_VAZIA = cnes.COMPETENCIA_VAZIA
COMPETENCIA_COM_DADOS = cnes.COMPETENCIA_COM_DADOS
TIPO_DO_DINHEIRO = pa.decimal128(18, 2)
CENTAVOS = Decimal("0.01")

COLUNAS_PROIBIDAS = frozenset({
    # quem é a pessoa ou quem a atendeu
    "N_AIH", "CPF_AUT", "GESTOR_CPF", "HOMONIMO", "PA_CNSMED", "PA_AUTORIZ", "CNS", "CNS_PAC",
    # onde mora e como é
    "NASC", "CEP", "MUNIC_RES", "SEXO", "IDADE", "COD_IDADE", "RACA_COR", "ETNIA", "INSTRU",
    "NUM_FILHOS", "NACIONAL", "VINCPREV", "CBOR", "CNAER",
    "PA_IDADE", "IDADEMIN", "IDADEMAX", "PA_SEXO", "PA_RACACOR", "PA_ETNIA", "PA_MUNPCN", "PA_CBOCOD",
    # a saúde dela
    "DIAG_PRINC", "DIAG_SECUN", "CID_ASSO", "CID_MORTE", "CID_NOTIF", "INFEHOSP", "GESTRISCO",
    "CONTRACEP1", "CONTRACEP2", "DIAGSEC1", "DIAGSEC2", "DIAGSEC3", "DIAGSEC4", "DIAGSEC5",
    "DIAGSEC6", "DIAGSEC7", "DIAGSEC8", "DIAGSEC9", "PA_CIDPRI", "PA_CIDSEC", "PA_CIDCAS",
    # datas que, com o hospital, apontam a pessoa
    "DT_INTER", "DT_SAIDA",
})  # fmt: skip


@dataclass(frozen=True)
class Sistema:
    """Um sistema do DATASUS lido aqui: de onde vem, que colunas lê e o que a tabela entrega."""

    nome: str
    fonte: str
    pasta_no_ftp: str
    prefixo: str
    aceita_partes: bool  # o SIA divide os estados grandes em PA<UF><AAMM>a.dbc, b, c...
    coluna_cnes: str
    coluna_documento: str
    coluna_mantenedora: str
    coluna_municipio: str
    colunas_somadas: tuple[str, ...]
    numeros: tuple[str, ...]  # colunas da tabela que a supressão esvazia
    marcas: tuple[str, ...]

    @property
    def colunas(self) -> tuple[str, ...]:
        """As colunas lidas do DBC: as únicas que saem do arquivo, mesmo na memória."""
        return (
            self.coluna_cnes,
            self.coluna_documento,
            self.coluna_mantenedora,
            self.coluna_municipio,
            *self.colunas_somadas,
        )

    @property
    def colunas_da_tabela(self) -> tuple[str, ...]:
        return (*COLUNAS_DE_IDENTIFICACAO, *self.numeros, *self.marcas, "disponivel_em")


COLUNAS_DE_IDENTIFICACAO = (
    "competencia",
    "codigo_cnes",
    "cnpj",
    "cnpj_mantenedora",
    "codigo_ibge_municipio",
    "uf",
)
CHAVE = ["competencia", "codigo_cnes"]
DINHEIRO = ("valor_total", "valor_uti", "valor_apresentado", "valor_aprovado")

SIH = Sistema(
    nome="sih",
    fonte="ms-sih-rd-competencia",
    pasta_no_ftp="/dissemin/publicos/SIHSUS/200801_/Dados",
    prefixo="RD",
    aceita_partes=False,
    coluna_cnes="CNES",
    coluna_documento="CGC_HOSP",
    coluna_mantenedora="CNPJ_MANT",
    coluna_municipio="MUNIC_MOV",
    colunas_somadas=("IDENT", "VAL_TOT", "VAL_UTI", "DIAS_PERM", "MORTE"),
    numeros=("internacoes", "valor_total", "valor_uti", "dias_permanencia", "obitos"),
    marcas=("suprimida", "obitos_suprimidos"),
)
SIA = Sistema(
    nome="sia",
    fonte="ms-sia-pa-competencia",
    pasta_no_ftp="/dissemin/publicos/SIASUS/200801_/Dados",
    prefixo="PA",
    aceita_partes=True,
    coluna_cnes="PA_CODUNI",
    coluna_documento="PA_CNPJCPF",
    coluna_mantenedora="PA_CNPJMNT",
    coluna_municipio="PA_UFMUN",
    colunas_somadas=("PA_QTDPRO", "PA_QTDAPR", "PA_VALPRO", "PA_VALAPR"),
    numeros=(
        "quantidade_apresentada",
        "quantidade_aprovada",
        "valor_apresentado",
        "valor_aprovado",
    ),
    marcas=("suprimida",),
)
SISTEMAS = {SIH.nome: SIH, SIA.nome: SIA}

# A situação é de uso interno (conferência com o TabNet e o painel das coletas): `registros` por UF, menos a
# soma publicada, revelaria a célula suprimida de uma UF com um só estabelecimento abaixo de 10. Não sai
# na API, no site nem na ficha.
COLUNAS_DA_SITUACAO = (
    "competencia",
    "uf",
    "sistema",
    "arquivos",
    "sha256",
    "registros",
    "estabelecimentos",
    "suprimidos",
    "fora_pessoa_fisica",
    "fora_sem_cnpj",
    "situacao",
    "coletado_em",
)

Listador = Callable[[str], list[str]]
"""`pasta` -> nomes dos arquivos nela."""
Baixador = Callable[[str, str], bytes]
"""`(pasta, nome)` -> bytes do arquivo (só na memória)."""


@dataclass
class _Estabelecimento:
    """O que se soma de um estabelecimento no mês, enquanto os arquivos passam."""

    uf: str
    documentos: Counter[str] = field(default_factory=Counter)
    mantenedoras: Counter[str] = field(default_factory=Counter)
    municipios: Counter[str] = field(default_factory=Counter)
    pessoa_fisica: bool = False
    somas: dict[str, int | Decimal] = field(default_factory=dict)

    def somar(self, coluna: str, valor: int | Decimal) -> None:
        self.somas[coluna] = self.somas.get(coluna, 0) + valor


def nomes_dos_arquivos(
    sistema: Sistema, uf: str, competencia: int, nomes_na_pasta: Iterable[str]
) -> list[str]:
    """Os arquivos da UF e da competência (com as partes, no SIA), em ordem."""
    partes = "[a-z]?" if sistema.aceita_partes else ""
    forma = re.compile(
        rf"{sistema.prefixo}{uf}{competencia % 10000:04d}{partes}\.dbc", re.IGNORECASE
    )
    # `fullmatch`, não `$`: o `$` aceita uma quebra de linha no fim, e o nome vai para o RETR do FTP
    return sorted((n for n in nomes_na_pasta if forma.fullmatch(n)), key=str.lower)


def e_pessoa_fisica(documento: str) -> bool:
    """O documento próprio do estabelecimento é um CPF (com ou sem zeros à esquerda)?

    CNPJ cujo DV confere é empresa, mesmo com a raiz cheia de zeros; só o que não é CNPJ válido e tem os
    DVs de um CPF é tratado como pessoa.
    """
    digitos = documento.strip()
    if len(digitos) == cnpj.TAMANHO and cnpj.dv_confere(digitos):
        return False
    return cnpj.cpf_confere(digitos[-cnpj.TAMANHO_DO_CPF :]) and set(
        digitos[: -cnpj.TAMANHO_DO_CPF]
    ) <= {"0"}


def _inteiro(registro: dict[str, str], coluna: str) -> int:
    texto = registro[coluna] or "0"
    try:
        return int(texto)
    except ValueError as erro:
        raise ValueError(f"SUS: número inválido em {coluna}: {texto!r}") from erro


def _dinheiro(registro: dict[str, str], coluna: str) -> Decimal:
    texto = registro[coluna] or "0"
    try:
        return Decimal(texto).quantize(CENTAVOS)
    except InvalidOperation as erro:
        raise ValueError(f"SUS: valor inválido em {coluna}: {texto!r}") from erro


def _somar_internacao(
    estabelecimento: _Estabelecimento, registro: dict[str, str]
) -> None:
    longa = registro["IDENT"] == LONGA_PERMANENCIA
    estabelecimento.somar("internacoes", 0 if longa else 1)
    estabelecimento.somar("obitos", int(not longa and registro["MORTE"] == OBITO))
    estabelecimento.somar("valor_total", _dinheiro(registro, "VAL_TOT"))
    estabelecimento.somar("valor_uti", _dinheiro(registro, "VAL_UTI"))
    estabelecimento.somar("dias_permanencia", _inteiro(registro, "DIAS_PERM"))


def _somar_procedimento(
    estabelecimento: _Estabelecimento, registro: dict[str, str]
) -> None:
    estabelecimento.somar("quantidade_apresentada", _inteiro(registro, "PA_QTDPRO"))
    estabelecimento.somar("quantidade_aprovada", _inteiro(registro, "PA_QTDAPR"))
    estabelecimento.somar("valor_apresentado", _dinheiro(registro, "PA_VALPRO"))
    estabelecimento.somar("valor_aprovado", _dinheiro(registro, "PA_VALAPR"))


_SOMAS = {SIH.nome: _somar_internacao, SIA.nome: _somar_procedimento}


def somar_registros(
    sistema: Sistema,
    registros: Iterator[dict[str, str]],
    uf: str,
    acumulado: dict[str, _Estabelecimento],
) -> int:
    """Soma os registros no `acumulado` (um por CNES); devolve quantos registros passaram."""
    somar = _SOMAS[sistema.nome]
    lidos = 0
    for registro in registros:
        lidos += 1
        codigo = registro[sistema.coluna_cnes]
        estabelecimento = acumulado.setdefault(codigo, _Estabelecimento(uf))
        documento = registro[sistema.coluna_documento]
        if documento and e_pessoa_fisica(documento):
            estabelecimento.pessoa_fisica = True
        estabelecimento.documentos[_cnpj_publicavel(documento)] += 1
        estabelecimento.mantenedoras[
            _cnpj_publicavel(registro[sistema.coluna_mantenedora])
        ] += 1
        estabelecimento.municipios[registro[sistema.coluna_municipio]] += 1
        somar(estabelecimento, registro)
    return lidos


def _cnpj_publicavel(documento: str) -> str:
    """O CNPJ só quando o DV confere; o resto vira vazio.

    Um CPF digitado com o DV errado não é reconhecido como pessoa física por `e_pessoa_fisica`, mas
    também não pode sair na coluna `cnpj`: só o que é CNPJ de verdade é publicado.
    """
    valor = cnpj.completo(documento)
    return valor if valor and cnpj.dv_confere(valor) else ""


def _mais_frequente(contagem: Counter[str]) -> str:
    """O valor não vazio mais frequente (empate: o menor), ou vazio."""
    preenchidos = [(-n, valor) for valor, n in contagem.items() if valor]
    return min(preenchidos)[1] if preenchidos else ""


def _suprimir(sistema: Sistema, somas: dict[str, int | Decimal]) -> dict[str, object]:
    """Os números publicáveis da linha, com a supressão da ADR 0081 item 4 já aplicada."""
    if sistema is SIH:
        pequena = somas["internacoes"] < MINIMO_PARA_PUBLICAR
    else:
        pequena = min(somas["quantidade_apresentada"], somas["quantidade_aprovada"]) < (
            MINIMO_PARA_PUBLICAR
        )
    if pequena:
        linha: dict[str, object] = dict.fromkeys(sistema.numeros)
        linha.update(dict.fromkeys(sistema.marcas, True))
        return linha
    linha = {coluna: somas[coluna] for coluna in sistema.numeros}
    linha["suprimida"] = False
    if sistema is SIH:
        poucos_obitos = somas["obitos"] < MINIMO_PARA_OBITOS
        linha["obitos"] = None if poucos_obitos else somas["obitos"]
        linha["obitos_suprimidos"] = poucos_obitos
    return linha


@dataclass
class _Contagem:
    estabelecimentos: int = 0
    suprimidos: int = 0
    fora_pessoa_fisica: int = 0
    fora_sem_cnpj: int = 0


def montar_tabela(
    sistema: Sistema,
    acumulado: dict[str, _Estabelecimento],
    competencia: int,
    disponivel_em: date,
) -> tuple[pd.DataFrame, dict[str, _Contagem]]:
    """A tabela publicável (sem pessoa física, já suprimida) e as contagens por UF."""
    contagens: dict[str, _Contagem] = {}
    linhas: list[dict[str, object]] = []
    for codigo, estabelecimento in sorted(acumulado.items()):
        contagem = contagens.setdefault(estabelecimento.uf, _Contagem())
        documento = _mais_frequente(estabelecimento.documentos)
        mantenedora = _mais_frequente(estabelecimento.mantenedoras)
        if estabelecimento.pessoa_fisica:
            contagem.fora_pessoa_fisica += 1
            continue
        if not documento and not mantenedora:
            contagem.fora_sem_cnpj += 1
            continue
        numeros = _suprimir(sistema, estabelecimento.somas)
        contagem.estabelecimentos += 1
        contagem.suprimidos += bool(numeros["suprimida"])
        linhas.append({
            "competencia": competencia,
            "codigo_cnes": codigo,
            "cnpj": documento,
            "cnpj_mantenedora": mantenedora,
            "codigo_ibge_municipio": _mais_frequente(estabelecimento.municipios),
            "uf": estabelecimento.uf,
            **numeros,
            "disponivel_em": pd.Timestamp(disponivel_em),
        })  # fmt: skip
    return _com_tipos(
        sistema, pd.DataFrame(linhas, columns=list(sistema.colunas_da_tabela))
    ), (contagens)


def _com_tipos(sistema: Sistema, tabela: pd.DataFrame) -> pd.DataFrame:
    """Tipos fixos no disco: contagem inteira com nulo, dinheiro em decimal(18,2), marcas booleanas."""
    tipos: dict[str, object] = {
        "competencia": "int64",
        "disponivel_em": "datetime64[ns]",
    }
    for coluna in sistema.numeros:
        tipos[coluna] = (
            pd.ArrowDtype(TIPO_DO_DINHEIRO) if coluna in DINHEIRO else "Int64"
        )
    for coluna in sistema.marcas:
        tipos[coluna] = "bool"
    for coluna in COLUNAS_DE_IDENTIFICACAO[1:]:
        tipos[coluna] = "str"
    return tabela.astype(tipos).reset_index(drop=True)


def coletar_competencia(
    sistema: Sistema,
    competencia: int,
    coletado_em: date,
    listar: Listador,
    baixar: Baixador,
    ufs: tuple[str, ...] = UFS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A tabela da competência (todas as `ufs`) e a situação de cada UF.

    Nenhuma UF publicada: tabela vazia e situação `vazia` (a fonte ainda não publicou). Só algumas: erro,
    para que a competência não entre pela metade e com a data errada nas UFs que chegarem depois.
    """
    na_pasta = listar(sistema.pasta_no_ftp)
    arquivos = {
        uf: nomes_dos_arquivos(sistema, uf, competencia, na_pasta) for uf in ufs
    }
    faltando = [uf for uf, nomes in arquivos.items() if not nomes]
    if faltando and len(faltando) < len(ufs):
        raise ValueError(
            f"SUS {sistema.nome} {competencia}: UFs ainda sem arquivo: {', '.join(faltando)}"
        )
    acumulado: dict[str, _Estabelecimento] = {}
    lidos: dict[str, tuple[list[str], int]] = {}
    for uf, nomes in arquivos.items():
        hashes: list[str] = []
        registros = 0
        for nome in nomes:
            conteudo = baixar(sistema.pasta_no_ftp, nome)
            hashes.append(hashlib.sha256(conteudo).hexdigest())
            registros += somar_registros(
                sistema, dbc.ler_dbc(conteudo, sistema.colunas), uf, acumulado
            )
            del conteudo  # o arquivo com as linhas dos pacientes não sobrevive à soma
        lidos[uf] = (hashes, registros)
    tabela, contagens = montar_tabela(sistema, acumulado, competencia, coletado_em)
    situacao = pd.DataFrame(
        [
            _situacao_da_uf(
                sistema,
                competencia,
                uf,
                arquivos[uf],
                *lidos[uf],
                contagens.get(uf, _Contagem()),
                coletado_em,
            )
            for uf in ufs
        ],
        columns=list(COLUNAS_DA_SITUACAO),
    )
    return tabela, situacao


def _situacao_da_uf(
    sistema: Sistema,
    competencia: int,
    uf: str,
    nomes: list[str],
    hashes: list[str],
    registros: int,
    contagem: _Contagem,
    coletado_em: date,
) -> dict[str, object]:
    return {
        "competencia": competencia,
        "uf": uf,
        "sistema": sistema.nome,
        "arquivos": ",".join(nomes),
        "sha256": ",".join(hashes),
        "registros": registros,
        "estabelecimentos": contagem.estabelecimentos,
        "suprimidos": contagem.suprimidos,
        "fora_pessoa_fisica": contagem.fora_pessoa_fisica,
        "fora_sem_cnpj": contagem.fora_sem_cnpj,
        "situacao": COMPETENCIA_COM_DADOS if nomes else COMPETENCIA_VAZIA,
        "coletado_em": pd.Timestamp(coletado_em),
    }


def listar_no_ftp(
    pasta: str, abrir: Callable[..., ftplib.FTP] = ftplib.FTP
) -> list[str]:
    """Os nomes dos arquivos da pasta no FTP anônimo do DATASUS."""
    with abrir(SERVIDOR_FTP, timeout=TEMPO_LIMITE_DO_FTP) as ftp:
        ftp.login()
        ftp.cwd(pasta)
        return list(ftp.nlst())


def baixar_do_ftp(
    pasta: str, nome: str, abrir: Callable[..., ftplib.FTP] = ftplib.FTP
) -> bytes:
    """O arquivo inteiro, só na memória. Entra na pasta antes: o FTP recusa RETR com o caminho completo."""
    pedacos: list[bytes] = []
    with abrir(SERVIDOR_FTP, timeout=TEMPO_LIMITE_DO_FTP) as ftp:
        ftp.login()
        ftp.cwd(pasta)
        ftp.retrbinary(f"RETR {nome}", pedacos.append)
    return b"".join(pedacos)
