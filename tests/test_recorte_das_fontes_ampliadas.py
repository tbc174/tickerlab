"""As quatro fontes ampliadas no recorte da API (linha 978): o degrau 8, o filtro e a trava de zero pessoa.

Anatel (PADOs e produtos homologados), ANP (tancagem) e PAT do MTE: só CNPJ de dígito certo e sem coluna de nome, mas
com linha marcada em `trata_como_pessoa` (EI e MEI) que a porta já esconde. Ao VPS vai só a cópia reduzida, pelo mesmo
filtro e pela mesma trava dos cadastros. Todo dado aqui é inventado: CNPJs montados com o dígito certo a partir de raízes
de mentira, nenhum nome real e nenhum CPF que confere guardado em arquivo (o teste o monta na hora).
"""

from pathlib import Path

import duckdb
import pytest

from base import recorte_dos_cadastros as recorte
from base.dicionario import TABELAS
from scripts import montar_recorte_da_api as envio
from tests.ajudantes_de_cpf import cpf_que_confere, formatado
from tests.test_recorte_dos_cadastros import (
    CONTROLE_DE_MENTIRA,
    RAIZ_FORA,
    RAIZ_MEI,
    RAIZ_OUTRA,
    RAIZ_PJ,
    _cnpj,
    _colunas,
    _empresas_pj,
    _ler,
    _parquet,
)

COM_AMPLIADAS = ("cnpj_empresas_pj", "cnpj_estabelecimentos_pj", *recorte.AMPLIADAS)
COLUNAS_DE_DATA = (
    "data_da_homologacao", "data_do_certificado", "validade_do_certificado", "data_da_posicao", "data_do_cadastro",
)  # fmt: skip
COLUNAS_DE_NUMERO = (
    "multa_aplicada", "tancagem_m3", "trabalhadores_ate_5_salarios", "trabalhadores_acima_de_5_salarios",
    "trabalhadores_atendidos",
)  # fmt: skip
CONTROLE_SOLTO = (
    "visto_em",
    "disponivel_em",
    "origem_sha256",
    "origem_coletada_em",
    "montado_em",
    "versao_do_codigo",
)


def _linha(
    nome: str, id_na_fonte: str, cnpj: str | None, marca: str, **texto: str
) -> str:
    """Uma linha da tabela com as colunas de verdade (as do dicionário); `texto` troca o valor de uma coluna."""
    raiz = "NULL::VARCHAR" if cnpj is None else f"'{cnpj[:8]}'"
    cnpj_sql = "NULL::VARCHAR" if cnpj is None else f"'{cnpj}'"
    partes = []
    for coluna in TABELAS[nome].colunas:
        if coluna in CONTROLE_SOLTO:
            continue
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
        elif coluna in texto:
            partes.append(f"'{texto[coluna]}' AS {coluna}")
        elif coluna in COLUNAS_DE_DATA:
            partes.append(f"DATE '2025-01-01' AS {coluna}")
        elif coluna in COLUNAS_DE_NUMERO:
            partes.append(f"1.5 AS {coluna}")
        else:
            partes.append(f"'valor de mentira' AS {coluna}")
    return f"SELECT {', '.join(partes)}, {CONTROLE_DE_MENTIRA}"


def _tabela(base: Path, nome: str, arquivo: str, linhas: list[str]) -> None:
    _parquet(base / nome / f"{arquivo}.parquet", " UNION ALL BY NAME ".join(linhas))


