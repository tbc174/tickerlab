"""As cópias reduzidas que a lista de compradores lê na API externa (linha 844): o filtro e a trava.

`controladas_pj` e `fips_registrados` saem só com as colunas listadas, só com raízes da `cnpj_empresas_pj` da
mesma saída e sem gestor, administrador, razão social nem CPF; a trava lê a saída e derruba a montagem.
"""

from pathlib import Path

import duckdb
import pytest

from base import recorte_dos_compradores as reduzidas
from base import vitrine
from base.contrato import catalogo
from base.controladas import cnpj14
from base.dossie import COLUNAS_DE_PESSOA
from tests.ajudantes_de_cpf import CPF_DE_TESTE, cpf_que_tambem_passa_como_cnpj


def _completado(cpf: str) -> str:
    """O valor como o `cnpj14` do FRE o grava: um CPF de 11 dígitos completado com zeros até 14."""
    valor = cnpj14(cpf)
    assert valor is not None
    return valor


# um CPF (inventado, de dígitos que conferem) completado pelo `cnpj14`: o dígito do CNPJ não confere
CPF_COMPLETADO = _completado(CPF_DE_TESTE)
# outro CPF inventado cuja forma completada também passa no dígito do CNPJ (1 em cada ~70 CPFs passa)
CPF_QUE_PASSA = _completado(cpf_que_tambem_passa_como_cnpj())
# raiz da lista, 14 caracteres, dígito verificador que não confere
DV_ERRADO = "11000001000101"
# alvo, FIP e companhia aberta (PJ) e as raízes dos dois CPFs: a lista nunca deveria ter, mas a trava não confia
LISTA = ("11000001", "13000001", "14000001", CPF_COMPLETADO[:8], CPF_QUE_PASSA[:8])
FORA = "99000001"  # raiz que a lista sem pessoa não tem (MEI, EI, fora do retrato)


def _parquet(caminho: Path, selecao: str) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    duckdb.sql(f"COPY ({selecao}) TO '{caminho.as_posix()}' (FORMAT PARQUET)")
    return caminho


def _empresas(pasta: Path) -> list[Path]:
    valores = ", ".join(f"('{r}')" for r in LISTA)
    return [
        _parquet(
            pasta / "empresas.parquet",
            f"SELECT * FROM (VALUES {valores}) t(cnpj_basico)",
        )
    ]


def _controladas(pasta: Path) -> list[Path]:
    """Dois FRE da aberta (o v2 tirou a controlada da lista), uma estrangeira, uma fora da lista e uma companhia
    que a lista não tem; com as colunas de nome do arquivo de verdade."""
    linhas = (
        # companhia, referencia, versao, conhecido_em, cnpj, razao_social, tipo, participacao
        "('14000001000140', DATE '2024-12-31', 1, DATE '2025-05-01', '11000001000152', 'ALVO SA', 'controlada', 60.0), "
        f"('14000001000140', DATE '2024-12-31', 2, DATE '2025-06-01', '{FORA}000101', 'FULANO DE TAL', 'coligada', 20.0), "
        "('14000001000140', DATE '2024-12-31', 2, DATE '2025-06-01', NULL, 'ESTRANGEIRA LTD', 'controlada', 100.0), "
        "('98000001000130', DATE '2024-12-31', 1, DATE '2025-05-01', '11000001000152', 'ALVO SA', 'controlada', 51.0), "
        # um CPF (11 dígitos) cuja raiz coincide com a de uma PJ da lista: não é CNPJ e não sai
        "('14000001000140', DATE '2024-12-31', 1, DATE '2025-05-01', '11000001901', 'FULANO', 'controlada', 5.0), "
        # o mesmo CPF depois do `cnpj14` (14 caracteres, raiz na lista), o que passa no dígito do CNPJ e o dígito
        # errado: nenhum sai
        f"('14000001000140', DATE '2024-12-31', 1, DATE '2025-05-01', '{CPF_COMPLETADO}', 'FULANO', 'controlada', 5.0), "
        f"('14000001000140', DATE '2024-12-31', 1, DATE '2025-05-01', '{CPF_QUE_PASSA}', 'FULANO', 'controlada', 5.0), "
        f"('14000001000140', DATE '2024-12-31', 1, DATE '2025-05-01', '{DV_ERRADO}', 'ALVO SA', 'controlada', 5.0), "
        # a companhia que é um CPF completado não sai nem com a marca
        f"('{CPF_COMPLETADO}', DATE '2024-12-31', 1, DATE '2025-05-01', '11000001000152', 'ALVO SA', 'controlada', 5.0)"
    )
    return [
        _parquet(
            pasta / "controladas" / "2025.parquet",
            "SELECT cnpj_companhia, 'ABERTA SA' AS companhia, referencia, versao, '123' AS id_documento, "
            "conhecido_em, cnpj, razao_social, tipo, participacao, 2025 AS ano_do_arquivo, "
            "'abc' AS origem_sha256, '2025-06-02' AS origem_coletada_em "
            f"FROM (VALUES {linhas}) t(cnpj_companhia, referencia, versao, conhecido_em, cnpj, razao_social, "
            "tipo, participacao)",
        )
    ]


