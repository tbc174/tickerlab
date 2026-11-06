"""Montar o dossiê de crédito de um CNPJ numa data, pela porta que já existe (C-PR02 do Plano Mestre v3.1; N4).

Três fontes, nenhum banco novo:

- **o cadastro da Receita**, pela vista do CNPJ (`src/cadastro_da_receita.py`): identificação e situação. A vista
  guarda só a publicação mais recente, então ela só entra se já era pública no dia; antes disso, lacuna;
- **a rede**, pela porta (`Porta.rede(..., como_era_em=dia)`): a razão social, os vínculos com outras pessoas
  jurídicas (com o grau de confirmação) e as emissões de valores mobiliários. Pessoa física, MEI, empresário
  individual e sanção ficam de fora; a ponta que só ficou pública depois do dia também (sem os dados dela não dá
  para saber se é uma pessoa);
- **as features de crédito** já calculadas pelo chamador (`features_do_emissor`), do mesmo CNPJ e do mesmo dia:
  os fundamentos e as demonstrações usadas. Sem ficha na CVM, o chamador passa `features=None`.

O que falta vira lacuna escrita, com o motivo (o contrato recusa seção vazia sem lacuna). O nome dos sócios
nunca é lido, nem com o portão dos nomes aberto: o dossiê é só de pessoa jurídica.

A rota que o exporia (C-PR05, depois de N4 e N5): `GET /v1/credito/dossies/{cnpj}?em=AAAA-MM-DD`, devolvendo
`como_dict()`.
"""

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pandas as pd

from base import receita_codigos
from base.cnpj import SEPARADORES, formatar
from base.pessoas.sem_cpf import tirar_cpf
from base.porta import Porta, vista_do_cnpj
from base.porta.rede import Rede, views
from base.rede.ids import PREFIXO_DE_PESSOA
from base.rede.ligacoes import SANCIONADA_POR
from src.cadastro_da_receita import CadastroDaReceita, cadastro_do_cnpj
from src.credito import dossie as dc
from src.credito.features import FeaturesDeCredito
from src.rastro import DocumentoUsado, Rastro

VERSAO = "dossie_credito 1"
FONTE_DA_RECEITA = "rfb-cnpj"  # o id da coleta (`src/busca_por_cnpj.py`)
# fontes que são documento ou cadastro oficial (FRE, FCA, carteira da CVM, IF.data, série da empresa, Receita)
FONTES_OFICIAIS = frozenset(
    {"cvm-fre", "cvm-fca", "cvm-cda", "bcb-ifdata", "empresa_serie", FONTE_DA_RECEITA}
)
SEPARADOR_DE_FONTES = ","
EMITE = "emite"
CONFERIDO_PELA_TABELA = "tabela"
TAMANHO_DO_HASH = 12  # o começo do sha256 do arquivo de origem, para achar o arquivo no registro de coletas

CADASTRO = "cadastro da Receita Federal"
RAZAO_SOCIAL = "razão social"
LIGACOES = "ligações com outras pessoas jurídicas"
EMISSOES = "emissões de valores mobiliários"
DEMONSTRACOES = "demonstrações financeiras"
DOCUMENTOS = "documentos usados"

# o que a base não vê ou não mostra, escrito em todo dossiê (seção, assunto, tipo, motivo)
LACUNAS_FIXAS: tuple[tuple[dc.Secao, str, dc.TipoDeLacuna, str], ...] = (
    (
        "identificacao",
        "endereço completo, telefone e e-mail",
        dc.BLOQUEADA,
        "O dossiê mostra só município e UF: endereço e contatos podem ser de uma pessoa.",
    ),
    (
        "situacao",
        "motivo da situação cadastral e situação especial",
        dc.BLOQUEADA,
        "A vista do CNPJ não publica estes campos.",
    ),
    (
        "situacao",
        "sanções",
        dc.BLOQUEADA,
        "As sanções do governo estão na base, mas só aparecem depois do parecer sobre como mostrá-las.",
    ),
    (
        "situacao",
        "dívida ativa com a União (PGFN)",
        dc.BLOQUEADA,
        "A base ainda não mostra a lista da PGFN.",
    ),
    (
        "situacao",
        "processos de insolvência",
        dc.BLOQUEADA,
        "Recuperação judicial e falência entram com os eventos de pessoa jurídica (linha 115 da fila).",
    ),
    (
        "vinculos",
        "nome dos sócios pessoa física",
        dc.BLOQUEADA,
        "O portão dos nomes segue fechado: o dossiê é só de pessoa jurídica.",
    ),
    (
        "vinculos",
        "sócios pessoa jurídica do quadro de sócios da Receita",
        dc.FONTE_INDISPONIVEL,
        "A rede ainda não lê o quadro de sócios da Receita.",
    ),
    (
        "vinculos",
        "cedente e devedor de CRI, CRA e FIDC",
        dc.FONTE_INDISPONIVEL,
        "Nenhuma fonte pública aberta liga o cedente e o devedor à operação.",
    ),
    (
        "fundamentos",
        "dívida bancária por credor",
        dc.NAO_OBSERVAVEL,
        "O SCR do Banco Central não é público por empresa.",
    ),
)