def _base_com_as_ampliadas(base: Path) -> None:
    """Em cada tabela: uma linha boa e, na maioria, linhas que não podem sair; o PAT tem três arquivos."""
    _empresas_pj(base)
    cpf = formatado(cpf_que_confere("888777666"))
    errado = _cnpj(RAIZ_OUTRA)[:-1] + str((int(_cnpj(RAIZ_OUTRA)[-1]) + 1) % 10)
    pados = recorte.PADOS
    _tabela(
        base,
        pados,
        "pados",
        [
            _linha(pados, "p1", _cnpj(RAIZ_PJ), "false", tema="Tema de mentira"),
            _linha(pados, "p2", _cnpj(RAIZ_OUTRA), "true"),  # marcada como pessoa
            _linha(pados, "p3", _cnpj(RAIZ_FORA), "false"),  # fora da lista sem pessoa
            _linha(
                pados, "p4", _cnpj(RAIZ_MEI), "false"
            ),  # a raiz de MEI que a saída tira
            _linha(pados, "p5", errado, "false"),  # dígito errado
            _linha(
                pados, "p6", _cnpj(RAIZ_PJ), "false", tema=f"autuado: {cpf}"
            ),  # CPF dentro do texto
            _linha(
                pados, "p7", _cnpj(RAIZ_PJ), "NULL::BOOLEAN"
            ),  # sem marca: na dúvida é pessoa
        ],
    )
    homologados = recorte.HOMOLOGADOS
    _tabela(
        base,
        homologados,
        "homologados",
        [
            _linha(
                homologados,
                "h1|PRODUTO DO FULANO",
                _cnpj(RAIZ_PJ),
                "false",
                nome_comercial="PRODUTO DO FULANO",
            ),
            _linha(homologados, "h2", None, "false"),  # sem CNPJ
            _linha(
                homologados, "h3", _cnpj(RAIZ_OUTRA), "false", modelo=f"contato {cpf}"
            ),
        ],
    )
    tancagem = recorte.TANCAGEM
    _tabela(
        base,
        tancagem,
        "tancagem",
        [
            _linha(tancagem, "t1", _cnpj(RAIZ_PJ), "false"),
            _linha(tancagem, "t2", _cnpj(RAIZ_OUTRA), "true"),
        ],
    )
    pat = recorte.PAT
    for arquivo, raiz, marca in (
        ("beneficiarias", RAIZ_PJ, "false"),
        ("facilitadoras", RAIZ_OUTRA, "false"),
    ):
        _tabela(
            base, pat, arquivo, [_linha(pat, f"{_cnpj(raiz)}|1", _cnpj(raiz), marca)]
        )
    _tabela(base, pat, "fornecedoras", [_linha(pat, "f1", _cnpj(RAIZ_PJ), "true")])


# --- a lista e o degrau ----------------------------------------------------------------------------


def test_as_ampliadas_sao_as_quatro_pedidas_e_nao_estao_nos_cadastros():
    assert set(recorte.AMPLIADAS) == {
        "anatel_pados", "anatel_produtos_homologados", "anp_tancagem", "mte_pat",
    }  # fmt: skip
    assert not set(recorte.AMPLIADAS) & set(recorte.CADASTROS)
    assert set(recorte.AMPLIADAS) <= set(recorte.COLUNAS)
    assert set(envio.AMPLIADAS) <= set(envio.COM_FILTRO_PROPRIO)
    assert not set(envio.AMPLIADAS) & set(envio.FICAM_EM_CASA)


def test_as_ampliadas_so_vao_pelo_degrau_8():
    """O cron (degrau 6) não as manda: o envio pede o pode da Diretoria com as contagens."""
    for degrau in range(1, 8):
        assert not set(envio.AMPLIADAS) & set(envio.tabelas_do_degrau(degrau))
    assert envio.tabelas_do_degrau(8) == (*envio.tabelas_do_degrau(7), *envio.AMPLIADAS)
    assert envio._argumentos(["--degrau", "8"]).degrau == 8
    for nome in envio.AMPLIADAS:
        with pytest.raises(envio.RecorteErro, match="degrau 8"):
            envio.conferir_a_lista((nome,))


def test_nenhuma_coluna_da_copia_e_de_nome_e_o_nome_do_produto_fica_em_casa():
    for nome in recorte.AMPLIADAS:
        colunas = recorte.COLUNAS[nome]
        assert set(colunas) <= set(TABELAS[nome].colunas)
        assert not [
            c for c in colunas if any(p in c for p in recorte.PEDACOS_PROIBIDOS)
        ], nome
        assert set(recorte.TEXTOS_LIVRES[nome]) <= set(colunas)
    assert "nome_comercial" in TABELAS[recorte.HOMOLOGADOS].colunas
    assert "nome_comercial" not in recorte.COLUNAS[recorte.HOMOLOGADOS]


