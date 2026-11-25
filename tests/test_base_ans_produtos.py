"""Planos de saúde da ANS (linha 770, item 1; fonte `ans-cobertura-e-produtos`): `ans_produtos`, uma linha por plano
e por versão, ligada ao CNPJ da operadora pelo registro da ANS (ponte `ans_operadoras`), nunca pelo nome.

Os arquivos daqui são de mentira, no formato conferido em 25/11/2026 nos três retratos que o arquivista guardou
(25/10, 01/11 e 15/11)."""

import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import ans_operadoras, ans_produtos
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base import retratos as motor
from base.ancoragem import parquets_sem_manifesto
from base.arquivo.destinos import DESTINOS, TABELA
from base.dicionario import TABELAS
from base.parquet import ler_tabela
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 10, 25)
SEGUNDO_DIA = date(2026, 11, 1)
URL = (
    "https://dadosabertos.ans.gov.br/FTP/PDA/caracteristicas_produtos_saude_suplementar-008/"
    "pda-008-caracteristicas_produtos_saude_suplementar.csv"
)
URL_DOS_MUNICIPIOS = URL.replace(
    "caracteristicas_produtos_saude_suplementar.csv",
    "tabela_auxiliar_de_detalhamento_de_municipios.csv",
)
URL_DAS_ATIVAS = "https://dadosabertos.ans.gov.br/FTP/PDA/operadoras_de_plano_de_saude_ativas/Relatorio_cadop.csv"
CABECALHO = (
    "ID_PLANO;CD_PLANO;NM_PLANO;REGISTRO_OPERADORA;RAZAO_SOCIAL;GR_MODALIDADE;PORTE_OPERADORA;"
    "VIGENCIA_PLANO;CONTRATACAO;GR_CONTRATACAO;SGMT_ASSISTENCIAL;GR_SGMT_ASSISTENCIAL;"
    "LG_ODONTOLOGICO;OBSTETRICIA;COBERTURA;TIPO_FINANCIAMENTO;ABRANGENCIA_COBERTURA;"
    "ID_GEO_COBERTURA;FATOR_MODERADOR;ACOMODACAO_HOSPITALAR;LIVRE_ESCOLHA;SITUACAO_PLANO;"
    "DT_SITUACAO;DT_REGISTRO_PLANO;DT_ATUALIZACAO"
)


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
MEI = _cnpj("44555666")


def _plano(
    id_plano: str,
    registro: str = "1",
    *,
    nome: str = "Plano Exemplo",
    situacao: str = "Ativo",
    odonto: str = "0",
    registrado: str = "2014-03-20",
    atualizado: str = "2026-10-25",
    geo: str = "ABC123",
) -> str:
    """Uma linha do arquivo, na ordem e com as aspas do arquivo real (`;`, texto entre aspas)."""
    return (
        f'{id_plano};"{id_plano}9";"{nome}";"{registro}";"Operadora De Mentira Ltda";"Medicina De Grupo";'
        f'"Grande";"P";"Coletivo por adesão";"Coletivo por adesão";"Ambulatorial + Hospitalar";'
        f'"Ambulatorial + Hospitalar";{odonto};"Com Obstetrícia";"Médico-hospitalar";"Preestabelecido";'
        f'"Municipal";"{geo}";"Ausente";"Individual";"Ausente";"{situacao}";"2019-11-14";'
        f'"{registrado}";"{atualizado}"'
    )


def _arquivo(*linhas: str) -> bytes:
    return "\n".join([CABECALHO, *linhas]).encode("utf-8")


def _retrato(dia: date, nome: str = "r") -> motor.Retrato:
    return motor.Retrato(
        URL,
        hashlib.sha256(f"{nome}{dia}".encode()).hexdigest(),
        None,
        datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC),  # type: ignore[arg-type]
    )


def test_le_o_plano_com_as_colunas_da_base_e_sem_o_nome_da_operadora():
    tabela, contagem = ans_produtos.ler_retrato(
        _arquivo(_plano("10", "000123", odonto="1", registrado=""))
    )
    linha = tabela.iloc[0]
    assert linha["id_na_fonte"] == "10"
    assert linha["codigo_do_plano"] == "109"
    assert linha["registro_da_operadora"] == "000123"
    assert linha["nome_do_plano"] == "Plano Exemplo"
    assert bool(linha["odontologico"])
    assert pd.isna(linha["registrado_em"])
    assert linha["situacao_desde"] == pd.Timestamp("2019-11-14")
    assert "razao_social" not in tabela
    assert (
        "atualizado_em" not in tabela
    )  # é a data do arquivo, igual em todas as linhas
    assert contagem == {"linhas": 1, "sem_id": 0, "id_repetido": 0}


