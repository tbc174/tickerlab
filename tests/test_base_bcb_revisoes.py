"""Revisões do BC no cadastro do IF.data e no SCR.data: a revisão é linha nova da mesma chave e só vale
desde o dia em que foi vista (`visto_em`), como nos valores do IF.data (#554, `base/setoriais/revisoes.py`)."""

import io
import zipfile

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import bcb_ifdata, bcb_scr
from base.parquet import como_no_disco, hash_da_tabela, so_acrescentou
from base.setoriais import revisoes
from tests.test_base_bcb import _ifdata, _scr

CHAVE_DO_CADASTRO = list(bcb_ifdata.CHAVE_DO_CADASTRO)
CHAVE_DO_SCR = [*bcb_scr.COLUNAS_DE_TEXTO, "ocorrencia"]
DIA1, DIA2 = pd.Timestamp("2026-10-10"), pd.Timestamp("2026-11-20")


def _cadastro_revisado() -> tuple[pd.DataFrame, pd.DataFrame]:
    antes = bcb_ifdata.ler_cadastro(_ifdata("cadastro_202506.json"))
    depois = antes.copy()
    depois.loc[0, "instituicao"] = "NOME REVISADO"
    return antes, depois


def test_cadastro_revisado_vira_linha_nova_que_vale_so_desde_o_dia_visto():
    antes, depois = _cadastro_revisado()
    tabela = bcb_ifdata.cadastro_com_revisoes([(DIA1, antes), (DIA2, depois)])
    codigo = antes.loc[0, "cod_inst"]
    da_instituicao = tabela[tabela["cod_inst"] == codigo].sort_values("visto_em")
    assert da_instituicao["instituicao"].tolist() == [
        antes.loc[0, "instituicao"],
        "NOME REVISADO",
    ]
    prazo = bcb_ifdata.disponivel_em(antes).iloc[0]
    assert da_instituicao["disponivel_em"].tolist() == [prazo, max(prazo, DIA2)]
    # as outras instituições não mudaram: uma linha só
    assert len(tabela) == len(antes) + 1


def test_cadastro_como_era_antes_da_revisao_devolve_o_nome_antigo():
    antes, depois = _cadastro_revisado()
    tabela = bcb_ifdata.cadastro_com_revisoes([(DIA1, antes), (DIA2, depois)])
    dia_da_revisao = tabela["disponivel_em"].max()
    na_vespera = revisoes.como_era_em(
        tabela, dia_da_revisao - pd.Timedelta(days=1), CHAVE_DO_CADASTRO
    )
    assert "NOME REVISADO" not in set(na_vespera["instituicao"])
    no_dia = revisoes.como_era_em(tabela, dia_da_revisao, CHAVE_DO_CADASTRO)
    assert "NOME REVISADO" in set(no_dia["instituicao"])


def test_cadastro_mais_novo_deixa_uma_linha_por_instituicao():
    antes, depois = _cadastro_revisado()
    tabela = bcb_ifdata.cadastro_com_revisoes([(DIA1, antes), (DIA2, depois)])
    atual = bcb_ifdata.cadastro_mais_novo(tabela)
    assert not atual.duplicated(CHAVE_DO_CADASTRO).any()
    assert len(atual) == len(antes)
    assert "NOME REVISADO" in set(atual["instituicao"])


def test_cadastro_mais_novo_aceita_tabela_sem_revisoes():
    sem = bcb_ifdata.ler_cadastro(_ifdata("cadastro_202506.json"))
    assert len(bcb_ifdata.cadastro_mais_novo(sem)) == len(sem)


def test_cadastro_sem_o_dia_da_coleta_vale_desde_o_prazo():
    antes, _ = _cadastro_revisado()
    tabela = bcb_ifdata.cadastro_com_revisoes([(pd.NaT, antes)])
    assert tabela["visto_em"].isna().all()
    assert (tabela["disponivel_em"] == bcb_ifdata.disponivel_em(tabela)).all()