# --- o filtro --------------------------------------------------------------------------------------


def test_so_a_linha_de_pj_sem_marca_sai_e_a_chave_de_texto_vira_impressao_digital(
    tmp_path,
):
    base, saida = tmp_path / "base", tmp_path / "saida"
    _base_com_as_ampliadas(base)
    resultados = {r.tabela: r for r in envio.montar(base, saida, COM_AMPLIADAS)}
    pados = saida / recorte.PADOS / "pados.parquet"
    assert _ler(pados, "cnpj") == [(_cnpj(RAIZ_PJ),)]
    assert resultados[recorte.PADOS].linhas_tiradas == 6
    assert resultados[recorte.HOMOLOGADOS].linhas_tiradas == 2
    assert resultados[recorte.TANCAGEM].linhas_tiradas == 1
    assert resultados[recorte.PAT].arquivos == 3
    assert resultados[recorte.PAT].linhas_tiradas == 1
    assert _ler(saida / recorte.PAT / "beneficiarias.parquet", "cnpj") == [
        (_cnpj(RAIZ_PJ),)
    ]
    assert _ler(saida / recorte.PAT / "facilitadoras.parquet", "cnpj") == [
        (_cnpj(RAIZ_OUTRA),)
    ]
    for nome in recorte.AMPLIADAS:
        for arquivo in (saida / nome).glob("*.parquet"):
            assert _colunas(arquivo) == list(recorte.COLUNAS[nome]), arquivo
            texto = " ".join(str(v) for linha in _ler(arquivo) for v in linha)
            assert "FULANO" not in texto
    # a chave que leva texto (tema, serviço, modelo, nome do produto) sai como impressão digital
    for arquivo in (pados, saida / recorte.HOMOLOGADOS / "homologados.parquet"):
        ((chave,),) = _ler(arquivo, "id_na_fonte")
        assert len(chave) == recorte.TAMANHO_DA_IMPRESSAO
    # a da tancagem e a do PAT (CNPJ e códigos) ficam como são
    ((chave,),) = _ler(saida / recorte.TANCAGEM / "tancagem.parquet", "id_na_fonte")
    assert chave == "t1"
    # a tabela inteira não sai: nenhum manifesto, nenhum outro arquivo
    assert sorted(p.name for p in (saida / recorte.PAT).iterdir()) == [
        "beneficiarias.parquet", "facilitadoras.parquet", "fornecedoras.parquet",
    ]  # fmt: skip


def test_o_pat_fica_com_o_arquivo_de_fornecedoras_vazio_e_o_envio_cai(tmp_path):
    """Um arquivo que fica sem linha não derruba sozinho; a tabela toda vazia derruba (trocaria a do VPS por nada)."""
    base = tmp_path / "base"
    _base_com_as_ampliadas(base)
    pat = recorte.PAT
    for arquivo in ("beneficiarias", "facilitadoras", "fornecedoras"):
        _tabela(base, pat, arquivo, [_linha(pat, "x", _cnpj(RAIZ_PJ), "true")])
    with pytest.raises(envio.RecorteErro, match="mte_pat: cópia vazia"):
        envio.montar(base, tmp_path / "saida", COM_AMPLIADAS)


def test_ampliada_sem_arquivo_na_base_derruba_o_envio(tmp_path):
    base = tmp_path / "base"
    _base_com_as_ampliadas(base)
    for arquivo in (base / recorte.TANCAGEM).glob("*"):
        arquivo.unlink()
    with pytest.raises(envio.RecorteErro, match="anp_tancagem: sem arquivo na base"):
        envio.montar(base, tmp_path / "saida", COM_AMPLIADAS)