def _registro(pasta: Path) -> list[Path]:
    """FIP da lista com dois gestores (um pessoa física), FIP fora da lista e FIDC da lista."""
    linhas = (
        "('1', '13.000.001/0001-88', 'FIP', '2020-01-01', NULL, 'PJ', '55000001000101', 'GESTORA SA', 'ADM SA'), "
        "('1', '13.000.001/0001-88', 'FIP', '2020-01-01', NULL, 'PF', NULL, NULL, 'ADM SA'), "
        f"('2', '{FORA}000101', 'FIP', '2021-01-01', NULL, 'PJ', '55000001000101', 'GESTORA SA', 'ADM SA'), "
        "('3', '11000001000152', 'FIDC', '2019-01-01', '2023-01-01', 'PJ', '55000001000101', 'GESTORA SA', 'ADM SA'), "
        "('4', '13000001901', 'FIP', '2022-01-01', NULL, 'PJ', '55000001000101', 'GESTORA SA', 'ADM SA'), "
        f"('5', '{CPF_COMPLETADO}', 'FIP', '2022-01-01', NULL, 'PJ', '55000001000101', 'GESTORA SA', 'ADM SA'), "
        f"('6', '{CPF_QUE_PASSA}', 'FIP', '2022-01-01', NULL, 'PJ', '55000001000101', 'GESTORA SA', 'ADM SA'), "
        "('7', '13000001000101', 'FIP', '2022-01-01', NULL, 'PJ', '55000001000101', 'GESTORA SA', 'ADM SA')"
    )
    return [
        _parquet(
            pasta / "fidc" / "cadastro" / "registro_fundo.parquet",
            "SELECT ID_Registro_Fundo, CNPJ_Fundo, Tipo_Fundo, Data_Registro, Data_Cancelamento, "
            "'FUNDO DE MENTIRA' AS Denominacao_Social, Tipo_Pessoa_Gestor, CPF_CNPJ_Gestor, Gestor, "
            "'60000001000101' AS CNPJ_Administrador, Administrador "
            f"FROM (VALUES {linhas}) t(ID_Registro_Fundo, CNPJ_Fundo, Tipo_Fundo, Data_Registro, "
            "Data_Cancelamento, Tipo_Pessoa_Gestor, CPF_CNPJ_Gestor, Gestor, Administrador)",
        )
    ]


def _montar(
    tmp_path: Path,
) -> tuple[duckdb.DuckDBPyConnection, dict[str, Path], list[Path]]:
    con = duckdb.connect()
    empresas = _empresas(tmp_path)
    destinos = {
        nome: tmp_path / "saida" / f"{nome}.parquet" for nome in reduzidas.REDUZIDAS
    }
    reduzidas.montar_controladas_pj(
        con, _controladas(tmp_path), empresas, destinos["controladas_pj"]
    )
    reduzidas.montar_fips_registrados(
        con, _registro(tmp_path), empresas, destinos["fips_registrados"]
    )
    return con, destinos, empresas


def _linhas(arquivo: Path, consulta: str = "SELECT * FROM t") -> list[tuple]:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM '{arquivo.as_posix()}'")
    return con.execute(consulta).fetchall()