def test_plano_sem_id_sai_e_id_repetido_fica_o_primeiro():
    tabela, contagem = ans_produtos.ler_retrato(
        _arquivo(
            _plano("10", nome="Primeiro"),
            _plano("10", nome="Segundo"),
            _plano(""),
            _plano("11"),
        )
    )
    assert list(tabela["id_na_fonte"]) == ["10", "11"]
    assert tabela["nome_do_plano"].iloc[0] == "Primeiro"
    assert contagem == {"linhas": 4, "sem_id": 1, "id_repetido": 1}


def test_o_primeiro_retrato_vale_desde_o_dia_dele_e_nao_desde_o_registro_do_plano():
    lidos = [
        (
            _retrato(PRIMEIRO_DIA),
            ans_produtos.ler_retrato(_arquivo(_plano("10", registrado="2014-03-20")))[
                0
            ],
        )
    ]
    tabela, pulados = ans_produtos.juntar_retratos(lidos)
    assert pulados == 0
    assert list(tabela["disponivel_em"]) == [pd.Timestamp(PRIMEIRO_DIA)]


def test_so_o_que_mudou_vira_linha_nova_e_a_data_de_atualizacao_do_arquivo_nao_conta():
    primeiro = ans_produtos.ler_retrato(
        _arquivo(
            _plano("10", atualizado="2026-10-25"),
            _plano("11", situacao="Ativo", atualizado="2026-10-25"),
            _plano("12", atualizado="2026-10-25"),
        )
    )[0]
    segundo = ans_produtos.ler_retrato(
        _arquivo(
            _plano("10", atualizado="2026-11-01"),
            _plano("11", situacao="Cancelado", atualizado="2026-11-01"),
        )
    )[0]
    tabela, _ = ans_produtos.juntar_retratos(
        [(_retrato(PRIMEIRO_DIA), primeiro), (_retrato(SEGUNDO_DIA), segundo)]
    )
    novas = tabela[tabela["disponivel_em"] == pd.Timestamp(SEGUNDO_DIA)]
    assert sorted(zip(novas["id_na_fonte"], novas["consta"], strict=True)) == [
        ("11", True),
        ("12", False),
    ]
    assert novas.set_index("id_na_fonte").loc["11", "situacao_do_plano"] == "Cancelado"


def test_cortar_o_futuro_nao_muda_o_passado():
    primeiro = ans_produtos.ler_retrato(_arquivo(_plano("10"), _plano("11")))[0]
    segundo = ans_produtos.ler_retrato(
        _arquivo(_plano("10", situacao="Suspenso"), _plano("11"), _plano("12"))
    )[0]
    completa, _ = ans_produtos.juntar_retratos(
        [(_retrato(PRIMEIRO_DIA), primeiro), (_retrato(SEGUNDO_DIA), segundo)]
    )
    so_o_passado, _ = ans_produtos.juntar_retratos([(_retrato(PRIMEIRO_DIA), primeiro)])
    do_passado = completa[completa["disponivel_em"] <= pd.Timestamp(PRIMEIRO_DIA)]
    colunas = [*ans_produtos.SO_DO_ARQUIVO, "consta", "disponivel_em"]
    pd.testing.assert_frame_equal(
        do_passado[colunas].reset_index(drop=True),
        so_o_passado[colunas].reset_index(drop=True),
    )


def _ponte(*linhas: tuple[str, str, str, bool, bool]) -> pd.DataFrame:
    """A `ans_operadoras` mínima: (registro, CNPJ, disponível desde, consta, é pessoa)."""
    return pd.DataFrame(
        {
            "id_na_fonte": [r for r, *_ in linhas],
            "cnpj": [cnpjs.formatar(c) for _, c, *_ in linhas],
            "cnpj_basico": [c[:8] for _, c, *_ in linhas],
            "disponivel_em": [pd.Timestamp(d) for _, _, d, *_ in linhas],
            "consta": [c for *_, c, _ in linhas],
            "trata_como_pessoa": [p for *_, p in linhas],
        }
    )