def test_as_ampliadas_nao_vao_sem_empresas_pj(tmp_path):
    base = tmp_path / "base"
    _base_com_as_ampliadas(base)
    with pytest.raises(envio.RecorteErro, match="junto com cnpj_empresas_pj"):
        envio.montar(base, tmp_path / "saida", recorte.AMPLIADAS)


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
    _base_com_as_ampliadas(base)
    with pytest.raises(envio.RecorteErro, match="fora da lista"):
        envio.montar(base, tmp_path / "saida", COM_AMPLIADAS)


def _conferir(tmp_path: Path, nome: str, selecao: str) -> dict[str, int]:
    _empresas_pj(tmp_path / "s")
    empresas = sorted((tmp_path / "s" / "cnpj_empresas_pj").glob("*.parquet"))
    arquivo = tmp_path / "s" / nome / "x.parquet"
    _parquet(arquivo, selecao)
    with duckdb.connect() as con:
        return recorte.conferir_cadastros(con, {nome: [arquivo]}, empresas)


def _saida_da_copia(tmp_path: Path, nome: str, linhas: list[str]) -> str:
    """A seleção da cópia reduzida (colunas da lista, chave como saiu) sobre as linhas dadas."""
    origem = tmp_path / "o" / nome / "o.parquet"
    _parquet(origem, " UNION ALL BY NAME ".join(linhas))
    colunas = ", ".join(f'"{c}"' for c in recorte.COLUNAS[nome])
    return f"SELECT {colunas} FROM '{origem.as_posix()}'"


def test_a_trava_aceita_a_cópia_boa(tmp_path):
    nome = recorte.TANCAGEM
    selecao = _saida_da_copia(
        tmp_path, nome, [_linha(nome, "t1", _cnpj(RAIZ_PJ), "false")]
    )
    assert _conferir(tmp_path, nome, selecao) == {nome: 1}


@pytest.mark.parametrize(
    ("marca", "cnpj", "texto", "esperado"),
    [
        ("true", _cnpj(RAIZ_PJ), {}, "marcada"),
        ("NULL::BOOLEAN", _cnpj(RAIZ_PJ), {}, "marcada"),
        ("false", _cnpj(RAIZ_FORA), {}, "fora da lista"),
        ("false", None, {}, "CNPJ que não confere"),
        (
            "false",
            _cnpj(RAIZ_PJ),
            {"segmento": formatado(cpf_que_confere("888777666"))},
            "CPF",
        ),
        ("false", _cnpj(RAIZ_PJ), {"tag": "fulano@exemplo.com"}, "e-mail"),
    ],
)
def test_a_trava_derruba_a_linha_que_o_filtro_nao_podia_deixar(
    tmp_path, marca, cnpj, texto, esperado
):
    nome = recorte.TANCAGEM
    selecao = _saida_da_copia(
        tmp_path, nome, [_linha(nome, "t1", cnpj, marca, **texto)]
    )
    with pytest.raises(recorte.CadastroComPessoa) as erro:
        _conferir(tmp_path, nome, selecao)
    mensagem = str(erro.value)
    assert (
        esperado.lower() in mensagem.lower()
        or "CPF ou e-mail" in mensagem
        or "marcada" in mensagem
    )
    # a mensagem só leva contagens: nenhum CNPJ, nome ou texto
    assert "888777666" not in mensagem
    assert "fulano" not in mensagem.lower()
    assert _cnpj(RAIZ_PJ) not in mensagem


def test_a_trava_derruba_a_coluna_que_a_copia_nao_leva(tmp_path):
    nome = recorte.HOMOLOGADOS
    origem = tmp_path / "o.parquet"
    _parquet(
        origem,
        _linha(
            nome, "h1", _cnpj(RAIZ_PJ), "false", nome_comercial="PRODUTO DE MENTIRA"
        ),
    )
    with pytest.raises(recorte.CadastroComPessoa, match="coluna.* fora da lista"):
        _conferir(tmp_path, nome, f"SELECT * FROM '{origem.as_posix()}'")
