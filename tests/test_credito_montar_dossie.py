"""Montar o dossiê de crédito de um CNPJ numa data pela porta (C-PR02 do Plano Mestre v3.1; N4, linha 113).

Base de mentira: a rede (como em `tests/test_porta.py`) e a vista do CNPJ de exemplo (`tests/ajudantes_do_cnpj.py`),
com o nome do sócio pessoa física no restrito. Nada de banco novo, nada de internet.
"""

import json
from datetime import date

import pandas as pd
import pytest

from base.pessoas import consulta
from base.porta import Porta
from base.rede import ligacoes as ligacoes_da_rede
from scripts import montar_vista_do_cnpj
from src.credito import dossie as dc
from src.credito import montar_dossie as md
from src.credito.features import Feature, FeaturesDeCredito
from src.rastro import DocumentoUsado, Rastro
from tests import ajudantes_do_cnpj as exemplo

CNPJ = exemplo.cnpj(
    exemplo.LIMITADA
)  # a limitada do exemplo: matriz, filial, sócio PF e sócio PJ
SEM_REDE = exemplo.cnpj(exemplo.MEI)
DIA = date(
    2024, 12, 31
)  # depois da publicação de 09/2024 da Receita (pública em 21/09/2024)
ANTES_DA_RECEITA = date(2024, 6, 30)
PESSOA = "P" + "1" * 20
NOME_DA_PESSOA_NA_REDE = "BELTRANO DA SILVA PESSOA"
SANCIONADORA = "E" + "5" * 20
DFP = DocumentoUsado(
    "DFP de 31/12/2023, versão 1", date(2024, 3, 28), "https://www.rad.cvm.gov.br/x"
)


def _gravar(pasta, caminho: str, tabela: pd.DataFrame) -> None:
    arquivo = pasta / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _ligacoes(*linhas: dict) -> pd.DataFrame:
    padrao = {
        "papel": None,
        "participacao": None,
        "aconteceu_em": "2015-01-01",
        "infracao_em": None,
        "coletado_em": "2026-10-15",
        "ate": None,
        "situacao": None,
        "encerrada_por": None,
        "fonte": "cvm-fre",
        "origem_sha256": "abc123",
        "conferido_por": "regra",
    }
    return ligacoes_da_rede.normalizar(
        pd.DataFrame([{**padrao, **linha} for linha in linhas])
    )


ENTIDADES = {  # id: (tipo, nome, mei, trata_como_pessoa)
    "EA": ("empresa", "Limitada de Exemplo S.A.", False, False),
    "EC1": ("empresa", "Controlada Um Ltda.", False, False),
    "EC2": ("empresa", "Controlada Dois Ltda.", False, False),
    "EAUD": ("auditor", "Auditores Reunidos", False, False),
    "EVM": ("valor_mobiliario", "Debênture LIMI11", False, False),
    "EMEI": ("empresa", "CICLANO DE TAL 12345678000100", True, False),
    "EEI": ("empresa", "FULANO EMPRESARIO INDIVIDUAL", False, True),
    PESSOA: (
        "empresa",
        NOME_DA_PESSOA_NA_REDE,
        False,
        False,
    ),  # sem a marca: o prefixo P basta
    SANCIONADORA: ("empresa", "Órgão que sanciona", False, False),
    "EFUT": ("empresa", "Controlada do Futuro Ltda.", False, False),
}


def _entidades(publicas_em: dict[str, str] | None = None) -> pd.DataFrame:
    publicas_em = publicas_em or {}
    return pd.DataFrame(
        [
            {
                "id_entidade": i,
                "tipo": tipo,
                "nome": nome,
                "natureza_juridica": "2062",
                "natureza_fonte": "fonte",
                "mei": mei,
                "trata_como_pessoa": como_pessoa,
                "fontes": "cvm",
                "publico_em": pd.Timestamp(publicas_em.get(i, "2010-01-01")),
            }
            for i, (tipo, nome, mei, como_pessoa) in ENTIDADES.items()
        ]
    )