DATA_NO_NOME = re.compile(r"\bde (\d{2}/\d{2}/\d{4})")
VERSAO_NO_NOME = re.compile(r"\bversão (\S+)")


def montar_dossie(
    cnpj: str,
    data: date,
    *,
    porta: Porta | None = None,
    vista: Path | None = None,
    features: FeaturesDeCredito | None = None,
) -> dc.DossieCredito:
    """O dossiê do CNPJ como a base o conhecia em `data`; a fonte que não foi passada vira lacuna."""
    cnpj = SEPARADORES.sub("", cnpj.strip()).upper()
    _conferir_features(features, cnpj, data)
    partes = [
        _do_cadastro(cnpj, data, vista),
        _da_rede(cnpj, data, porta),
        _das_features(features),
    ]
    documentos = tuple(d for parte in partes for d in parte.documentos)
    lacunas = [lacuna for parte in partes for lacuna in parte.lacunas]
    lacunas += [dc.Lacuna(*fixa) for fixa in LACUNAS_FIXAS]
    if not documentos:
        lacunas.append(_lacuna_dos_documentos(vista, features))
    return dc.DossieCredito(
        cnpj=cnpj,
        data_de_referencia=data,
        identificacao=tuple(f for p in partes for f in p.identificacao),
        situacao=tuple(f for p in partes for f in p.situacao),
        documentos=documentos,
        fundamentos=tuple(f for p in partes for f in p.fundamentos),
        vinculos=tuple(v for p in partes for v in p.vinculos),
        operacoes_publicas=tuple(o for p in partes for o in p.operacoes),
        lacunas=tuple(lacunas),
    )


class _Parte:
    """O que uma fonte põe em cada seção do dossiê."""

    def __init__(self) -> None:
        self.identificacao: list[dc.Fato] = []
        self.situacao: list[dc.Fato] = []
        self.documentos: list[dc.Documento] = []
        self.fundamentos: list[dc.Fato] = []
        self.vinculos: list[dc.Vinculo] = []
        self.operacoes: list[dc.Operacao] = []
        self.lacunas: list[dc.Lacuna] = []


def _conferir_features(
    features: FeaturesDeCredito | None, cnpj: str, data: date
) -> None:
    if features is None:
        return
    if features.data_da_analise != data:
        raise ValueError(
            f"as features são do dia {features.data_da_analise}, não do dia do dossiê ({data})"
        )
    if features.cnpj and SEPARADORES.sub("", features.cnpj).upper() != cnpj:
        raise ValueError("as features são de outro CNPJ")


def _lacuna_dos_documentos(
    vista: Path | None, features: FeaturesDeCredito | None
) -> dc.Lacuna:
    if vista is None and features is None:
        return dc.Lacuna(
            "documentos",
            DOCUMENTOS,
            dc.FONTE_INDISPONIVEL,
            "Nenhuma fonte de documentos foi lida.",
        )
    return dc.Lacuna(
        "documentos", DOCUMENTOS, dc.SEM_REGISTRO, "Nenhum documento público até o dia."
    )


# --- o cadastro da Receita ------------------------------------------------------------------------


def _do_cadastro(cnpj: str, data: date, vista: Path | None) -> _Parte:
    parte = _Parte()
    lacuna = _lacuna_do_cadastro(cnpj, data, vista)
    if lacuna is not None:
        parte.lacunas.append(lacuna)
        return parte
    cadastro = cadastro_do_cnpj(cnpj, vista)
    if cadastro is None:
        parte.lacunas.append(
            dc.Lacuna(
                "situacao",
                CADASTRO,
                dc.SEM_REGISTRO,
                "O CNPJ não aparece na publicação da Receita.",
                FONTE_DA_RECEITA,
            )
        )
    else:
        _preencher_do_cadastro(parte, cnpj, cadastro)
    return parte


