"""A cópia reduzida de `empresa_serie` e de `anatel_acessos` no recorte da API (linha 978, PR B dos setores): o degrau 7, o filtro e a trava.

Todo dado aqui é inventado: CNPJs montados com o dígito certo a partir de raízes de mentira, nenhum nome real.
"""

from pathlib import Path

import duckdb
import pytest

from base import cnpj as cnpj_
from base import recorte_dos_setores as recorte
from base.dicionario import TABELAS
from base.porta.duckdb import ARQUIVOS
from scripts import montar_recorte_da_api as envio
from tests.ajudantes_de_cpf import CPF_DE_TESTE, formatado

RAIZ_PJ, RAIZ_OUTRA, RAIZ_MEI, RAIZ_FORA = (
    "11000001",
    "22000002",
    "55555555",
    "99999999",
)
TABELAS_PJ = ("cnpj_empresas_pj", "cnpj_estabelecimentos_pj")
COM_SETORES = (*TABELAS_PJ, *recorte.SETORES)
SERIE = "empresa_serie/empresa_serie.parquet"
ACESSOS = "setoriais/anatel/acessos.parquet"
# o que as tabelas inteiras trazem a mais que a cópia (nomes de entidade, companhia, prestadora e grupo)
NOMES = ("nome", "companhia", "empresa", "grupo_economico")


def _cnpj(raiz: str) -> str:
    primeiros = raiz + "0001"
    return primeiros + cnpj_.digitos_verificadores(primeiros)