def _com_cnpj(tabela: pd.DataFrame, ponte: pd.DataFrame | None):
    return ans_produtos.com_cnpj_da_operadora(tabela, ponte)


def test_o_cnpj_vem_do_registro_da_operadora_sem_zeros_a_esquerda():
    tabela, _ = ans_produtos.ler_retrato(_arquivo(_plano("10", "000123")))
    tabela = tabela.assign(disponivel_em=pd.Timestamp(PRIMEIRO_DIA))
    ligada, contagem = _com_cnpj(
        tabela, _ponte(("123", EMPRESA, "2026-01-01", True, False))
    )
    assert ligada["cnpj"].iloc[0] == cnpjs.formatar(EMPRESA)
    assert ligada["cnpj_basico"].iloc[0] == EMPRESA[:8]
    assert contagem["ligadas"] == 1


def test_ponte_que_so_existe_depois_do_plano_nao_liga_nada():
    tabela, _ = ans_produtos.ler_retrato(_arquivo(_plano("10", "123")))
    tabela = tabela.assign(disponivel_em=pd.Timestamp(PRIMEIRO_DIA))
    ligada, _ = _com_cnpj(tabela, _ponte(("123", EMPRESA, "2026-11-30", True, False)))
    assert ligada["cnpj"].isna().all()


def test_operadora_pessoa_ou_fora_da_fonte_ou_sem_ponte_fica_sem_cnpj():
    tabela, _ = ans_produtos.ler_retrato(_arquivo(_plano("10", "1"), _plano("11", "2")))
    tabela = tabela.assign(disponivel_em=pd.Timestamp(PRIMEIRO_DIA))
    ponte = _ponte(
        ("1", MEI, "2026-01-01", True, True),
        ("2", EMPRESA, "2026-01-01", False, False),
    )
    ligada, _ = _com_cnpj(tabela, ponte)
    assert ligada["cnpj"].isna().all()
    sem_ponte, contagem = _com_cnpj(tabela, None)
    assert sem_ponte["cnpj"].isna().all()
    assert contagem["ponte_vazia"] == 1


def test_ligacao_nunca_e_pelo_nome():
    tabela, _ = ans_produtos.ler_retrato(_arquivo(_plano("10", "999")))
    tabela = tabela.assign(disponivel_em=pd.Timestamp(PRIMEIRO_DIA))
    ponte = _ponte(("1", EMPRESA, "2026-01-01", True, False)).assign(
        razao_social="Operadora De Mentira Ltda"
    )
    ligada, _ = _com_cnpj(tabela, ponte)
    assert ligada["cnpj"].isna().all()