def _lacuna_do_cadastro(cnpj: str, data: date, vista: Path | None) -> dc.Lacuna | None:
    """A vista que não chegou, ou que é mais nova que o dia (ela guarda só a publicação mais recente)."""
    manifesto = None if vista is None else vista_do_cnpj.manifesto(vista)
    if manifesto is None:
        motivo = "A vista do CNPJ não estava na base."
    elif (publica_em := date.fromisoformat(manifesto["disponivel_em"])) > data:
        motivo = f"A publicação da Receita na base só ficou pública em {publica_em:%d/%m/%Y}."
    else:
        return None
    return dc.Lacuna(
        "situacao", CADASTRO, dc.FONTE_INDISPONIVEL, motivo, FONTE_DA_RECEITA
    )


def _preencher_do_cadastro(
    parte: _Parte, cnpj: str, cadastro: CadastroDaReceita
) -> None:
    mes = pd.Timestamp(cadastro.mes)
    documento = DocumentoUsado(
        f"dados abertos do CNPJ, publicação de {mes:%m/%Y}", cadastro.disponivel_em
    )
    rastro = Rastro.dos_documentos(
        "lido como publicado", VERSAO, FONTE_DA_RECEITA, [documento]
    )

    def fato(
        chave: str, valor: object, aconteceu_em: date | None = None
    ) -> dc.Fato | None:
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return None
        return dc.Fato(chave, valor, rastro, cadastro.disponivel_em, aconteceu_em)  # type: ignore[arg-type]

    estabelecimentos = cadastro.estabelecimentos
    proprio = estabelecimentos[estabelecimentos["cnpj"] == cnpj].iloc[0]
    identificacao = [
        fato("cnpj", formatar(cnpj)),
        fato("matriz_ou_filial", "matriz" if bool(proprio["matriz"]) else "filial"),
        fato("data_inicio_atividade", _texto_do_dia(proprio["data_inicio_atividade"])),
        fato("atividade_principal", receita_codigos.cnae(proprio["cnae_principal"])),
        fato("municipio", _municipio(proprio)),
        fato("estabelecimentos", len(estabelecimentos)),
    ]
    simples = cadastro.simples or {}
    situacao = [
        fato(
            "situacao_cadastral",
            receita_codigos.situacao_cadastral(proprio["situacao_cadastral"]),
            _dia(proprio["data_situacao_cadastral"]),
        ),
        fato("optante_simples", bool(simples.get("optante_simples", False))),
        fato("optante_mei", bool(simples.get("optante_mei", False))),
    ]
    parte.identificacao += [f for f in identificacao if f is not None]
    parte.situacao += [f for f in situacao if f is not None]
    parte.documentos.append(
        dc.Documento(
            "cadastro do CNPJ",
            None,
            cadastro.disponivel_em,
            rastro,
            versao=cadastro.mes,
        )
    )


def _municipio(estabelecimento: pd.Series) -> str | None:
    nome = receita_codigos.municipio(estabelecimento["municipio"])
    uf = estabelecimento["uf"]
    if not nome:
        return None
    return f"{nome}/{uf}" if isinstance(uf, str) and uf else nome


# --- a rede ---------------------------------------------------------------------------------------


def _da_rede(cnpj: str, data: date, porta: Porta | None) -> _Parte:
    parte = _Parte()
    if porta is None or "ligacoes" not in views(porta.con):
        _lacunas_sem_a_rede(parte, dc.FONTE_INDISPONIVEL, "A rede não estava na base.")
        return parte
    try:
        rede = porta.rede(cnpj, como_era_em=data)
    except LookupError:
        _lacunas_sem_a_rede(
            parte, dc.SEM_REGISTRO, "A empresa não aparece na rede até o dia."
        )
        return parte
    entidades = rede.entidades.set_index("id_entidade")
    _razao_social(parte, entidades.loc[rede.centro])
    for ligacao in rede.ligacoes.to_dict("records"):
        _ler_ligacao(parte, rede, entidades, ligacao)
    parte.vinculos.sort(key=lambda v: (v.tipo, v.outra_parte.id_entidade, v.publico_em))
    parte.operacoes.sort(key=lambda o: (o.identificador, o.publico_em))
    if not parte.vinculos:
        parte.lacunas.append(
            dc.Lacuna(
                "vinculos",
                LIGACOES,
                dc.SEM_REGISTRO,
                "Nenhuma ligação pública até o dia.",
            )
        )
    if not parte.operacoes:
        parte.lacunas.append(
            dc.Lacuna(
                "operacoes_publicas",
                EMISSOES,
                dc.SEM_REGISTRO,
                "Nenhuma emissão pública até o dia.",
            )
        )
    return parte