def _scr_revisado() -> tuple[pd.DataFrame, pd.DataFrame]:
    antes = bcb_scr.ler_ano(_scr("scrdata_2012.zip"))
    depois = antes.copy()
    depois.loc[0, "carteira_ativa"] = antes.loc[0, "carteira_ativa"] + 1.0
    return antes, depois


def test_scr_revisado_vira_linha_nova_que_vale_so_desde_o_dia_visto():
    antes, depois = _scr_revisado()
    tabela = bcb_scr.ano_com_revisoes([(DIA1, antes), (DIA2, depois)])
    assert len(tabela) == len(antes) + 1
    (nova,) = tabela[tabela["visto_em"] == DIA2].to_dict("records")
    velha = tabela[tabela["visto_em"] == DIA1].iloc[0]
    assert nova["carteira_ativa"] == antes.loc[0, "carteira_ativa"] + 1.0
    assert nova["disponivel_em"] == max(velha["disponivel_em"], DIA2) > DIA1


def test_scr_linhas_iguais_da_mesma_chave_continuam_todas():
    """O BC publica mais de uma linha por chave (a amostra tem 6 pares iguais) e a base soma todas."""
    antes, _ = _scr_revisado()
    assert antes.duplicated(list(bcb_scr.COLUNAS_DE_TEXTO)).any()
    tabela = bcb_scr.ano_com_revisoes([(DIA1, antes), (DIA2, antes.copy())])
    assert len(tabela) == len(antes)


def test_scr_igual_na_coleta_seguinte_nao_vira_linha_nova():
    antes, _ = _scr_revisado()
    tabela = bcb_scr.ano_com_revisoes([(DIA1, antes), (DIA2, antes.copy())])
    assert len(tabela) == len(antes)


@settings(deadline=None, max_examples=20)
@given(st.integers(0, 60), st.floats(1, 1e6))
def test_scr_cortar_o_futuro_nao_muda_o_passado(dias_ate_a_revisao, acrescimo):
    """Princípio do projeto: a foto de um dia anterior à revisão é a mesma com ou sem a revisão."""
    antes = _SCR_BASE
    depois = antes.copy()
    depois.loc[0, "carteira_ativa"] = antes.loc[0, "carteira_ativa"] + acrescimo
    dia_da_revisao = DIA1 + pd.Timedelta(days=200 + dias_ate_a_revisao)
    com = bcb_scr.ano_com_revisoes([(DIA1, antes), (dia_da_revisao, depois)])
    sem = bcb_scr.ano_com_revisoes([(DIA1, antes)])
    vespera = dia_da_revisao - pd.Timedelta(days=1)
    foto_com = revisoes.como_era_em(com, vespera, CHAVE_DO_SCR)
    foto_sem = revisoes.como_era_em(sem, vespera, CHAVE_DO_SCR)
    ordem = ["data_base", *CHAVE_DO_SCR[1:]]
    pd.testing.assert_frame_equal(
        foto_com.sort_values(ordem).reset_index(drop=True)[sem.columns],
        foto_sem.sort_values(ordem).reset_index(drop=True)[sem.columns],
        check_dtype=False,
        check_categorical=False,
    )


# --- o SCR lido uma versão por vez e mês a mês (linha 1076) ---------------------------------------
DIA3, DIA4 = pd.Timestamp("2026-12-15"), pd.Timestamp("2027-01-12")


def _como_era_ate_a_linha_1076(
    coletas: list[tuple[pd.Timestamp, bytes]],
) -> pd.DataFrame:
    """O resultado de antes da linha 1076: todas as versões lidas por `ler_ano` e `juntar_coletas` de uma vez."""
    com_prazo = []
    for dia, conteudo in coletas:
        tabela = bcb_scr.ler_ano(conteudo)
        com_prazo.append(
            (
                dia,
                bcb_scr._com_a_ordem_na_chave(tabela).assign(
                    disponivel_em=bcb_scr.disponivel_em(tabela)
                ),
            )
        )
    juntas = revisoes.juntar_coletas(com_prazo, CHAVE_DO_SCR)
    for coluna in bcb_scr.COLUNAS_DE_TEXTO[1:]:
        juntas[coluna] = juntas[coluna].astype("category")
    return juntas


