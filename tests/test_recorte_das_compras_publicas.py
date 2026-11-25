"""As compras públicas no recorte da API (linha 988): o degrau 9, o filtro e a trava de zero pessoa.

O cadastro de fornecedores do SICAF (`comprasgov_sicaf`) e o Banco de Preços em Saúde (`bps_compras`): CNPJ inteiro
em toda linha, sem coluna de nome nem de CPF, mas com linha marcada em `trata_como_pessoa`. Ao VPS vai só a cópia
reduzida, pelo filtro e pela trava dos cadastros, com as condições a mais (`CONDICOES_A_MAIS`): a natureza de pessoa
que o próprio SICAF escreve, e o fabricante e a instituição compradora do BPS. Todo dado aqui é inventado: CNPJs
montados com o dígito certo a partir de raízes de mentira, nenhum nome real e nenhum CPF que confere guardado em
arquivo (o teste o monta na hora).
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
    RAIZ_OUTRA,
    RAIZ_PJ,
    _cnpj,
    _colunas,
    _empresas_pj,
    _ler,
    _parquet,
)

SICAF, BPS = recorte.SICAF, recorte.BPS
COM_AS_COMPRAS = (
    "cnpj_empresas_pj",
    "cnpj_estabelecimentos_pj",
    *recorte.COMPRAS_PUBLICAS,
)
CONTROLE_SOLTO = (
    "visto_em",
    "disponivel_em",
    "origem_sha256",
    "origem_coletada_em",
    "montado_em",
    "versao_do_codigo",
)
DATAS = ("data_da_compra", "data_de_insercao")
NUMEROS = ("capacidade", "quantidade", "preco_unitario", "preco_total")
SIM_OU_NAO = ("ativo", "habilitado_a_licitar")
NATUREZA_DE_EMPRESA = "2062"  # sociedade empresária limitada


def _cnpj_errado(raiz: str) -> str:
    certo = _cnpj(raiz)
    return certo[:-1] + str((int(certo[-1]) + 1) % 10)


def _padrao(coluna: str) -> str:
    """O valor de mentira de uma coluna que o caso não troca."""
    if coluna in DATAS:
        return "DATE '2025-01-01'"
    if coluna in NUMEROS:
        return "1.5"
    if coluna in SIM_OU_NAO:
        return "true"
    if coluna == "ano_da_compra":
        return "2025"
    if coluna == "natureza_juridica":
        return f"'{NATUREZA_DE_EMPRESA}'"
    if coluna == "cnpj_do_fabricante":
        return f"'{_cnpj(RAIZ_OUTRA)}'"
    if coluna == "cnpj_basico_do_fabricante":
        return f"'{RAIZ_OUTRA}'"
    if coluna == "cnpj_da_instituicao":
        return f"'{_cnpj(RAIZ_PJ)}'"
    return "'valor de mentira'"


def _linha(nome: str, id_na_fonte: str, cnpj: str, marca: str, **troca: str) -> str:
    """Uma linha com as colunas de verdade (as do dicionário); `troca` põe outro valor SQL numa coluna."""
    partes = [
        f"'{id_na_fonte}' AS id_na_fonte",
        f"'{cnpj}' AS cnpj",
        f"'{cnpj[:8]}' AS cnpj_basico",
    ]
    partes += ["true AS consta", f"{marca} AS trata_como_pessoa"]
    for coluna in TABELAS[nome].colunas:
        if coluna in (
            *CONTROLE_SOLTO,
            "id_na_fonte",
            "cnpj",
            "cnpj_basico",
            "consta",
            "trata_como_pessoa",
        ):
            continue
        partes.append(f"{troca.get(coluna, _padrao(coluna))} AS {coluna}")
    return f"SELECT {', '.join(partes)}, {CONTROLE_DE_MENTIRA}"


def _tabela(base: Path, nome: str, arquivo: str, linhas: list[str]) -> None:
    _parquet(base / nome / f"{arquivo}.parquet", " UNION ALL BY NAME ".join(linhas))


def _base_com_as_compras(base: Path) -> None:
    """Em cada tabela, linhas boas e todo tipo de linha que não pode sair; o SICAF tem dois arquivos."""
    _empresas_pj(base)
    pj = _cnpj(RAIZ_PJ)
    cpf = formatado(cpf_que_confere("888777666"))
    _tabela(
        base,
        SICAF,
        "ativos",
        [
            _linha(SICAF, "s1", pj, "false"),
            _linha(
                SICAF, "s2", pj, "false", natureza_juridica="'2135'"
            ),  # empresário individual pelo SICAF
            _linha(
                SICAF, "s3", pj, "false", natureza_juridica="'4120'"
            ),  # grupo 4: pessoa física
            _linha(
                SICAF, "s4", pj, "false", natureza_juridica="NULL::VARCHAR"
            ),  # sem natureza
            _linha(SICAF, "s5", pj, "true"),  # marcada pela Receita
            _linha(SICAF, "s6", _cnpj(RAIZ_FORA), "false"),  # fora da lista sem pessoa
        ],
    )
    _tabela(
        base,
        SICAF,
        "inativos",
        [
            _linha(SICAF, "s7", _cnpj(RAIZ_OUTRA), "false"),
            _linha(
                SICAF, "s8", pj, "false", municipio=f"'contato {cpf}'"
            ),  # CPF no texto
        ],
    )
    _tabela(
        base,
        BPS,
        "compras",
        [
            _linha(BPS, "b1", pj, "false"),
            _linha(
                BPS,
                "b2",
                pj,
                "false",
                cnpj_do_fabricante="NULL::VARCHAR",
                cnpj_basico_do_fabricante="NULL::VARCHAR",
            ),  # fabricante de fora (sem CNPJ): sai
            _linha(
                BPS,
                "b3",
                pj,
                "false",
                cnpj_do_fabricante=f"'{_cnpj(RAIZ_FORA)}'",
                cnpj_basico_do_fabricante=f"'{RAIZ_FORA}'",
            ),  # fabricante fora da lista sem pessoa
            _linha(
                BPS,
                "b4",
                pj,
                "false",
                cnpj_do_fabricante=f"'{_cnpj_errado(RAIZ_OUTRA)}'",
            ),  # dígito errado
            _linha(
                BPS, "b5", pj, "false", cnpj_basico_do_fabricante=f"'{RAIZ_PJ}'"
            ),  # raiz trocada
            _linha(
                BPS, "b6", pj, "false", cnpj_da_instituicao=f"'{_cnpj_errado(RAIZ_PJ)}'"
            ),  # instituição errada
            _linha(
                BPS, "b7", pj, "false", item="'fulano@exemplo.com'"
            ),  # e-mail no texto
            _linha(BPS, "b8", pj, "true"),  # marcada
        ],
    )


# --- a lista e o degrau ----------------------------------------------------------------------------


def test_as_compras_publicas_sao_as_duas_e_nao_estao_em_outro_grupo():
    assert recorte.COMPRAS_PUBLICAS == ("comprasgov_sicaf", "bps_compras")
    assert not set(recorte.COMPRAS_PUBLICAS) & {*recorte.CADASTROS, *recorte.AMPLIADAS}
    assert set(envio.COMPRAS_PUBLICAS) <= set(envio.COM_FILTRO_PROPRIO)
    assert not set(envio.COMPRAS_PUBLICAS) & set(envio.FICAM_EM_CASA)


def test_as_compras_publicas_so_vao_pelo_degrau_9():
    """O cron (degrau 6) não as manda: o envio pede o pode da Diretoria com as contagens."""
    for degrau in range(1, 9):
        assert not set(envio.COMPRAS_PUBLICAS) & set(envio.tabelas_do_degrau(degrau))
    assert envio.tabelas_do_degrau(9) == (
        *envio.tabelas_do_degrau(8),
        *envio.COMPRAS_PUBLICAS,
    )
    assert envio._argumentos(["--degrau", "9"]).degrau == 9
    for nome in envio.COMPRAS_PUBLICAS:
        with pytest.raises(envio.RecorteErro, match="degrau 9"):
            envio.conferir_a_lista((nome,))


def test_nenhuma_coluna_da_copia_e_de_nome_e_o_processo_de_compra_fica_em_casa():
    for nome in recorte.COMPRAS_PUBLICAS:
        colunas = recorte.COLUNAS[nome]
        assert set(colunas) <= set(TABELAS[nome].colunas), nome
        assert not [
            c for c in colunas if any(p in c for p in recorte.PEDACOS_PROIBIDOS)
        ], nome
        assert set(recorte.TEXTOS_LIVRES[nome]) <= set(colunas), nome
        assert nome in recorte.CONDICOES_A_MAIS
    assert "processo_de_compra" in TABELAS[BPS].colunas
    assert "processo_de_compra" not in recorte.COLUNAS[BPS]


def test_toda_coluna_de_texto_da_copia_e_conferida_contra_cpf_e_e_mail():
    """O que não é chave, CNPJ, data, número ou sim/não é texto livre: CPF ou e-mail ali derruba a linha."""
    fora_do_texto = {
        *recorte.CONTROLE,
        *DATAS,
        *NUMEROS,
        *SIM_OU_NAO,
        "ano_da_compra",
        "cnae",
    }
    fora_do_texto |= {
        "cnpj_do_fabricante",
        "cnpj_basico_do_fabricante",
        "cnpj_da_instituicao",
    }
    for nome in recorte.COMPRAS_PUBLICAS:
        textos = set(recorte.COLUNAS[nome]) - fora_do_texto
        assert textos == set(recorte.TEXTOS_LIVRES[nome]), nome


# --- o filtro --------------------------------------------------------------------------------------


def test_so_a_linha_de_pj_sai_com_as_condicoes_a_mais(tmp_path):
    base, saida = tmp_path / "base", tmp_path / "saida"
    _base_com_as_compras(base)
    resultados = {r.tabela: r for r in envio.montar(base, saida, COM_AS_COMPRAS)}
    assert _ler(saida / SICAF / "ativos.parquet", "id_na_fonte") == [("s1",)]
    assert _ler(saida / SICAF / "inativos.parquet", "id_na_fonte") == [("s7",)]
    assert resultados[SICAF].arquivos == 2
    assert resultados[SICAF].linhas_tiradas == 6
    assert sorted(_ler(saida / BPS / "compras.parquet", "id_na_fonte")) == [
        ("b1",),
        ("b2",),
    ]
    assert resultados[BPS].linhas_tiradas == 6
    for nome in recorte.COMPRAS_PUBLICAS:
        for arquivo in (saida / nome).glob("*.parquet"):
            assert _colunas(arquivo) == list(recorte.COLUNAS[nome]), arquivo
            texto = " ".join(str(v) for linha in _ler(arquivo) for v in linha)
            assert "fulano" not in texto
            assert "888777666" not in texto.replace(".", "")
    # a tabela inteira não sai: nenhum manifesto, nenhum outro arquivo
    assert sorted(p.name for p in (saida / SICAF).iterdir()) == [
        "ativos.parquet",
        "inativos.parquet",
    ]
    assert sorted(p.name for p in (saida / BPS).iterdir()) == ["compras.parquet"]


def test_compra_publica_sem_arquivo_na_base_derruba_o_envio(tmp_path):
    base = tmp_path / "base"
    _base_com_as_compras(base)
    for arquivo in (base / BPS).glob("*"):
        arquivo.unlink()
    with pytest.raises(envio.RecorteErro, match="bps_compras: sem arquivo na base"):
        envio.montar(base, tmp_path / "saida", COM_AS_COMPRAS)


def test_as_compras_publicas_nao_vao_sem_empresas_pj(tmp_path):
    base = tmp_path / "base"
    _base_com_as_compras(base)
    with pytest.raises(envio.RecorteErro, match="junto com cnpj_empresas_pj"):
        envio.montar(base, tmp_path / "saida", recorte.COMPRAS_PUBLICAS)


def test_o_bps_todo_marcado_deixa_a_copia_vazia_e_o_envio_cai(tmp_path):
    base = tmp_path / "base"
    _base_com_as_compras(base)
    _tabela(base, BPS, "compras", [_linha(BPS, "b1", _cnpj(RAIZ_PJ), "true")])
    with pytest.raises(envio.RecorteErro, match="bps_compras: cópia vazia"):
        envio.montar(base, tmp_path / "saida", COM_AS_COMPRAS)


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
    _base_com_as_compras(base)
    with pytest.raises(envio.RecorteErro, match="fora da lista"):
        envio.montar(base, tmp_path / "saida", COM_AS_COMPRAS)


def _conferir(tmp_path: Path, nome: str, linhas: list[str]) -> dict[str, int]:
    """A trava sobre a seleção da cópia (só as colunas da lista) feita das linhas dadas, sem passar pelo filtro."""
    _empresas_pj(tmp_path / "s")
    empresas = sorted((tmp_path / "s" / "cnpj_empresas_pj").glob("*.parquet"))
    origem = tmp_path / "o" / nome / "o.parquet"
    _parquet(origem, " UNION ALL BY NAME ".join(linhas))
    colunas = ", ".join(f'"{c}"' for c in recorte.COLUNAS[nome])
    arquivo = tmp_path / "s" / nome / "x.parquet"
    _parquet(arquivo, f"SELECT {colunas} FROM '{origem.as_posix()}'")
    with duckdb.connect() as con:
        return recorte.conferir_cadastros(con, {nome: [arquivo]}, empresas)


def test_a_trava_aceita_a_copia_boa(tmp_path):
    pj = _cnpj(RAIZ_PJ)
    assert _conferir(tmp_path, SICAF, [_linha(SICAF, "s1", pj, "false")]) == {SICAF: 1}
    sem_fabricante = {
        "cnpj_do_fabricante": "NULL::VARCHAR",
        "cnpj_basico_do_fabricante": "NULL::VARCHAR",
    }
    linhas = [
        _linha(BPS, "b1", pj, "false"),
        _linha(BPS, "b2", pj, "false", **sem_fabricante),
    ]
    assert _conferir(tmp_path / "bps", BPS, linhas) == {BPS: 2}


@pytest.mark.parametrize(
    ("nome", "troca", "esperado"),
    [
        (SICAF, {"natureza_juridica": "'2135'"}, "empresário individual"),
        (SICAF, {"natureza_juridica": "'4120'"}, "pessoa física"),
        (SICAF, {"natureza_juridica": "NULL::VARCHAR"}, "sem natureza"),
        # o código com máscara, com zero na frente ou vazio (revisão cruzada): a leitura mais estreita não deixa sair
        (SICAF, {"natureza_juridica": "'213-5'"}, "empresário individual"),
        (SICAF, {"natureza_juridica": "'02135'"}, "empresário individual"),
        (SICAF, {"natureza_juridica": "'412-0'"}, "pessoa física"),
        (SICAF, {"natureza_juridica": "''"}, "sem natureza"),
        (
            BPS,
            {"cnpj_do_fabricante": f"'{_cnpj_errado(RAIZ_OUTRA)}'"},
            "CNPJ do fabricante",
        ),
        (
            BPS,
            {
                "cnpj_do_fabricante": f"'{_cnpj(RAIZ_FORA)}'",
                "cnpj_basico_do_fabricante": f"'{RAIZ_FORA}'",
            },
            "raiz do fabricante",
        ),
        (BPS, {"cnpj_basico_do_fabricante": f"'{RAIZ_PJ}'"}, "raiz do fabricante"),
        (BPS, {"cnpj_da_instituicao": f"'{_cnpj_errado(RAIZ_PJ)}'"}, "instituição"),
        # a compradora com o dígito certo, mas de raiz fora da lista sem pessoa (empresário individual, MEI)
        (
            BPS,
            {"cnpj_da_instituicao": f"'{_cnpj(RAIZ_FORA)}'"},
            "raiz da instituição",
        ),
        (
            BPS,
            {"item": f"'para {formatado(cpf_que_confere('888777666'))}'"},
            "CPF ou e-mail",
        ),
    ],
)
def test_a_trava_derruba_a_linha_que_o_filtro_nao_podia_deixar(
    tmp_path, nome, troca, esperado
):
    with pytest.raises(recorte.CadastroComPessoa) as erro:
        _conferir(
            tmp_path, nome, [_linha(nome, "x1", _cnpj(RAIZ_PJ), "false", **troca)]
        )
    mensagem = str(erro.value)
    assert esperado in mensagem
    # a mensagem só leva contagens: nenhum CNPJ, nome ou texto
    assert "888777666" not in mensagem
    assert _cnpj(RAIZ_PJ) not in mensagem
    assert RAIZ_FORA not in mensagem


def test_a_trava_derruba_o_processo_de_compra_que_a_copia_nao_leva(tmp_path):
    _empresas_pj(tmp_path / "s")
    empresas = sorted((tmp_path / "s" / "cnpj_empresas_pj").glob("*.parquet"))
    arquivo = tmp_path / "s" / BPS / "x.parquet"
    _parquet(arquivo, _linha(BPS, "b1", _cnpj(RAIZ_PJ), "false"))
    with (
        duckdb.connect() as con,
        pytest.raises(recorte.CadastroComPessoa, match="fora da lista"),
    ):
        recorte.conferir_cadastros(con, {BPS: [arquivo]}, empresas)