def _colunas(arquivo: Path) -> list[str]:
    return [
        c[0]
        for c in duckdb.sql(f"DESCRIBE SELECT * FROM '{arquivo.as_posix()}'").fetchall()
    ]


def test_sai_so_com_as_colunas_listadas(tmp_path):
    _, destinos, _ = _montar(tmp_path)
    for nome, arquivo in destinos.items():
        assert _colunas(arquivo) == list(reduzidas.COLUNAS[nome])
        assert not set(_colunas(arquivo)) & COLUNAS_DE_PESSOA


def test_nenhuma_coluna_de_nome_de_gestor_ou_de_administrador_na_lista():
    for colunas in reduzidas.COLUNAS.values():
        for coluna in colunas:
            assert not any(p in coluna.lower() for p in reduzidas.PEDACOS_PROIBIDOS), (
                coluna
            )


def test_controladas_pj_so_com_raiz_da_lista_e_a_marca_de_cada_documento(tmp_path):
    _, destinos, _ = _montar(tmp_path)
    linhas = _linhas(
        destinos["controladas_pj"],
        "SELECT cnpj_companhia, cnpj, tipo, participacao, versao, publico_em FROM t ORDER BY versao, cnpj NULLS LAST",
    )
    v1, v2 = "2025-05-01", "2025-06-01"
    assert [(c, cn, ti, pa, ve, str(pu)) for c, cn, ti, pa, ve, pu in linhas] == [
        ("14000001000140", "11000001000152", "controlada", 60.0, 1, v1),
        ("14000001000140", None, None, None, 1, v1),  # a marca do documento v1
        (
            "14000001000140",
            None,
            None,
            None,
            2,
            v2,
        ),  # a do v2: a fora da lista e a estrangeira não saem
    ]


def test_o_documento_mais_novo_da_companhia_e_o_mesmo_da_tabela_inteira(tmp_path):
    """Sem a marca, o v2 (que só tinha controladas fora da lista) sumiria e o v1 voltaria a valer."""
    _, destinos, _ = _montar(tmp_path)
    ultimo = "SELECT cnpj_companhia, max(versao) FROM t GROUP BY 1"
    assert _linhas(destinos["controladas_pj"], ultimo) == [("14000001000140", 2)]


def test_fips_registrados_so_fip_da_lista_sem_repetir_o_gestor(tmp_path):
    _, destinos, _ = _montar(tmp_path)
    assert _linhas(destinos["fips_registrados"]) == [
        ("13.000.001/0001-88", "FIP", "2020-01-01", None)
    ]


def test_a_trava_passa_na_saida_montada_e_devolve_as_contagens(tmp_path):
    con, destinos, empresas = _montar(tmp_path)
    assert reduzidas.conferir_reduzidas(con, destinos, empresas) == {
        "controladas_pj": 3,
        "fips_registrados": 1,
    }


def _saida_com(
    tmp_path: Path, nome: str, selecao: str
) -> tuple[duckdb.DuckDBPyConnection, dict[str, Path], list[Path]]:
    con, destinos, empresas = _montar(tmp_path)
    _parquet(destinos[nome], selecao)
    return con, destinos, empresas


CONTROLADA = (
    "SELECT '14000001000140' AS cnpj_companhia, {cnpj} AS cnpj, {tipo} AS tipo, {participacao} AS participacao, "
    "DATE '2024-12-31' AS referencia, 1 AS versao, DATE '2025-05-01' AS publico_em"
)
FIP = (
    "SELECT {cnpj} AS CNPJ_Fundo, {tipo} AS Tipo_Fundo, '2020-01-01' AS Data_Registro, "
    "NULL AS Data_Cancelamento"
)