def _zip(meses: dict[str, str]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        for nome, texto in meses.items():
            arquivo.writestr(nome, texto.encode("utf-8-sig"))
    return saida.getvalue()


def _meses_da_amostra() -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(_scr("scrdata_2012.zip"))) as arquivo:
        return {
            n: arquivo.read(n).decode("utf-8-sig") for n in sorted(arquivo.namelist())
        }


def _com_carteira(texto: str, linha: int, valor: str) -> str:
    """O CSV com o `carteira_ativa` da linha `linha` (1 = a primeira depois do cabeçalho) trocado."""
    linhas = texto.splitlines(keepends=True)
    coluna = linhas[0].split(";").index("carteira_ativa")
    campos = linhas[linha].split(";")
    campos[coluna] = f'"{valor}"'
    linhas[linha] = ";".join(campos)
    return "".join(linhas)


def _quatro_versoes() -> list[tuple[pd.Timestamp, bytes]]:
    """Quatro arquivos do ano, como o ano corrente cresce: só novembro; novembro revisto; novembro de volta ao
    valor da 1ª e dezembro (com um número que muda depois); e dezembro revisto."""
    novembro, dezembro = _meses_da_amostra().values()
    nomes = ("scrdata_201211.csv", "scrdata_201212.csv")
    return [
        (DIA1, _zip({nomes[0]: novembro})),
        (DIA2, _zip({nomes[0]: _com_carteira(novembro, 1, "999999,5")})),
        (DIA3, _zip({nomes[0]: novembro, nomes[1]: dezembro})),
        (
            DIA4,
            _zip(
                {nomes[0]: novembro, nomes[1]: _com_carteira(dezembro, 5, "777777,5")}
            ),
        ),
    ]


@pytest.mark.parametrize("ordem", ["na ordem", "fora de ordem"])
def test_scr_mes_a_mes_da_o_mesmo_de_antes_linha_por_linha(ordem):
    coletas = _quatro_versoes()
    if ordem == "fora de ordem":
        coletas = coletas[::-1]

    mes_a_mes = bcb_scr.ano_com_revisoes_dos_arquivos(
        [(dia, lambda c=conteudo: c) for dia, conteudo in coletas]
    )
    antes = _como_era_ate_a_linha_1076(coletas)

    pd.testing.assert_frame_equal(mes_a_mes, antes, check_categorical=False)
    ordem_do_hash = list(bcb_scr.COLUNAS_DE_TEXTO)
    assert hash_da_tabela(como_no_disco(mes_a_mes), ordem_do_hash) == hash_da_tabela(
        como_no_disco(antes), ordem_do_hash
    )


def test_scr_com_as_tabelas_ja_lidas_da_o_mesmo_que_com_os_arquivos():
    coletas = _quatro_versoes()

    das_tabelas = bcb_scr.ano_com_revisoes(
        [(dia, bcb_scr.ler_ano(conteudo)) for dia, conteudo in coletas]
    )
    dos_arquivos = bcb_scr.ano_com_revisoes_dos_arquivos(
        [(dia, lambda c=conteudo: c) for dia, conteudo in coletas]
    )

    pd.testing.assert_frame_equal(das_tabelas, dos_arquivos)


def test_scr_le_um_arquivo_de_cada_vez_e_em_ordem():
    lidos: list[pd.Timestamp] = []

    def leitor(dia: pd.Timestamp, conteudo: bytes):
        def ler() -> bytes:
            lidos.append(dia)
            return conteudo

        return ler

    coletas = _quatro_versoes()[::-1]
    bcb_scr.ano_com_revisoes_dos_arquivos([(d, leitor(d, c)) for d, c in coletas])

    assert lidos == [DIA1, DIA2, DIA3, DIA4]