def _coletar(banco, fonte: str, url: str, conteudo: bytes, dia: date) -> None:
    com_registro(fonte, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def _cadop(*linhas: tuple[str, str]) -> bytes:
    cabecalho = "REGISTRO_OPERADORA;CNPJ;RAZAO_SOCIAL;NOME_FANTASIA;MODALIDADE;UF;DATA_REGISTRO_ANS"
    return "\n".join(
        [
            cabecalho,
            *(f"{r};{c};OPERADORA;;Medicina de Grupo;SP;1999-05-20" for r, c in linhas),
        ]
    ).encode("utf-8")


def _montar(modulo, banco, tmp_path, pessoas=frozenset(), refazer=False) -> dict:
    with banco.connect() as conexao:
        return modulo.montar(
            conexao,
            tmp_path / "base",
            AGORA,
            pessoas=set(pessoas),
            refazer=refazer,
            **({"leitor": ler_tabela} if modulo is ans_produtos else {}),
        )


def test_monta_a_tabela_ligada_pela_ponte_marca_pessoa_e_ignora_o_outro_arquivo(
    banco, tmp_path
):
    _coletar(
        banco,
        "ans-operadoras",
        URL_DAS_ATIVAS.replace("operadoras_de_plano_de_saude_ativas", "x"),
        _cadop(("1", EMPRESA)),
        PRIMEIRO_DIA,
    )
    _montar(ans_operadoras, banco, tmp_path)
    _coletar(
        banco,
        "ans-cobertura-e-produtos",
        URL,
        _arquivo(_plano("10", "1"), _plano("11", "7")),
        SEGUNDO_DIA,
    )
    _coletar(
        banco,
        "ans-cobertura-e-produtos",
        URL_DOS_MUNICIPIOS,
        b"X;Y\n1;2\n",
        SEGUNDO_DIA,
    )
    resumo = _montar(ans_produtos, banco, tmp_path, pessoas={MEI[:8]})
    assert set(resumo) == {"planos"}
    tabela = pd.read_parquet(tmp_path / "base/ans_produtos/planos.parquet")
    por_id = tabela.set_index("id_na_fonte")
    assert por_id.loc["10", "cnpj"] == cnpjs.formatar(EMPRESA)
    assert pd.isna(por_id.loc["11", "cnpj"])  # registro 7 não está na ponte
    assert not tabela["trata_como_pessoa"].any()
    assert parquets_sem_manifesto(tmp_path / "base") == []


def test_operadora_pessoa_da_receita_marca_o_plano_como_pessoa(banco, tmp_path):
    _coletar(
        banco,
        "ans-operadoras",
        URL_DAS_ATIVAS.replace("operadoras_de_plano_de_saude_ativas", "x"),
        _cadop(("1", MEI)),
        PRIMEIRO_DIA,
    )
    _montar(ans_operadoras, banco, tmp_path, pessoas={MEI[:8]})
    _coletar(
        banco, "ans-cobertura-e-produtos", URL, _arquivo(_plano("10", "1")), SEGUNDO_DIA
    )
    _montar(ans_produtos, banco, tmp_path, pessoas={MEI[:8]})
    tabela = pd.read_parquet(tmp_path / "base/ans_produtos/planos.parquet")
    assert tabela["cnpj"].isna().all()  # a ponte já esconde a operadora que é pessoa


def test_a_tabela_se_refaz_quando_a_ponte_muda_e_nao_quando_nada_mudou(banco, tmp_path):
    _coletar(
        banco, "ans-cobertura-e-produtos", URL, _arquivo(_plano("10", "1")), SEGUNDO_DIA
    )
    _montar(ans_produtos, banco, tmp_path)  # sem ponte ainda: CNPJ vazio
    assert _montar(ans_produtos, banco, tmp_path) == {"planos": montagem.JA_MONTADO}
    _coletar(
        banco,
        "ans-operadoras",
        URL_DAS_ATIVAS.replace("operadoras_de_plano_de_saude_ativas", "x"),
        _cadop(("1", EMPRESA)),
        date(2026, 10, 1),
    )
    _montar(ans_operadoras, banco, tmp_path)
    resumo = _montar(ans_produtos, banco, tmp_path)
    assert resumo["planos"] != montagem.JA_MONTADO
    tabela = pd.read_parquet(tmp_path / "base/ans_produtos/planos.parquet")
    assert tabela["cnpj"].iloc[0] == cnpjs.formatar(EMPRESA)


def test_tabela_no_dicionario_e_destino_da_fonte():
    assert ans_produtos.TABELA in TABELAS
    assert set(ans_produtos.CADASTROS[0].colunas) <= set(
        TABELAS[ans_produtos.TABELA].colunas
    )
    destino = DESTINOS["ans-cobertura-e-produtos"]
    assert destino.tipo == TABELA
    assert destino.tabelas == ("ans_produtos",)


def test_sem_leitor_da_ponte_o_cnpj_sai_vazio_e_nao_quebra(banco, tmp_path):
    _coletar(
        banco,
        "ans-operadoras",
        URL_DAS_ATIVAS.replace("operadoras_de_plano_de_saude_ativas", "x"),
        _cadop(("1", EMPRESA)),
        date(2026, 10, 1),
    )
    _montar(ans_operadoras, banco, tmp_path)
    _coletar(
        banco,
        "ans-cobertura-e-produtos",
        URL,
        _arquivo(_plano("10", "1")),
        SEGUNDO_DIA,
    )
    with banco.connect() as conexao:
        ans_produtos.montar(conexao, tmp_path / "base", AGORA, pessoas=set())
    tabela = pd.read_parquet(tmp_path / "base/ans_produtos/planos.parquet")
    assert tabela["cnpj"].isna().all()
