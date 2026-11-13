"""Os cinco cadastros em retrato no recorte da API (linha 915): o degrau 5, o filtro e a trava de zero pessoa.

Todo dado aqui é inventado: CNPJs montados com o dígito certo a partir de raízes de mentira, nenhum nome real.
"""

from datetime import date
from pathlib import Path

import duckdb
import pytest

from base import cnpj as cnpj_
from base import recorte_dos_cadastros as recorte
from base.dicionario import TABELAS
from base.dossie import pode_consultar
from base.porta import Porta
from base.porta.duckdb import ARQUIVOS
from scripts import carga_cadastros
from scripts import montar_recorte_da_api as envio
from src.credito import sinais as si

RAIZ_PJ, RAIZ_OUTRA, RAIZ_MEI, RAIZ_FORA = (
    "11000001",
    "22000002",
    "55555555",
    "99999999",
)
TABELAS_PJ = ("cnpj_empresas_pj", "cnpj_estabelecimentos_pj")
COM_CADASTROS = (*TABELAS_PJ, *recorte.CADASTROS)
CONTROLE_DE_MENTIRA = (
    "TIMESTAMP '2026-11-10 03:00:00' AS visto_em, DATE '2026-11-10' AS disponivel_em, "
    "'abc' AS origem_sha256, TIMESTAMP '2026-11-10 02:00:00' AS origem_coletada_em, "
    "TIMESTAMP '2026-11-10 04:00:00' AS montado_em, 'teste' AS versao_do_codigo"
)
# o que a fonte escreveria em cada coluna de nome ou de texto livre (inventado)
NOMES_DE_MENTIRA = {
    "razao_social": "'EMPRESA DE MENTIRA LTDA'",
    "nome_fantasia": "'MENTIRA'",
    "motivo_do_descredenciamento": "'TEXTO LIVRE DE MENTIRA'",
    "nome": "'FULANO DE MENTIRA'",
    "empregador": "'FULANO DE MENTIRA'",
    "estabelecimento": "'FAZENDA DO FULANO DE MENTIRA'",
    "situacao_do_termo": "'ATIVO'",
}
VALORES_DE_MENTIRA = {
    "modalidade": "'Cooperativa médica'", "uf": "'SP'", "registrada_em": "DATE '2001-01-01'",
    "descredenciada_em": "NULL::DATE", "situacao": "'ativas'", "codigo_do_mercado": "1",
    "autorizada_em": "DATE '2001-01-01'", "ano_da_acao": "'2024'", "cnae": "'0151-2/01'",
    "trabalhadores": "3", "incluida_em": "DATE '2025-10-01'", "lei": "'LEI00000000000000001'",
    "autoridade": "'RA000681'", "categoria": "'GENERAL'", "situacao_do_lei": "'ISSUED'", "conflito": "false",
    "numero_do_termo": "'123456'", "cancelado": "'N'", "codigo_do_municipio": "3550308",
    "desembargado": "'N'", "numero_do_auto": "'654321-E'", "area_embargada_ha": "1.5",
    "embargada_em": "DATE '2025-01-01'", "desembargada_em": "NULL::DATE",
}  # fmt: skip


def _cnpj(raiz: str) -> str:
    primeiros = raiz + "0001"
    return primeiros + cnpj_.digitos_verificadores(primeiros)