def test_scr_versao_nova_so_acrescenta_o_que_mudou():
    leitores = [(dia, lambda c=conteudo: c) for dia, conteudo in _quatro_versoes()]

    for quantas in range(1, len(leitores)):
        anterior = bcb_scr.ano_com_revisoes_dos_arquivos(leitores[:quantas])
        nova = bcb_scr.ano_com_revisoes_dos_arquivos(leitores[: quantas + 1])
        assert so_acrescentou(anterior, nova)
    # novembro (240) e a revisão dele (+1); dezembro (240) e a revisão dele (+1); a volta não é linha nova
    assert len(nova) == 240 + 1 + 240 + 1


def test_scr_csv_com_mes_repetido_para_a_leitura():
    novembro = _meses_da_amostra()["scrdata_201211.csv"]
    repetido = _zip({"a.csv": novembro, "b.csv": novembro})

    with pytest.raises(bcb_scr.MesForaDoFormatoError, match="b.csv"):
        bcb_scr.ano_com_revisoes_dos_arquivos([(DIA1, lambda: repetido)])


def test_scr_csv_so_com_cabecalho_nao_conta_como_mes():
    """Como em `ler_ano`, um CSV sem linhas não acrescenta nada (revisão cruzada do PR da linha 1076)."""
    meses = _meses_da_amostra()
    vazio = next(iter(meses.values())).splitlines(keepends=True)[0]
    coletas = [(DIA1, _zip({**meses, "scrdata_201299.csv": vazio}))]

    mes_a_mes = bcb_scr.ano_com_revisoes_dos_arquivos(
        [(DIA1, lambda c=coletas[0][1]: c)]
    )

    pd.testing.assert_frame_equal(
        mes_a_mes, _como_era_ate_a_linha_1076(coletas), check_categorical=False
    )


def test_scr_arquivo_sem_nenhum_mes_para_a_leitura():
    so_cabecalho = next(iter(_meses_da_amostra().values())).splitlines(keepends=True)[0]
    sem_linhas = _zip({"scrdata_201211.csv": so_cabecalho})

    with pytest.raises(bcb_scr.MesForaDoFormatoError, match="nenhum mês"):
        bcb_scr.ano_com_revisoes_dos_arquivos([(DIA1, lambda: sem_linhas)])


@settings(deadline=None, max_examples=20)
@given(st.integers(0, 60), st.integers(1, 10**6))
def test_scr_mes_a_mes_cortar_o_futuro_nao_muda_o_passado(
    dias_ate_a_revisao, acrescimo
):
    """Cada revisão só vale a partir do dia em que foi coletada, também lendo um arquivo por vez."""
    meses = _meses_da_amostra()
    antes = _zip(meses)
    primeiro = next(iter(meses))
    depois = _zip(
        {**meses, primeiro: _com_carteira(meses[primeiro], 1, f"{acrescimo},5")}
    )
    dia_da_revisao = DIA1 + pd.Timedelta(days=200 + dias_ate_a_revisao)
    com = bcb_scr.ano_com_revisoes_dos_arquivos(
        [(DIA1, lambda: antes), (dia_da_revisao, lambda: depois)]
    )
    sem = bcb_scr.ano_com_revisoes_dos_arquivos([(DIA1, lambda: antes)])
    vespera = dia_da_revisao - pd.Timedelta(days=1)
    foto_com = revisoes.como_era_em(com, vespera, CHAVE_DO_SCR)
    foto_sem = revisoes.como_era_em(sem, vespera, CHAVE_DO_SCR)
    ordem = ["data_base", *CHAVE_DO_SCR[1:]]
    pd.testing.assert_frame_equal(
        foto_com.sort_values(ordem).reset_index(drop=True)[sem.columns],
        foto_sem.sort_values(ordem).reset_index(drop=True)[sem.columns],
        check_dtype=False,
        check_categorical=False,
    )
    revistas = com[com["visto_em"] == dia_da_revisao]
    assert len(revistas) == 1
    assert (revistas["disponivel_em"] >= dia_da_revisao).all()


_SCR_BASE = bcb_scr.ler_ano(_scr("scrdata_2012.zip"))