def _parquet(caminho: Path, selecao: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    duckdb.sql(f"COPY ({selecao}) TO '{caminho.as_posix()}' (FORMAT PARQUET)")


def _empresas_pj(base: Path) -> None:
    """PJ e OUTRA têm estabelecimento; a RAIZ_MEI com natureza de empresa não (sai em `tirar_raizes_de_mei`)."""
    _parquet(
        base / "cnpj_empresas_pj" / "00.parquet",
        f"SELECT * FROM (VALUES ('{RAIZ_PJ}', 'A SA', '2054', 'demais'), ('{RAIZ_OUTRA}', 'B SA', '2054', 'demais'), "
        f"('{RAIZ_MEI}', 'FULANO DE MENTIRA', '2062', 'micro')) t(cnpj_basico, razao_social, natureza_juridica, porte)",
    )
    _parquet(
        base / "cnpj_estabelecimentos_pj" / "00.parquet",
        f"SELECT * FROM (VALUES ('{RAIZ_PJ}'), ('{RAIZ_OUTRA}')) t(cnpj_basico)",
    )


def _aspas(valor: str | None) -> str:
    return "NULL::VARCHAR" if valor is None else "'" + valor.replace("'", "''") + "'"


def _linha_da_serie(
    chave: str,
    raiz: str | None,
    companhia: str | None = None,
    nome: str = "ENTIDADE DE MENTIRA",
) -> str:
    """Uma linha com as colunas da tabela de verdade (o contrato) e os nomes que a cópia não leva."""
    valores = {
        "fonte": "'aneel-samp'", "chave": _aspas(chave), "nome": _aspas(nome), "raiz": _aspas(raiz),
        "cnpj_companhia": _aspas(companhia), "companhia": "'COMPANHIA DE MENTIRA SA'", "via": "'propria'",
        "por": "'cnpj'", "participacao": "100.0", "desde": "DATE '2020-01-01'",
        "ultima_referencia": "DATE '2025-12-01'", "ate": "NULL::DATE", "ate_publico_em": "NULL::DATE",
        "vigente": "true", "principal": "true", "tickers": "'MENT3'", "origem_sha256": "'abc'",
        "montado_em": "TIMESTAMP '2026-11-10 04:00:00'", "versao_do_codigo": "'teste'",
    }  # fmt: skip
    assert set(valores) == set(TABELAS["empresa_serie"].colunas)
    return "SELECT " + ", ".join(f"{v} AS {c}" for c, v in valores.items())


def _linha_de_acessos(cnpj: str | None, empresa: str = "PRESTADORA DE MENTIRA") -> str:
    valores = {
        "competencia": "DATE '2025-10-01'", "servico": "'SCM'", "recorte": "'Banda Larga Fixa'",
        "cnpj": _aspas(cnpj), "empresa": _aspas(empresa), "grupo_economico": "'GRUPO DE MENTIRA'",
        "porte_da_prestadora": "'Grande'", "uf": "'SP'", "regiao_pgo": "'1'", "codigo_nacional": "'11'",
        "modalidade_de_cobranca": "'Pós-pago'", "tecnologia": "'Fibra'", "geracao": "''",
        "tipo_de_pessoa": "'Pessoa Jurídica'", "tipo_de_produto": "'Banda larga'",
        "faixa_de_velocidade": "'> 34 Mbps'", "meio_de_acesso": "'Cabo'", "tipo_de_acesso_tv": "''",
        "acessos": "10", "arquivo": "'acessos.csv'", "disponivel_em": "DATE '2025-11-15'",
        "visto_em": "TIMESTAMP '2026-11-10 03:00:00'",
    }  # fmt: skip
    assert set(valores) == set(TABELAS["anatel_acessos"].colunas) | {
        "empresa",
        "grupo_economico",
    }
    return "SELECT " + ", ".join(f"{v} AS {c}" for c, v in valores.items())


def _base_com_os_setores(base: Path) -> None:
    errado = _cnpj(RAIZ_OUTRA)[:-1] + str((int(_cnpj(RAIZ_OUTRA)[-1]) + 1) % 10)
    _empresas_pj(base)
    _parquet(
        base / SERIE,
        " UNION ALL ".join(
            [
                _linha_da_serie(
                    "e1", RAIZ_PJ, _cnpj(RAIZ_OUTRA)
                ),  # entidade e companhia de PJ
                _linha_da_serie("e2", RAIZ_PJ),  # sem companhia ligada: sai
                _linha_da_serie("e3", RAIZ_FORA),  # raiz fora da lista sem pessoa
                _linha_da_serie("e4", None),  # só nome ou sigla: sem documento
                _linha_da_serie("e5", RAIZ_MEI),  # a raiz que a saída tira
                _linha_da_serie(
                    "e6", RAIZ_PJ, _cnpj(RAIZ_FORA)
                ),  # companhia fora da lista
                _linha_da_serie("e7", RAIZ_PJ, errado),  # companhia com dígito errado
                _linha_da_serie(
                    "fulano@exemplo.com", RAIZ_PJ
                ),  # e-mail dentro da chave
                _linha_da_serie(
                    formatado(CPF_DE_TESTE), RAIZ_PJ
                ),  # CPF dentro da chave
                _linha_da_serie(
                    "000" + CPF_DE_TESTE, RAIZ_PJ
                ),  # CPF completado com zeros na chave (a Anatel o põe na coluna de CNPJ)
                _linha_da_serie(
                    errado, RAIZ_PJ
                ),  # chave em forma de CNPJ com dígito errado
            ]
        ),
    )
    _parquet(
        base / ACESSOS,
        " UNION ALL ".join(
            [
                _linha_de_acessos(_cnpj(RAIZ_PJ)),
                _linha_de_acessos(_cnpj(RAIZ_OUTRA)),
                _linha_de_acessos(_cnpj(RAIZ_FORA)),  # fora da lista sem pessoa
                _linha_de_acessos(_cnpj(RAIZ_MEI)),  # a raiz que a saída tira
                _linha_de_acessos(errado),  # dígito errado
                _linha_de_acessos("000" + CPF_DE_TESTE),  # CPF completado com zeros
                _linha_de_acessos(None),  # sem documento
            ]
        ),
    )


def _ler(arquivo: Path, colunas: str = "*") -> list[tuple]:
    return duckdb.sql(f"SELECT {colunas} FROM '{arquivo.as_posix()}'").fetchall()


def _colunas(arquivo: Path) -> list[str]:
    return [
        c[0]
        for c in duckdb.sql(f"DESCRIBE SELECT * FROM '{arquivo.as_posix()}'").fetchall()
    ]


# --- a lista e o degrau ----------------------------------------------------------------------------


def test_as_colunas_que_saem_existem_e_nenhuma_e_de_nome():
    assert (
        set(recorte.COLUNAS)
        == set(recorte.SETORES)
        == {"empresa_serie", "anatel_acessos"}
    )
    for nome, colunas in recorte.COLUNAS.items():
        conhecidas = set(TABELAS[nome].colunas)
        assert set(colunas) <= conhecidas, nome
        assert not set(colunas) & set(recorte.COLUNAS_DE_NOME), nome
        assert not set(colunas) & set(NOMES)
    # a chave do contrato de cada tabela segue na cópia, e a data de cada linha também
    assert set(TABELAS["empresa_serie"].chaves) <= set(recorte.COLUNAS["empresa_serie"])
    assert set(TABELAS["anatel_acessos"].chaves) <= set(
        recorte.COLUNAS["anatel_acessos"]
    )
    for nome, colunas in recorte.COLUNAS.items():
        assert set(TABELAS[nome].datas.values()) <= set(colunas), nome


def test_as_copias_dos_setores_so_vao_pelo_degrau_7():
    """O cron noturno (degrau 6) não as manda: o envio pede o pode da Diretoria com as contagens."""
    for degrau in (1, 2, 3, 4, 5, 6):
        assert not set(recorte.SETORES) & set(envio.tabelas_do_degrau(degrau))
    assert envio.tabelas_do_degrau(7) == (*envio.tabelas_do_degrau(6), *recorte.SETORES)
    assert envio._argumentos(["--degrau", "7"]).degrau == 7
    for nome in recorte.SETORES:
        with pytest.raises(envio.RecorteErro, match="degrau 7"):
            envio.conferir_a_lista((nome,))
    # a tabela inteira de casa continua fora da cópia por arquivo
    assert set(recorte.SETORES) <= set(envio.COM_FILTRO_PROPRIO)
    assert "anatel_acessos" in envio.FICAM_EM_CASA


def test_os_setores_nao_vao_sem_empresas_pj(tmp_path):
    base = tmp_path / "base"
    _base_com_os_setores(base)
    with pytest.raises(envio.RecorteErro, match="junto com cnpj_empresas_pj"):
        envio.montar(base, tmp_path / "saida", recorte.SETORES)


def test_tabela_dos_setores_sem_arquivo_na_base_derruba_o_envio(tmp_path):
    base = tmp_path / "base"
    _base_com_os_setores(base)
    (base / SERIE).unlink()
    with pytest.raises(envio.RecorteErro, match="empresa_serie: sem arquivo na base"):
        envio.montar(base, tmp_path / "saida", COM_SETORES)


# --- o filtro --------------------------------------------------------------------------------------


def test_so_a_entidade_de_pj_sai_sem_nome_nem_linha_sem_documento(tmp_path):
    base, saida = tmp_path / "base", tmp_path / "saida"
    _base_com_os_setores(base)
    resultados = {r.tabela: r for r in envio.montar(base, saida, COM_SETORES)}
    serie, acessos = saida / SERIE, saida / ACESSOS
    # sobram as duas entidades de PJ com companhia de PJ (ou sem companhia): e1 e e2
    assert sorted(_ler(serie, "chave")) == [("e1",), ("e2",)]
    assert resultados["empresa_serie"].linhas_tiradas == 9
    assert sorted(_ler(acessos, "cnpj")) == sorted(
        [(_cnpj(RAIZ_PJ),), (_cnpj(RAIZ_OUTRA),)]
    )
    assert resultados["anatel_acessos"].linhas_tiradas == 5
    assert _colunas(serie) == list(recorte.COLUNAS["empresa_serie"])
    assert _colunas(acessos) == list(recorte.COLUNAS["anatel_acessos"])
    for arquivo in (serie, acessos):
        texto = " ".join(str(v) for linha in _ler(arquivo) for v in linha)
        assert "MENTIRA" not in texto
        assert "@" not in texto
    # só a cópia sai: a tabela inteira e os outros arquivos da pasta ficam
    assert sorted(p.name for p in serie.parent.iterdir()) == ["empresa_serie.parquet"]


def test_o_filtro_nao_mexe_na_tabela_inteira_de_casa(tmp_path):
    base = tmp_path / "base"
    _base_com_os_setores(base)
    antes = {a: (base / a).read_bytes() for a in (SERIE, ACESSOS)}
    envio.montar(base, tmp_path / "saida", COM_SETORES)
    for arquivo, conteudo in antes.items():
        assert (base / arquivo).read_bytes() == conteudo
    assert len(_ler(base / SERIE)) == 11
    assert len(_ler(base / ACESSOS)) == 7


def test_a_copia_dos_setores_mantem_as_linhas_e_os_valores_que_saem(tmp_path):
    base, saida = tmp_path / "base", tmp_path / "saida"
    _base_com_os_setores(base)
    envio.montar(base, saida, COM_SETORES)
    colunas = ", ".join(recorte.COLUNAS["empresa_serie"])
    consulta = f"SELECT {colunas} FROM '{{}}' WHERE chave = 'e1'"
    de_casa = duckdb.sql(consulta.format((base / SERIE).as_posix())).fetchall()
    assert de_casa == duckdb.sql(consulta.format((saida / SERIE).as_posix())).fetchall()


def test_arquivo_gravado_antes_das_colunas_de_fim_da_ligacao_tambem_sai(tmp_path):
    """O arquivo do acervo pode ser de antes de `ate`, `ate_publico_em` e `vigente`: a cópia leva as que há."""
    base, saida = tmp_path / "base", tmp_path / "saida"
    _base_com_os_setores(base)
    origem = base / SERIE
    velho = tmp_path / "velho.parquet"
    duckdb.sql(
        f"COPY (SELECT * EXCLUDE (ate, ate_publico_em, vigente) FROM '{origem.as_posix()}') "
        f"TO '{velho.as_posix()}' (FORMAT PARQUET)"
    )
    velho.replace(origem)
    envio.montar(base, saida, COM_SETORES)
    assert "ate" not in _colunas(saida / SERIE)
    assert _conferir(saida, sorted((saida / "cnpj_empresas_pj").glob("*.parquet"))) == {
        "empresa_serie": 2,
        "anatel_acessos": 2,
    }


# --- a trava ---------------------------------------------------------------------------------------


def _copia_boa(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    base, saida = tmp_path / "base", tmp_path / "saida"
    _base_com_os_setores(base)
    envio.montar(base, saida, COM_SETORES)
    # a lista sem pessoa é a da saída (já sem a raiz de MEI)
    return base, saida, sorted((saida / "cnpj_empresas_pj").glob("*.parquet"))


def _conferir(saida: Path, empresas: list[Path]) -> dict[str, int]:
    con = duckdb.connect()
    return recorte.conferir_setores(
        con,
        {"empresa_serie": [saida / SERIE], "anatel_acessos": [saida / ACESSOS]},
        empresas,
    )


def test_a_trava_aceita_a_copia_certa_e_devolve_so_contagens(tmp_path):
    _, saida, empresas = _copia_boa(tmp_path)
    assert _conferir(saida, empresas) == {"empresa_serie": 2, "anatel_acessos": 2}


def _estragar(arquivo: Path, selecao: str) -> None:
    antigo = arquivo.with_suffix(".velho")
    arquivo.rename(antigo)
    _parquet(
        arquivo, selecao.replace("{origem}", f"read_parquet('{antigo.as_posix()}')")
    )


@pytest.mark.parametrize(
    ("arquivo", "selecao", "mensagem"),
    [
        (
            SERIE,
            "SELECT *, 'FULANO' AS nome FROM {origem}",
            r"coluna\(s\) fora da lista",
        ),
        (
            ACESSOS,
            "SELECT *, 'FULANO' AS empresa FROM {origem}",
            r"coluna\(s\) fora da lista",
        ),
        (SERIE, "SELECT * EXCLUDE (raiz) FROM {origem}", "sem "),
        (
            SERIE,
            f"SELECT * REPLACE ('{RAIZ_FORA}' AS raiz) FROM {{origem}}",
            "raiz fora da lista",
        ),
        (
            SERIE,
            "SELECT * REPLACE (NULL::VARCHAR AS raiz) FROM {origem}",
            "raiz fora da lista",
        ),
        (
            SERIE,
            f"SELECT * REPLACE ('{_cnpj(RAIZ_FORA)}' AS cnpj_companhia) FROM {{origem}}",
            "companhia ligada",
        ),
        (
            SERIE,
            "SELECT * REPLACE ('fulano@exemplo.com' AS chave) FROM {origem}",
            "texto livre",
        ),
        (
            SERIE,
            f"SELECT * REPLACE ('{formatado(CPF_DE_TESTE)}' AS chave) FROM {{origem}}",
            "texto livre",
        ),
        (
            SERIE,
            f"SELECT * REPLACE ('{CPF_DE_TESTE}' AS chave) FROM {{origem}}",
            "CPF",
        ),
        (
            SERIE,
            f"SELECT * REPLACE ('000{CPF_DE_TESTE}' AS chave) FROM {{origem}}",
            "chave em forma de CNPJ que não confere",
        ),
        (
            SERIE,
            "SELECT * REPLACE ('1234567' AS raiz) FROM {origem}",
            "raiz que não tem 8 posições",
        ),
        (
            ACESSOS,
            f"SELECT * REPLACE ('{_cnpj(RAIZ_FORA)}' AS cnpj) FROM {{origem}}",
            "raiz fora da lista",
        ),
        (
            ACESSOS,
            f"SELECT * REPLACE ('000{CPF_DE_TESTE}' AS cnpj) FROM {{origem}}",
            "CNPJ que não confere",
        ),
        (ACESSOS, "SELECT * FROM {origem} WHERE false", "cópia vazia"),
    ],
)
def test_a_trava_derruba_o_envio_com_pessoa_na_saida(
    tmp_path, arquivo, selecao, mensagem
):
    _, saida, empresas = _copia_boa(tmp_path)
    _estragar(saida / arquivo, selecao)
    with pytest.raises(recorte.SetorComPessoa, match=mensagem) as erro:
        _conferir(saida, empresas)
    # a mensagem leva contagens, nunca um valor
    texto = str(erro.value)
    assert CPF_DE_TESTE not in texto
    assert "fulano" not in texto.lower()
    assert RAIZ_FORA not in texto


def test_a_trava_recusa_tabela_que_nao_e_dos_setores(tmp_path):
    _, saida, empresas = _copia_boa(tmp_path)
    with pytest.raises(
        recorte.SetorComPessoa, match="não é uma das tabelas dos setores"
    ):
        recorte.conferir_setores(duckdb.connect(), {"outra": [saida / SERIE]}, empresas)


def test_o_filtro_e_a_trava_recusam_lista_vazia_de_empresas(tmp_path):
    _, saida, _ = _copia_boa(tmp_path)
    with pytest.raises(recorte.SetorComPessoa, match="sem cnpj_empresas_pj"):
        _conferir(saida, [])


def test_filtro_que_deixasse_passar_a_pessoa_derruba_a_montagem(tmp_path, monkeypatch):
    """A trava lê a saída: se o filtro copiasse tudo, nada sairia."""

    def sem_filtro(con, _nome, origem, _empresas, destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{origem.as_posix()}')) TO '{destino.as_posix()}' (FORMAT PARQUET)"
        )
        return 0, 0

    monkeypatch.setattr(recorte, "montar_setor", sem_filtro)
    base = tmp_path / "base"
    _base_com_os_setores(base)
    with pytest.raises(envio.RecorteErro, match="fora da lista"):
        envio.montar(base, tmp_path / "saida", COM_SETORES)


def test_os_arquivos_dos_setores_moram_onde_a_porta_le():
    assert ARQUIVOS["empresa_serie"] == SERIE
    assert ARQUIVOS["anatel_acessos"].startswith("setoriais/anatel/")