@pytest.mark.parametrize(
    ("nome", "selecao", "erro"),
    [
        (
            "controladas_pj",
            CONTROLADA.format(
                cnpj=f"'{FORA}000101'", tipo="'controlada'", participacao="10.0"
            ),
            "raiz fora da lista",
        ),
        (
            "controladas_pj",
            CONTROLADA.format(cnpj="NULL", tipo="'controlada'", participacao="100.0"),
            "sem CNPJ",
        ),
        (
            "controladas_pj",
            CONTROLADA.replace("'14000001000140' AS", f"'{FORA}000101' AS").format(
                cnpj="NULL", tipo="NULL", participacao="NULL"
            ),
            "raiz fora da lista",
        ),
        (
            "controladas_pj",
            CONTROLADA.format(
                cnpj="'11000001000152'", tipo="'controlada'", participacao="1.0"
            )
            + ", 'FULANO' AS razao_social",
            r"coluna\(s\) fora da lista",
        ),
        (
            "controladas_pj",
            CONTROLADA.format(
                cnpj="'11000001901'", tipo="'controlada'", participacao="5.0"
            ),
            "sem os 14 caracteres",
        ),
        (
            "fips_registrados",
            FIP.format(cnpj="'13000001901'", tipo="'FIP'"),
            "sem os 14 caracteres",
        ),
        *(
            caso
            for valor in (CPF_COMPLETADO, CPF_QUE_PASSA, DV_ERRADO)
            for caso in (
                (
                    "controladas_pj",
                    CONTROLADA.format(
                        cnpj=f"'{valor}'", tipo="'controlada'", participacao="5.0"
                    ),
                    "CNPJ que não confere",
                ),
                (
                    "fips_registrados",
                    FIP.format(cnpj=f"'{valor}'", tipo="'FIP'"),
                    "CNPJ que não confere",
                ),
            )
        ),
        # a companhia só precisa do dígito do CNPJ (ver test_a_companhia_aberta_com_raiz_de_zeros_fica)
        *(
            (
                "controladas_pj",
                CONTROLADA.replace("'14000001000140' AS", f"'{valor}' AS").format(
                    cnpj="NULL", tipo="NULL", participacao="NULL"
                ),
                "CNPJ que não confere",
            )
            for valor in (CPF_COMPLETADO, DV_ERRADO)
        ),
        (
            "fips_registrados",
            FIP.format(cnpj=f"'{FORA}000101'", tipo="'FIP'"),
            "raiz fora da lista",
        ),
        (
            "fips_registrados",
            FIP.format(cnpj="NULL", tipo="'FIP'"),
            "raiz fora da lista",
        ),
        (
            "fips_registrados",
            FIP.format(cnpj="'13000001000188'", tipo="'FIDC'"),
            "não é FIP",
        ),
        (
            "fips_registrados",
            FIP.format(cnpj="'13000001000188'", tipo="'FIP'") + ", 'FULANA' AS Gestor",
            r"coluna\(s\) fora da lista",
        ),
        (
            "fips_registrados",
            FIP.format(cnpj="'13000001000188'", tipo="'FIP'")
            + ", '12345678901' AS CPF_CNPJ_Gestor",
            r"coluna\(s\) fora da lista",
        ),
    ],
)
def test_a_trava_derruba_a_saida_fora_da_regra(tmp_path, nome, selecao, erro):
    con, destinos, empresas = _saida_com(tmp_path, nome, selecao)
    with pytest.raises(reduzidas.ReduzidaComPessoa, match=erro) as achado:
        reduzidas.conferir_reduzidas(con, destinos, empresas)
    # a mensagem vai ao log e ao aviso do Kuma: só contagens, nunca um CNPJ, um CPF ou um nome
    for valor in (FORA, CPF_COMPLETADO[3:], CPF_QUE_PASSA[3:], "FULAN"):
        assert valor not in str(achado.value)


@pytest.mark.parametrize(
    ("valor", "e_de_empresa"),
    [
        ("11000001000152", True),
        ("11.000.001/0001-52", True),
        ("98000001000130", True),
        (DV_ERRADO, False),
        ("11000001901", False),  # CPF sem completar
        (
            CPF_COMPLETADO,
            False,
        ),  # CPF completado pelo cnpj14: o dígito do CNPJ não confere
        (
            CPF_QUE_PASSA,
            False,
        ),  # passa no dígito do CNPJ, mas o resto é um CPF que confere
        ("00000000000000", False),
        ("", False),
        (None, False),
    ],
)
def test_so_o_cnpj_de_empresa_passa(valor, e_de_empresa):
    assert reduzidas.cnpj_de_empresa(valor) is e_de_empresa
    # a regra da companhia só não tem a dos três zeros
    assert reduzidas.cnpj_que_confere(valor) is (e_de_empresa or valor == CPF_QUE_PASSA)