def _lacunas_sem_a_rede(parte: _Parte, tipo: dc.TipoDeLacuna, motivo: str) -> None:
    parte.lacunas += [
        _lacuna_da_razao_social(),
        dc.Lacuna("vinculos", LIGACOES, tipo, motivo),
        dc.Lacuna("operacoes_publicas", EMISSOES, tipo, motivo),
    ]


def _lacuna_da_razao_social() -> dc.Lacuna:
    # a razão social vem da rede: a base ainda não lê o arquivo de empresas da Receita
    return dc.Lacuna(
        "identificacao",
        RAZAO_SOCIAL,
        dc.FONTE_INDISPONIVEL,
        "Fora da rede societária: a base ainda não lê a razão social do cadastro da Receita.",
        FONTE_DA_RECEITA,
    )


def _e_pessoa(id_entidade: str, entidade: pd.Series | None) -> bool:
    """Pessoa física, MEI, empresário individual, ou entidade sem dados no dia (não dá para saber)."""
    if (
        id_entidade.startswith(PREFIXO_DE_PESSOA)
        or entidade is None
        or pd.isna(entidade.get("tipo"))
    ):
        return True
    return bool(
        _ou_falso(entidade.get("mei")) or _ou_falso(entidade.get("trata_como_pessoa"))
    )


def _razao_social(parte: _Parte, centro: pd.Series) -> None:
    if pd.isna(
        centro.get("tipo")
    ):  # o cadastro dela na rede só ficou público depois do dia
        parte.lacunas.append(_lacuna_da_razao_social())
        return
    if _e_pessoa(str(centro.name), centro):
        motivo = (
            "A razão social do MEI e do empresário individual é o nome de uma pessoa."
        )
        parte.lacunas.append(
            dc.Lacuna("identificacao", RAZAO_SOCIAL, dc.BLOQUEADA, motivo)
        )
        return
    publico_em = _dia(centro["publico_em"])
    fonte = str(centro.get("fontes") or "rede")
    documento = DocumentoUsado(f"cadastro da rede societária ({fonte})", publico_em)
    rastro = Rastro.dos_documentos("lido como publicado", VERSAO, fonte, [documento])
    parte.identificacao.append(
        dc.Fato("razao_social", tirar_cpf(str(centro["nome"])), rastro, publico_em)
    )  # type: ignore[arg-type]


def _ler_ligacao(
    parte: _Parte, rede: Rede, entidades: pd.DataFrame, ligacao: dict
) -> None:
    if ligacao["tipo"] == SANCIONADA_POR:
        return  # as sanções esperam o parecer (lacuna fixa), nem como contagem
    da_empresa = ligacao["de"] == rede.centro
    outra = ligacao["para"] if da_empresa else ligacao["de"]
    entidade = entidades.loc[outra] if outra in entidades.index else None
    if _e_pessoa(outra, entidade):
        return
    assert entidade is not None
    rastro = _rastro_da_ligacao(ligacao)
    publico_em = _dia(ligacao["publico_em"])
    assert publico_em is not None
    if ligacao["tipo"] == EMITE:
        if da_empresa:
            parte.operacoes.append(
                dc.Operacao(
                    "emissor",
                    str(entidade["tipo"]),
                    _identificador(rede, outra, "isin") or outra,
                    rastro,
                    publico_em,
                )
            )
        return
    parte.vinculos.append(
        dc.Vinculo(
            tipo=ligacao["tipo"],
            sentido=dc.DA_EMPRESA if da_empresa else dc.PARA_A_EMPRESA,
            outra_parte=dc.ParteJuridica(
                outra,
                str(entidade["tipo"]),
                tirar_cpf(_texto(entidade.get("nome"))),
                _identificador(rede, outra, "cnpj"),
            ),
            grau=_grau(ligacao),
            rastro=rastro,
            publico_em=publico_em,
            desde=_dia(ligacao.get("aconteceu_em")),
            participacao=_numero(ligacao.get("participacao")),
        )
    )


def _fontes(ligacao: dict) -> list[str]:
    return [
        f.strip()
        for f in str(ligacao.get("fonte") or "").split(SEPARADOR_DE_FONTES)
        if f.strip()
    ]