def _parquet(caminho: Path, selecao: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    duckdb.sql(f"COPY ({selecao}) TO '{caminho.as_posix()}' (FORMAT PARQUET)")


def _empresas_pj(base: Path) -> None:
    """PJ e RAIZ_OUTRA têm estabelecimento; o RAIZ_MEI com natureza de empresa não (sai em `tirar_raizes_de_mei`)."""
    _parquet(
        base / "cnpj_empresas_pj" / "00.parquet",
        f"SELECT * FROM (VALUES ('{RAIZ_PJ}', 'A SA', '2054', 'demais'), ('{RAIZ_OUTRA}', 'B SA', '2054', 'demais'), "
        f"('{RAIZ_MEI}', 'FULANO DE MENTIRA', '2062', 'micro')) t(cnpj_basico, razao_social, natureza_juridica, porte)",
    )
    _parquet(
        base / "cnpj_estabelecimentos_pj" / "00.parquet",
        f"SELECT * FROM (VALUES ('{RAIZ_PJ}'), ('{RAIZ_OUTRA}')) t(cnpj_basico)",
    )


def _linha(nome: str, id_na_fonte: str, cnpj: str | None, marca: str) -> str:
    """Uma linha do cadastro com as colunas da tabela de verdade (as do dicionário)."""
    cnpj_sql = "NULL::VARCHAR" if cnpj is None else f"'{cnpj}'"
    raiz = "NULL::VARCHAR" if cnpj is None else f"'{cnpj[:8]}'"
    partes = []
    for coluna in TABELAS[nome].colunas:
        if coluna == "id_na_fonte":
            partes.append(f"'{id_na_fonte}' AS id_na_fonte")
        elif coluna == "cnpj":
            partes.append(f"{cnpj_sql} AS cnpj")
        elif coluna == "cnpj_basico":
            partes.append(f"{raiz} AS cnpj_basico")
        elif coluna == "consta":
            partes.append("true AS consta")
        elif coluna == "trata_como_pessoa":
            partes.append(f"{marca} AS trata_como_pessoa")
        elif coluna in NOMES_DE_MENTIRA:
            partes.append(f"{NOMES_DE_MENTIRA[coluna]} AS {coluna}")
        elif coluna in VALORES_DE_MENTIRA:
            partes.append(f"{VALORES_DE_MENTIRA[coluna]} AS {coluna}")
    return f"SELECT {', '.join(partes)}, {CONTROLE_DE_MENTIRA}"


def _cadastro(base: Path, nome: str, arquivo: str, linhas: list[str]) -> None:
    _parquet(base / nome / f"{arquivo}.parquet", " UNION ALL BY NAME ".join(linhas))


def _base_com_os_cinco(base: Path) -> None:
    """Em cada cadastro: uma RAIZ_PJ boa e, na Lista Suja, todo tipo de linha que não pode sair."""
    _empresas_pj(base)
    errado = _cnpj(RAIZ_OUTRA)[:-1] + str((int(_cnpj(RAIZ_OUTRA)[-1]) + 1) % 10)
    _cadastro(
        base,
        recorte.MTE,
        "empregadores",
        [
            _linha(
                recorte.MTE,
                f"{_cnpj(RAIZ_PJ)}|2024|FAZENDA DO FULANO",
                _cnpj(RAIZ_PJ),
                "false",
            ),
            _linha(recorte.MTE, "a", _cnpj(RAIZ_OUTRA), "true"),  # marcada como pessoa
            _linha(
                recorte.MTE, "b", _cnpj(RAIZ_OUTRA), "NULL::BOOLEAN"
            ),  # sem marca: na dúvida é pessoa
            _linha(
                recorte.MTE, "c", _cnpj(RAIZ_MEI), "false"
            ),  # RAIZ_MEI que a saída tira
            _linha(
                recorte.MTE, "d", _cnpj(RAIZ_FORA), "false"
            ),  # fora da lista sem pessoa
            _linha(recorte.MTE, "e", errado, "false"),  # dígito errado
        ],
    )
    _cadastro(
        base,
        recorte.SUSEP,
        "entidades",
        [
            _linha(recorte.SUSEP, "1", _cnpj(RAIZ_PJ), "false"),
            _linha(recorte.SUSEP, "2", None, "false"),  # sem CNPJ
        ],
    )
    _cadastro(
        base, recorte.ANS, "ativas", [_linha(recorte.ANS, "1", _cnpj(RAIZ_PJ), "false")]
    )
    _cadastro(
        base,
        recorte.ANS,
        "canceladas",
        [_linha(recorte.ANS, "2", _cnpj(RAIZ_OUTRA), "false")],
    )
    _cadastro(
        base,
        recorte.GLEIF,
        "ponte",
        [_linha(recorte.GLEIF, "1", _cnpj(RAIZ_PJ), "false")],
    )
    _cadastro(
        base,
        recorte.IBAMA,
        "termos",
        [
            _linha(recorte.IBAMA, "1", _cnpj(RAIZ_PJ), "false"),
            _linha(recorte.IBAMA, "2", _cnpj(RAIZ_MEI), "true"),
        ],
    )


def _ler(arquivo: Path, colunas: str = "*") -> list[tuple]:
    return duckdb.sql(f"SELECT {colunas} FROM '{arquivo.as_posix()}'").fetchall()


def _colunas(arquivo: Path) -> list[str]:
    return [
        c[0]
        for c in duckdb.sql(f"DESCRIBE SELECT * FROM '{arquivo.as_posix()}'").fetchall()
    ]


# --- a lista e o degrau ----------------------------------------------------------------------------


def test_os_cadastros_sao_os_cinco_do_comando_da_montagem():
    assert set(recorte.CADASTROS) == set(carga_cadastros.MODULOS)


def test_as_colunas_que_saem_existem_e_nenhuma_e_de_nome_ou_texto_livre():
    for nome, colunas in recorte.COLUNAS.items():
        assert set(colunas) <= set(TABELAS[nome].colunas), nome
        for coluna in colunas:
            assert not any(p in coluna for p in recorte.PEDACOS_PROIBIDOS), (
                nome,
                coluna,
            )
        # o que fica de fora é exatamente o de nome, o de texto livre e a situação do termo do IBAMA
        fora = set(TABELAS[nome].colunas) - set(colunas)
        assert fora <= set(NOMES_DE_MENTIRA), (nome, fora)


def test_os_cadastros_so_vao_pelo_degrau_5():
    """O cron (degraus 2 a 4) não os manda: o envio pede o pode da Diretoria com a prova de zero pessoa."""
    for degrau in (1, 2, 3, 4):
        assert not set(recorte.CADASTROS) & set(envio.tabelas_do_degrau(degrau))
    assert envio.tabelas_do_degrau(5) == (
        *envio.tabelas_do_degrau(4),
        *recorte.CADASTROS,
    )
    assert envio._argumentos(["--degrau", "5"]).degrau == 5
    for nome in recorte.CADASTROS:
        assert TABELAS[
            nome
        ].pessoa  # a tabela inteira é de pessoa: só a cópia reduzida sai
        assert not pode_consultar(nome)
        with pytest.raises(envio.RecorteErro, match="degrau 5"):
            envio.conferir_a_lista((nome,))


# --- o filtro --------------------------------------------------------------------------------------


def test_so_a_linha_de_pj_sai_sem_nome_nem_texto_livre(tmp_path):
    base, saida = tmp_path / "base", tmp_path / "saida"
    _base_com_os_cinco(base)
    resultados = {r.tabela: r for r in envio.montar(base, saida, COM_CADASTROS)}
    mte = saida / recorte.MTE / "empregadores.parquet"
    assert _ler(mte, "cnpj") == [(_cnpj(RAIZ_PJ),)]
    assert resultados[recorte.MTE].linhas_tiradas == 5
    assert _ler(saida / recorte.SUSEP / "entidades.parquet", "cnpj") == [
        (_cnpj(RAIZ_PJ),)
    ]
    assert _ler(saida / recorte.IBAMA / "termos.parquet", "cnpj") == [(_cnpj(RAIZ_PJ),)]
    assert _ler(saida / recorte.ANS / "canceladas.parquet", "cnpj") == [
        (_cnpj(RAIZ_OUTRA),)
    ]
    for nome in recorte.CADASTROS:
        for arquivo in (saida / nome).glob("*.parquet"):
            assert _colunas(arquivo) == list(recorte.COLUNAS[nome]), arquivo
            texto = " ".join(str(v) for linha in _ler(arquivo) for v in linha)
            assert "FULANO" not in texto
            assert "MENTIRA" not in texto
    # a chave da Lista Suja (que leva o estabelecimento) sai como impressão digital
    ((chave,),) = _ler(mte, "id_na_fonte")
    assert len(chave) == recorte.TAMANHO_DA_IMPRESSAO
    assert "FAZENDA" not in chave
    # a tabela inteira não sai: nenhum manifesto, nenhum outro arquivo
    assert sorted(p.name for p in (saida / recorte.MTE).iterdir()) == [
        "empregadores.parquet"
    ]


def test_os_cadastros_nao_vao_sem_empresas_pj(tmp_path):
    base = tmp_path / "base"
    _base_com_os_cinco(base)
    with pytest.raises(envio.RecorteErro, match="junto com cnpj_empresas_pj"):
        envio.montar(base, tmp_path / "saida", recorte.CADASTROS)


def test_cadastro_sem_arquivo_na_base_derruba_o_envio(tmp_path):
    base = tmp_path / "base"
    _base_com_os_cinco(base)
    for arquivo in (base / recorte.GLEIF).glob("*"):
        arquivo.unlink()
    with pytest.raises(envio.RecorteErro, match="gleif_ponte: sem arquivo na base"):
        envio.montar(base, tmp_path / "saida", COM_CADASTROS)


def test_cadastro_que_fica_vazio_derruba_o_envio(tmp_path):
    """Sem a Receita na montagem toda linha fica marcada: a cópia vazia trocaria a do VPS por nada."""
    base = tmp_path / "base"
    _base_com_os_cinco(base)
    _cadastro(
        base,
        recorte.GLEIF,
        "ponte",
        [_linha(recorte.GLEIF, "1", _cnpj(RAIZ_PJ), "true")],
    )
    with pytest.raises(envio.RecorteErro, match="gleif_ponte: cópia vazia"):
        envio.montar(base, tmp_path / "saida", COM_CADASTROS)


# --- a trava ---------------------------------------------------------------------------------------


def test_sem_o_filtro_a_trava_derruba_o_envio(tmp_path, monkeypatch):
    """A trava lê a saída: se o filtro deixasse passar a tabela inteira, nada sairia."""

    def sem_filtro(con, _nome, origem, _empresas, destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        con.execute(
            f"COPY (SELECT * FROM '{origem.as_posix()}') TO '{destino.as_posix()}' (FORMAT PARQUET)"
        )
        return 0, 0

    monkeypatch.setattr(recorte, "montar_cadastro", sem_filtro)
    base = tmp_path / "base"
    _base_com_os_cinco(base)
    with pytest.raises(envio.RecorteErro, match="fora da lista"):
        envio.montar(base, tmp_path / "saida", COM_CADASTROS)


def _saida_conferida(tmp_path: Path, nome: str, selecao: str) -> dict[str, int]:
    _empresas_pj(tmp_path / "s")
    empresas = sorted((tmp_path / "s" / "cnpj_empresas_pj").glob("*.parquet"))
    arquivo = tmp_path / "s" / nome / "x.parquet"
    _parquet(arquivo, selecao)
    with duckdb.connect() as con:
        return recorte.conferir_cadastros(con, {nome: [arquivo]}, empresas)


def _gleif(documento: str, **trocas: str) -> str:
    valores = {
        "id_na_fonte": "'1'", "cnpj": f"'{documento}'", "cnpj_basico": f"'{documento[:8]}'", "consta": "true",
        "trata_como_pessoa": "false", "visto_em": "TIMESTAMP '2026-11-10 03:00:00'",
        "disponivel_em": "DATE '2026-11-10'", "origem_sha256": "'abc'",
        "origem_coletada_em": "TIMESTAMP '2026-11-10 02:00:00'", "montado_em": "TIMESTAMP '2026-11-10 04:00:00'",
        "versao_do_codigo": "'teste'", "lei": "'LEI00000000000000001'", "autoridade": "'RA000681'",
        "categoria": "'GENERAL'", "situacao_do_lei": "'ISSUED'", "conflito": "false", **trocas,
    }  # fmt: skip
    return "SELECT " + ", ".join(f"{v} AS {c}" for c, v in valores.items())


def test_a_saida_certa_passa_e_devolve_as_contagens(tmp_path):
    assert _saida_conferida(tmp_path, recorte.GLEIF, _gleif(_cnpj(RAIZ_PJ))) == {
        recorte.GLEIF: 1
    }


@pytest.mark.parametrize(
    ("trocas", "erro"),
    [
        ({"trata_como_pessoa": "true"}, "como pessoa ou sem a marca"),
        ({"trata_como_pessoa": "NULL::BOOLEAN"}, "como pessoa ou sem a marca"),
        ({"cnpj_basico": f"'{RAIZ_OUTRA}'"}, "raiz diferente da do CNPJ"),
        ({"cnpj": "NULL::VARCHAR"}, "CNPJ que não confere"),
        ({"lei": "'123.456.789-09'"}, "cara de CPF"),
        ({"nome": "'FULANO DE MENTIRA'"}, "1 coluna"),
    ],
)
def test_a_trava_pega_cada_coisa_fora_da_regra(tmp_path, trocas, erro):
    with pytest.raises(recorte.CadastroComPessoa, match=erro):
        _saida_conferida(tmp_path, recorte.GLEIF, _gleif(_cnpj(RAIZ_PJ), **trocas))


def test_a_trava_pega_raiz_fora_da_lista(tmp_path):
    with pytest.raises(recorte.CadastroComPessoa, match="raiz fora da lista"):
        _saida_conferida(tmp_path, recorte.GLEIF, _gleif(_cnpj(RAIZ_FORA)))


def test_a_trava_pega_a_chave_da_lista_suja_que_nao_e_impressao_digital(tmp_path):
    base = tmp_path / "base"
    _base_com_os_cinco(base)
    saida = tmp_path / "saida"
    envio.montar(base, saida, COM_CADASTROS)
    arquivo = saida / recorte.MTE / "empregadores.parquet"
    _parquet(
        tmp_path / "trocada.parquet",
        f"SELECT * REPLACE ('{_cnpj(RAIZ_PJ)}|2024|FAZENDA' AS id_na_fonte) FROM '{arquivo.as_posix()}'",
    )
    empresas = sorted((saida / "cnpj_empresas_pj").glob("*.parquet"))
    with (
        duckdb.connect() as con,
        pytest.raises(recorte.CadastroComPessoa, match="impressão digital"),
    ):
        recorte.conferir_cadastros(
            con, {recorte.MTE: [tmp_path / "trocada.parquet"]}, empresas
        )


def test_cpf_inteiro_so_pega_o_valor_que_e_um_cpf_que_confere():
    assert recorte.cpf_inteiro("123.456.789-09")
    assert recorte.cpf_inteiro("12345678909")
    assert not recorte.cpf_inteiro("12345678900")  # dígito errado
    assert not recorte.cpf_inteiro("654321-E")
    assert not recorte.cpf_inteiro(_cnpj(RAIZ_PJ))
    assert not recorte.cpf_inteiro(None)


# --- a API lê a cópia reduzida pelo nome -------------------------------------------------------------


def test_o_sinal_de_credito_le_a_copia_reduzida_no_vps(tmp_path):
    """No VPS a porta acha a cópia no caminho da tabela inteira e o sinal conta só a RAIZ_PJ (o público da Lista Suja
    e do embargo é o fim do mês do retrato: o dia da ficha é em dezembro)."""
    base, saida = tmp_path / "base", tmp_path / "saida"
    _base_com_os_cinco(base)
    envio.montar(base, saida, COM_CADASTROS)
    arquivos = {nome: ARQUIVOS[nome] for nome in (recorte.MTE, recorte.IBAMA)}
    with Porta(saida, arquivos=arquivos, conferidas={}) as porta:
        sinais = {
            f.chave: f
            for f in si.sinais_da_ficha(porta, _cnpj(RAIZ_PJ), date(2026, 12, 15))
        }
    assert sinais["registros_na_lista_suja"].valor == 1
    assert sinais["embargos_vigentes_no_ibama"].valor == 1