def test_a_companhia_aberta_com_raiz_de_zeros_fica(tmp_path):
    """A emissora registrada na CVM é sempre PJ: a regra dos três zeros não vale para ela (há companhia aberta de
    verdade com essa cara). A controlada com a mesma cara não sai."""
    assert reduzidas.cnpj_que_confere(CPF_QUE_PASSA)
    companhia = CONTROLADA.replace("'14000001000140' AS", f"'{CPF_QUE_PASSA}' AS")
    con, destinos, empresas = _saida_com(
        tmp_path,
        "controladas_pj",
        companhia.format(
            cnpj="'11000001000152'", tipo="'controlada'", participacao="60.0"
        ),
    )
    assert reduzidas.conferir_reduzidas(con, destinos, empresas)["controladas_pj"] == 1
    origem = tmp_path / "fre_com_zeros" / "controladas.parquet"
    _parquet(
        origem,
        companhia.replace("publico_em", "conhecido_em").format(
            cnpj="'11000001000152'", tipo="'controlada'", participacao="60.0"
        ),
    )
    destino = tmp_path / "fre_com_zeros" / "saida.parquet"
    # a linha da controlada e a marca do documento
    assert reduzidas.montar_controladas_pj(con, [origem], empresas, destino) == 2


@pytest.mark.parametrize("nome", reduzidas.REDUZIDAS)
def test_a_trava_derruba_a_copia_vazia(tmp_path, nome):
    """Cópia vazia trocaria a do VPS por nada: a lista perderia o sinal sem ninguém saber."""
    con, destinos, empresas = _montar(tmp_path)
    vazia = {"controladas_pj": CONTROLADA, "fips_registrados": FIP}[nome].format(
        cnpj="'11000001000152'", tipo="'FIP'", participacao="1.0"
    )
    _parquet(destinos[nome], f"SELECT * FROM ({vazia}) WHERE false")
    with pytest.raises(reduzidas.ReduzidaComPessoa, match=f"{nome}: cópia vazia"):
        reduzidas.conferir_reduzidas(con, destinos, empresas)


def test_a_trava_falha_sem_a_lista_sem_pessoa(tmp_path):
    con, destinos, _ = _montar(tmp_path)
    with pytest.raises(reduzidas.ReduzidaComPessoa, match="cnpj_empresas_pj"):
        reduzidas.conferir_reduzidas(con, destinos, [])


def test_a_montagem_falha_sem_a_lista_sem_pessoa(tmp_path):
    with pytest.raises(reduzidas.ReduzidaComPessoa, match="cnpj_empresas_pj"):
        reduzidas.montar_fips_registrados(
            duckdb.connect(), _registro(tmp_path), [], tmp_path / "f.parquet"
        )


def test_o_site_nao_conta_a_copia_reduzida_como_tabela_nova():
    """A cópia reduzida é o mesmo dado da tabela de onde sai (que o catálogo já mostra): fica fora do site."""
    assert set(reduzidas.REDUZIDAS) == vitrine.COPIAS_REDUZIDAS
    publico = vitrine.catalogo_publico(catalogo())["tabelas"]
    assert not set(reduzidas.REDUZIDAS) & set(publico)
    assert set(reduzidas.ORIGEM.values()) <= set(publico)


def test_a_trava_derruba_a_copia_sem_uma_coluna_da_lista(tmp_path):
    con, destinos, empresas = _saida_com(
        tmp_path,
        "fips_registrados",
        "SELECT '13000001000188' AS CNPJ_Fundo, 'FIP' AS Tipo_Fundo, '2020-01-01' AS Data_Registro",
    )
    with pytest.raises(
        reduzidas.ReduzidaComPessoa, match=r"sem \['Data_Cancelamento'\]"
    ):
        reduzidas.conferir_reduzidas(con, destinos, empresas)


def test_a_trava_so_aceita_as_copias_reduzidas(tmp_path):
    con, destinos, empresas = _montar(tmp_path)
    with pytest.raises(reduzidas.ReduzidaComPessoa, match="não é uma cópia reduzida"):
        reduzidas.conferir_reduzidas(
            con, {**destinos, "controladas": destinos["controladas_pj"]}, empresas
        )