def _grau(ligacao: dict) -> dc.GrauDeConfirmacao:
    if ligacao.get("conferido_por") == CONFERIDO_PELA_TABELA:
        return dc.TABELA_CONFERIDA
    fontes = _fontes(ligacao)
    if fontes and all(f in FONTES_OFICIAIS for f in fontes):
        return dc.DOCUMENTO_OFICIAL
    return dc.DECLARADO_POR_TERCEIRO


def _rastro_da_ligacao(ligacao: dict) -> Rastro:
    fonte = SEPARADOR_DE_FONTES.join(_fontes(ligacao)) or "rede"
    sha = _texto(ligacao.get("origem_sha256"))
    nome = f"{fonte}, arquivo {sha[:TAMANHO_DO_HASH]}" if sha else fonte
    documento = DocumentoUsado(nome, _dia(ligacao["publico_em"]))
    return Rastro.dos_documentos("ligação lida da fonte", VERSAO, fonte, [documento])


def _identificador(rede: Rede, id_entidade: str, sistema: str) -> str | None:
    ids = rede.identificadores
    achados = ids[(ids["id_entidade"] == id_entidade) & (ids["sistema"] == sistema)][
        "valor"
    ]
    return str(achados.iloc[0]) if not achados.empty else None


# --- as features ----------------------------------------------------------------------------------


def _das_features(features: FeaturesDeCredito | None) -> _Parte:
    parte = _Parte()
    if features is None:
        parte.lacunas.append(
            dc.Lacuna(
                "fundamentos",
                DEMONSTRACOES,
                dc.NAO_OBSERVAVEL,
                "Sem ficha na CVM: empresa fechada não publica demonstrações financeiras.",
            )
        )
        return parte
    for feature in features.features:
        if feature.valor is None:
            motivo = (
                feature.motivo or "A conta não aparece nas demonstrações até o dia."
            )
            parte.lacunas.append(
                dc.Lacuna("fundamentos", feature.chave, dc.SEM_REGISTRO, motivo)
            )
            continue
        publico_em = feature.disponivel_em or feature.rastro.publicado_em
        assert publico_em is not None, (
            f"{feature.chave}: feature sem a data em que ficou pública"
        )
        parte.fundamentos.append(
            dc.Fato(
                feature.chave,
                feature.valor,
                feature.rastro,
                publico_em,
                periodo=feature.periodo,
            )
        )
    parte.documentos += list(_documentos_das_features(features))
    return parte


def _documentos_das_features(features: FeaturesDeCredito) -> Iterator[dc.Documento]:
    vistos: set[str] = set()
    for feature in features.features:
        for usado in feature.rastro.documentos:
            if usado.nome in vistos or usado.publicado_em is None:
                continue
            vistos.add(usado.nome)
            yield _documento(usado, feature.rastro.fonte_id)


def _documento(usado: DocumentoUsado, fonte_id: str) -> dc.Documento:
    """ "DFP de 31/12/2023, versão 1" vira tipo DFP, referente a 31/12/2023, versão 1."""
    assert usado.publicado_em is not None
    data = DATA_NO_NOME.search(usado.nome)
    versao = VERSAO_NO_NOME.search(usado.nome)
    rastro = Rastro.dos_documentos(
        "documento usado nas features", VERSAO, fonte_id, [usado]
    )
    return dc.Documento(
        tipo=usado.nome.split()[0],
        referente_a=pd.Timestamp(_dia_brasileiro(data.group(1))).date()
        if data
        else None,
        publico_em=usado.publicado_em,
        rastro=rastro,
        versao=versao.group(1).rstrip(",") if versao else "",
        url=usado.url,
    )


# --- tipos simples --------------------------------------------------------------------------------


def _dia_brasileiro(texto: str) -> str:
    dia, mes, ano = texto.split("/")
    return f"{ano}-{mes}-{dia}"


def _dia(valor: object) -> date | None:
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):  # type: ignore[arg-type]
        return None
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _texto_do_dia(valor: object) -> str | None:
    dia = _dia(valor)
    return dia.isoformat() if dia else None


def _numero(valor: object) -> float | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return float(valor)  # type: ignore[arg-type]


def _texto(valor: object) -> str:
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):  # type: ignore[arg-type]
        return ""
    return str(valor)


def _ou_falso(valor: object) -> bool:
    return False if valor is None or pd.isna(valor) else bool(valor)  # type: ignore[arg-type]