def _identificadores() -> pd.DataFrame:
    linhas = [
        ("EA", "cnpj_raiz", exemplo.LIMITADA, None, None, "2010-01-01"),
        ("EC1", "cnpj_raiz", "44555666", None, None, "2010-01-01"),
        ("EC1", "cnpj", "44555666000199", None, None, "2010-01-01"),
        ("EVM", "isin", "BRLIMIDBS001", None, None, "2019-01-01"),
    ]
    tabela = pd.DataFrame(
        linhas,
        columns=["id_entidade", "sistema", "valor", "desde", "ate", "publico_em"],
    )
    for coluna in ("desde", "ate", "publico_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela.assign(regra=1, conferido_por="regra", fontes="cvm")


LIGACOES_DO_PASSADO = (
    {
        "de": "EC1",
        "para": "EA",
        "tipo": "controlada_de",
        "publico_em": "2016-05-31",
        "participacao": 100.0,
    },
    {  # ligada pela tabela conferida à mão
        "de": "EC2",
        "para": "EA",
        "tipo": "coligada_de",
        "publico_em": "2019-05-31",
        "conferido_por": "tabela",
    },
    {
        "de": "EAUD",
        "para": "EA",
        "tipo": "auditada_por",
        "publico_em": "2018-03-01",
        "fonte": "cvm-fca",
    },
    {
        "de": "EA",
        "para": "EVM",
        "tipo": "emite",
        "publico_em": "2019-02-01",
        "fonte": "cvm-cda",
    },
    {"de": PESSOA, "para": "EA", "tipo": "controlada_de", "publico_em": "2017-05-31"},
    {"de": "EA", "para": "EMEI", "tipo": "controlada_de", "publico_em": "2017-05-31"},
    {"de": "EEI", "para": "EA", "tipo": "coligada_de", "publico_em": "2017-05-31"},
    {
        "de": "EA",
        "para": SANCIONADORA,
        "tipo": "sancionada_por",
        "publico_em": "2020-01-10",
        "fonte": "ceis",
    },
    {  # o fim aconteceu antes do dia, mas só ficou público depois: no dia ainda valia
        "de": "EC2",
        "para": "EA",
        "tipo": "controlada_de",
        "publico_em": "2017-05-31",
        "ate": "2024-06-01",
        "ate_publico_em": "2025-04-23",
    },
)
LIGACOES_DO_FUTURO = (
    {"de": "EFUT", "para": "EA", "tipo": "controlada_de", "publico_em": "2025-05-31"},
    {"de": "EC1", "para": "EA", "tipo": "coligada_de", "publico_em": "2025-01-02"},
)


def _gravar_rede(pasta, com_o_futuro: bool) -> None:
    ligacoes = LIGACOES_DO_PASSADO + (LIGACOES_DO_FUTURO if com_o_futuro else ())
    _gravar(pasta, "rede/entidades.parquet", _entidades({"EFUT": "2025-05-31"}))
    _gravar(pasta, "rede/identificadores.parquet", _identificadores())
    _gravar(pasta, "rede/ligacoes.parquet", _ligacoes(*ligacoes))


@pytest.fixture
def rede(tmp_path):
    pasta = tmp_path / "rede_com_o_futuro"
    _gravar_rede(pasta, com_o_futuro=True)
    return pasta


@pytest.fixture
def rede_cortada(tmp_path):
    pasta = tmp_path / "rede_cortada"
    _gravar_rede(pasta, com_o_futuro=False)
    return pasta


@pytest.fixture
def vista(tmp_path):
    base = exemplo.gravar_base(tmp_path / "base_do_cnpj")
    destino = tmp_path / "vista"
    montar_vista_do_cnpj.montar(base, destino)
    exemplo.gravar_restrito(
        destino / "restrito"
    )  # o nome do sócio PF ao lado: nunca pode sair
    return destino


def _features(cnpj: str = CNPJ, dia: date = DIA) -> FeaturesDeCredito:
    rastro = Rastro.dos_documentos(
        "passivo / patrimônio líquido", "credito 1", "cvm", [DFP]
    )
    return FeaturesDeCredito(
        cnpj,
        dia,
        (
            Feature(
                "alavancagem", 1.8, "balanço de 31/12/2023", rastro, DFP.publicado_em
            ),
            Feature(
                "cobertura_de_juros",
                None,
                "12 meses até 31/12/2023",
                rastro,
                motivo="A conta não aparece.",
            ),
        ),
    )


def _montar(
    pasta=None, vista=None, features=None, cnpj=CNPJ, dia=DIA
) -> dc.DossieCredito:
    if pasta is None:
        return md.montar_dossie(cnpj, dia, vista=vista, features=features)
    with Porta(pasta) as porta:
        return md.montar_dossie(cnpj, dia, porta=porta, vista=vista, features=features)


def _json(dossie: dc.DossieCredito) -> str:
    return json.dumps(dossie.como_dict(), ensure_ascii=False)


def _assuntos(dossie: dc.DossieCredito, secao: str) -> dict[str, str]:
    return {lacuna.assunto: lacuna.tipo for lacuna in dossie.lacunas_da(secao)}


def _vinculo(dossie: dc.DossieCredito, tipo: str, outra: str) -> dc.Vinculo:
    return next(
        v
        for v in dossie.vinculos
        if v.tipo == tipo and v.outra_parte.id_entidade == outra
    )


# --- o dossiê completo ----------------------------------------------------------------------------


def test_monta_o_dossie_com_as_tres_fontes(rede, vista):
    dossie = _montar(rede, vista, _features())
    assert dossie.cnpj == CNPJ and dossie.data_de_referencia == DIA
    fatos = {f.chave: f.valor for f in (*dossie.identificacao, *dossie.situacao)}
    assert fatos["razao_social"] == "Limitada de Exemplo S.A."
    assert fatos["situacao_cadastral"] == "Ativa"
    assert fatos["matriz_ou_filial"] == "matriz"
    assert fatos["estabelecimentos"] == 2
    assert {f.chave for f in dossie.fundamentos} == {"alavancagem"}
    assert [d.tipo for d in dossie.documentos] == ["cadastro do CNPJ", "DFP"]
    json.loads(_json(dossie))  # sai em JSON


def test_vinculos_com_grau_e_sentido(rede, vista):
    dossie = _montar(rede, vista)
    controlada = _vinculo(dossie, "controlada_de", "EC1")
    assert (
        controlada.sentido == dc.PARA_A_EMPRESA
    )  # a EC1 é controlada da empresa do dossiê
    assert controlada.grau == dc.DOCUMENTO_OFICIAL
    assert controlada.participacao == 100.0
    assert controlada.outra_parte.cnpj == "44555666000199"
    assert controlada.rastro.fonte_id == "cvm-fre"
    assert _vinculo(dossie, "coligada_de", "EC2").grau == dc.TABELA_CONFERIDA
    assert _vinculo(dossie, "auditada_por", "EAUD").outra_parte.tipo == "auditor"


def test_o_fim_que_so_ficou_publico_depois_nao_aparece(rede, vista):
    """D5: a EC2 deixou de ser controlada em 01/06/2024, mas isso só ficou público em 2025."""
    vinculo = _vinculo(_montar(rede, vista), "controlada_de", "EC2")
    assert vinculo.ate is None and vinculo.ate_publico_em is None


def test_emissao_vai_para_operacoes_publicas(rede, vista):
    dossie = _montar(rede, vista)
    assert [
        (o.papel, o.instrumento, o.identificador) for o in dossie.operacoes_publicas
    ] == [("emissor", "valor_mobiliario", "BRLIMIDBS001")]
    assert all(v.tipo != "emite" for v in dossie.vinculos)


# --- sem olhar o futuro ---------------------------------------------------------------------------


def test_cortar_o_futuro_nao_muda_o_dossie_do_passado(rede, rede_cortada, vista):
    com_o_futuro = _montar(rede, vista, _features())
    sem_o_futuro = _montar(rede_cortada, vista, _features())
    assert com_o_futuro.como_dict() == sem_o_futuro.como_dict()
    assert "EFUT" not in _json(com_o_futuro)


@pytest.mark.parametrize(
    "dia", [date(2016, 12, 31), date(2019, 12, 31), DIA, date(2025, 12, 31)]
)
def test_nada_publicado_depois_do_dia_entra(rede, vista, dia):
    dossie = _montar(
        rede, vista, dia=dia
    )  # o contrato derruba o dossiê que olha o futuro
    assert all(v.publico_em <= dia for v in dossie.vinculos)


def test_vista_mais_nova_que_o_dia_vira_lacuna(rede, vista):
    """A vista guarda só a publicação mais recente da Receita: num dia de antes dela, o cadastro não serve."""
    dossie = _montar(rede, vista, dia=ANTES_DA_RECEITA)
    assert (
        _assuntos(dossie, "situacao")["cadastro da Receita Federal"]
        == dc.FONTE_INDISPONIVEL
    )
    assert all(f.rastro.fonte_id != md.FONTE_DA_RECEITA for f in dossie.identificacao)
    assert {f.chave for f in dossie.identificacao} == {
        "razao_social"
    }  # da rede, que já era pública


def test_features_de_outro_dia_ou_outro_cnpj_nao_entram(rede, vista):
    with pytest.raises(ValueError, match="dia"):
        _montar(rede, vista, _features(dia=date(2025, 3, 31)))
    with pytest.raises(ValueError, match="CNPJ"):
        _montar(rede, vista, _features(cnpj=SEM_REDE))


# --- ausência de evidência vira lacuna ------------------------------------------------------------


def test_sem_nenhuma_fonte_monta_so_com_lacunas():
    dossie = _montar()
    for secao in dc.SECOES:
        assert dossie.lacunas_da(secao), secao
    assert not (dossie.identificacao or dossie.vinculos or dossie.fundamentos)
    assert (
        _assuntos(dossie, "vinculos")["ligações com outras pessoas jurídicas"]
        == dc.FONTE_INDISPONIVEL
    )


def test_conta_que_nao_aparece_vira_lacuna_sem_registro(rede, vista):
    dossie = _montar(rede, vista, _features())
    lacuna = next(
        l for l in dossie.lacunas_da("fundamentos") if l.assunto == "cobertura_de_juros"
    )
    assert lacuna.tipo == dc.SEM_REGISTRO and lacuna.motivo == "A conta não aparece."


def test_empresa_fora_da_rede_tem_lacuna_sem_registro(rede, vista):
    dossie = _montar(rede, vista, cnpj=SEM_REDE)
    assert (
        _assuntos(dossie, "vinculos")["ligações com outras pessoas jurídicas"]
        == dc.SEM_REGISTRO
    )
    assert (
        _assuntos(dossie, "operacoes_publicas")["emissões de valores mobiliários"]
        == dc.SEM_REGISTRO
    )


def test_base_sem_a_tabela_de_ligacoes_e_fonte_indisponivel(tmp_path, vista):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    dossie = _montar(vazia, vista)
    assert (
        _assuntos(dossie, "vinculos")["ligações com outras pessoas jurídicas"]
        == dc.FONTE_INDISPONIVEL
    )


def test_lacunas_fixas_estao_sempre_escritas(rede, vista):
    dossie = _montar(rede, vista, _features())
    assert (
        _assuntos(dossie, "vinculos")["nome dos sócios pessoa física"] == dc.BLOQUEADA
    )
    assert _assuntos(dossie, "situacao")["sanções"] == dc.BLOQUEADA
    assert (
        _assuntos(dossie, "situacao")["dívida ativa com a União (PGFN)"] == dc.BLOQUEADA
    )
    assert (
        _assuntos(dossie, "fundamentos")["dívida bancária por credor"]
        == dc.NAO_OBSERVAVEL
    )


# --- empresa sem ficha na CVM ---------------------------------------------------------------------


def test_empresa_sem_ficha_na_cvm_monta_pelo_cadastro_da_receita(rede, vista):
    dossie = _montar(
        rede, vista, cnpj=SEM_REDE
    )  # o MEI do exemplo: sem rede, sem demonstrações
    fatos = {f.chave: f.valor for f in (*dossie.identificacao, *dossie.situacao)}
    assert fatos["optante_mei"] is True
    assert _assuntos(dossie, "identificacao")["razão social"] == dc.FONTE_INDISPONIVEL
    assert (
        _assuntos(dossie, "fundamentos")["demonstrações financeiras"]
        == dc.NAO_OBSERVAVEL
    )
    assert all(f.rastro.fonte_id == md.FONTE_DA_RECEITA for f in dossie.identificacao)


def test_cnpj_que_a_vista_nao_tem_e_sem_registro(rede, vista):
    dossie = _montar(rede, vista, cnpj=exemplo.cnpj("55666777"))
    assert (
        _assuntos(dossie, "situacao")["cadastro da Receita Federal"] == dc.SEM_REGISTRO
    )


# --- nada de pessoa física ------------------------------------------------------------------------


def test_nenhum_nome_nem_cpf_de_pessoa_fisica(rede, vista, monkeypatch):
    """Nem com o portão dos nomes aberto: o dossiê não lê o nome do sócio, e a rede de PF e de MEI fica fora."""
    monkeypatch.setattr(consulta.portao, "nomes_liberados", lambda *_: True)
    texto = _json(_montar(rede, vista, _features()))
    proibidos = (
        exemplo.NOME_DO_SOCIO,
        NOME_DA_PESSOA_NA_REDE,
        PESSOA,
        "CICLANO",
        "FULANO",
        '"EMEI"',
        '"EEI"',
    )
    for proibido in proibidos:
        assert proibido not in texto
    assert "***123456**" not in texto and not dc.CPF.search(texto)


def test_sancao_nao_aparece_nem_como_contagem(rede, vista):
    texto = _json(_montar(rede, vista))
    assert SANCIONADORA not in texto and "sancionada_por" not in texto


def test_razao_social_de_mei_ou_empresario_individual_fica_bloqueada(tmp_path, vista):
    """A razão social do MEI e do empresário individual é o nome da pessoa (ADR 0077, item 1)."""
    pasta = tmp_path / "rede_do_mei"
    entidades = _entidades().assign(mei=lambda t: t["id_entidade"].isin(["EA", "EMEI"]))
    _gravar(pasta, "rede/entidades.parquet", entidades)
    _gravar(pasta, "rede/identificadores.parquet", _identificadores())
    _gravar(pasta, "rede/ligacoes.parquet", _ligacoes(*LIGACOES_DO_PASSADO[:1]))
    dossie = _montar(pasta, vista)
    assert _assuntos(dossie, "identificacao")["razão social"] == dc.BLOQUEADA
    assert "Limitada de Exemplo" not in _json(dossie)
