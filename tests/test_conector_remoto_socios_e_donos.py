"""A ferramenta `socios_e_donos` do conector (ADR 0128, Emenda 4): pessoa física só para quem tem a permissão.

Riscos que estes testes pegam: (1) a ferramenta aparecer, ou responder, para a organização sem a permissão
`pessoa_no_conector`; (2) o conector deixar passar CPF (formatado, mascarado ou onze dígitos que conferem),
e-mail, telefone, CEP ou um campo fora da lista fechada se a API um dia mandar; (3) a tranca de pessoa das
outras ferramentas afrouxar por causa desta; (4) a lista do conector e a da API se separarem. De ponta a ponta,
a API de verdade roda dentro do teste (`httpx.ASGITransport`) com o acervo de mentira e duas organizações.
Todo nome e todo CPF aqui é inventado.
"""

import json
import re

import httpx
import pytest

from conector_remoto import ferramentas, socios_e_donos
from conector_remoto.saida import TETO_DE_CARACTERES
from src import api, pessoa_no_texto
from src.analista import pessoa
from src.api_externa import VARIAVEL_DA_CHAVE, acesso, pessoas
from tests import ajudantes_da_api_externa as aj_api
from tests import ajudantes_do_conector as aj
from tests import test_montar_acervo_pessoa as montar_de_mentira
from tests.ajudantes_de_cpf import cpf_que_confere, formatado, meio

SOCIEDADE = "11222333000181"
INDIVIDUAL = "22333444000181"
CPF_DE_MENTIRA = cpf_que_confere("888654321")
FERRAMENTA = "socios_e_donos"


def _corpo(**extra) -> dict:
    return {
        "status": "ready",
        "partners": [
            {
                "name": "FULANA EXEMPLO",
                "role": "Sócio-Administrador",
                "since": "2020-01-31",
            }
        ],
        "partners_total": 1,
        "owners": [],
        "owners_status": "none",
        "source": "Cadastro Nacional da Pessoa Jurídica (Receita Federal)",
        "attribution": {"partners": "Receita Federal", "owners": "Receita Federal"},
        "snapshot_month": "2026-10",
        "limits": ["Sem CPF."],
    } | extra


def _api_com(corpo: object, conjuntos=("pessoa_no_conector",), status: int = 200):
    rotas = {f"/companies/{SOCIEDADE}/people": httpx.Response(status, json=corpo)}
    return aj.api_de_mentira(rotas, conjuntos=conjuntos)


# ---------------------------------------------------------------- quem vê a ferramenta


def test_sem_a_permissao_a_ferramenta_nao_aparece_nem_responde():
    pedidos: list[httpx.Request] = []
    rotas = {f"/companies/{SOCIEDADE}/people": httpx.Response(200, json=_corpo())}
    transporte = aj.api_de_mentira(
        rotas, conjuntos=("links", "profiles"), pedidos=pedidos
    )
    with aj.conector(transporte) as cliente:
        assert FERRAMENTA not in aj.nomes_das_ferramentas(cliente, aj.CHAVE_DE_MENTIRA)
        erro, texto = aj.chamar(
            cliente, aj.CHAVE_DE_MENTIRA, FERRAMENTA, cnpj=SOCIEDADE
        )
    assert erro and "FULANA" not in texto
    assert not [p for p in pedidos if p.url.path.endswith("/people")]


def test_com_a_permissao_a_ferramenta_entrega_os_socios():
    with aj.conector(_api_com(_corpo())) as cliente:
        assert FERRAMENTA in aj.nomes_das_ferramentas(cliente, aj.CHAVE_DE_MENTIRA)
        corpo = aj.chamar_ok(
            cliente, aj.CHAVE_DE_MENTIRA, FERRAMENTA, cnpj="11.222.333/0001-81"
        )
    assert corpo == _corpo()


def test_a_ferramenta_so_pede_cnpj_e_nao_chama_a_api_com_cpf():
    pedidos: list[httpx.Request] = []
    rotas = {f"/companies/{SOCIEDADE}/people": httpx.Response(200, json=_corpo())}
    transporte = aj.api_de_mentira(
        rotas, conjuntos=("pessoa_no_conector",), pedidos=pedidos
    )
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(
            cliente, aj.CHAVE_DE_MENTIRA, FERRAMENTA, cnpj=formatado(CPF_DE_MENTIRA)
        )
    assert erro and "nunca CPF" in texto
    assert not [p for p in pedidos if p.url.path.endswith("/people")]


def test_o_404_da_api_vira_o_nao_disponivel_de_sempre():
    with aj.conector(_api_com({"detail": "Not Found"}, status=404)) as cliente:
        erro, texto = aj.chamar(
            cliente, aj.CHAVE_DE_MENTIRA, FERRAMENTA, cnpj=SOCIEDADE
        )
    assert erro and "Não disponível" in texto


# ---------------------------------------------------------------- a tranca da saída


SUJOS = {
    "chave de CPF": _corpo(cpf="x"),
    "chave de nascimento no sócio": _corpo(
        partners=[
            {
                "name": "FULANA EXEMPLO",
                "role": "Sócio",
                "since": None,
                "birth_date": "1980-01-01",
            }
        ]
    ),
    "faixa de idade": _corpo(age_range="31-40"),
    "endereço": _corpo(address="RUA EXEMPLO"),
    "CPF formatado no nome": _corpo(
        partners=[
            {
                "name": f"FULANA {formatado(CPF_DE_MENTIRA)}",
                "role": "Sócio",
                "since": None,
            }
        ]
    ),
    "CPF mascarado na qualificação": _corpo(
        partners=[
            {
                "name": "FULANA",
                "role": f"Sócio ***{meio(CPF_DE_MENTIRA)}**",
                "since": None,
            }
        ]
    ),
    "CPF só com dígitos no titular": _corpo(
        owners=[{"name": f"BELTRANO EXEMPLO {CPF_DE_MENTIRA}"}]
    ),
    "e-mail": _corpo(owners=[{"name": "beltrano@exemplo.invalid"}]),
    "telefone": _corpo(owners=[{"name": "BELTRANO (11) 91234-5678"}]),
    "telefone em largura total": _corpo(
        owners=[{"name": "BELTRANO ３４５６-７８９０"}]
    ),
    "CEP": _corpo(limits=["Rua Exemplo, 01310-100"]),
    "corpo que não é objeto": [{"name": "FULANA"}],
}


@pytest.mark.parametrize("caso", SUJOS)
def test_resposta_suja_da_api_e_recusada_inteira_sem_repetir_o_valor(caso):
    with aj.conector(_api_com(SUJOS[caso])) as cliente:
        erro, texto = aj.chamar(
            cliente, aj.CHAVE_DE_MENTIRA, FERRAMENTA, cnpj=SOCIEDADE
        )
    assert erro, caso
    assert ferramentas.MENSAGEM_DE_PESSOA_PROIBIDA in texto
    assert "FULANA" not in texto and "BELTRANO" not in texto
    assert meio(CPF_DE_MENTIRA) not in texto and "exemplo.invalid" not in texto


def test_o_registro_diz_onde_falhou_nunca_o_valor(caplog):
    with aj.conector(_api_com(SUJOS["CPF formatado no nome"])) as cliente:
        aj.chamar(cliente, aj.CHAVE_DE_MENTIRA, FERRAMENTA, cnpj=SOCIEDADE)
    registros = [
        r for r in caplog.records if r.getMessage() == "resposta_com_pessoa_recusada"
    ]
    assert registros and registros[0].__dict__["caminhos"] == ["partners[0].name"]
    assert meio(CPF_DE_MENTIRA) not in caplog.text and "FULANA" not in caplog.text


def test_caractere_invisivel_nao_esconde_o_cpf():
    escondido = "\u200b".join(formatado(CPF_DE_MENTIRA))
    corpo = _corpo(
        partners=[{"name": f"FULANA {escondido}", "role": "Sócio", "since": None}]
    )
    with aj.conector(_api_com(corpo)) as cliente:
        erro, texto = aj.chamar(
            cliente, aj.CHAVE_DE_MENTIRA, FERRAMENTA, cnpj=SOCIEDADE
        )
    assert erro and ferramentas.MENSAGEM_DE_PESSOA_PROIBIDA in texto


def test_resposta_acima_do_teto_nao_sai():
    muitos = [
        {"name": f"SOCIA EXEMPLO {chr(65 + i % 26)}", "role": "Sócio", "since": None}
        for i in range(4000)
    ]
    corpo = _corpo(partners=muitos, partners_total=len(muitos))
    assert len(json.dumps(corpo, ensure_ascii=False)) > TETO_DE_CARACTERES
    with aj.conector(_api_com(corpo)) as cliente:
        erro, texto = aj.chamar(
            cliente, aj.CHAVE_DE_MENTIRA, FERRAMENTA, cnpj=SOCIEDADE
        )
    assert erro and "grande demais" in texto and "SOCIA" not in texto


def test_as_outras_ferramentas_seguem_recusando_socio():
    """A tranca própria é só desta ferramenta: a ficha com `partners` continua recusada inteira."""
    rotas = {
        f"/companies/{SOCIEDADE}/profile": httpx.Response(
            200, json={"partners": [{"name": "FULANA"}]}
        )
    }
    transporte = aj.api_de_mentira(rotas, conjuntos=("profiles", "pessoa_no_conector"))
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(
            cliente, aj.CHAVE_DE_MENTIRA, "ficha_da_empresa", cnpj=SOCIEDADE
        )
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto and "FULANA" not in texto


def test_a_lista_fechada_e_os_padroes_sao_os_da_api():
    assert socios_e_donos.CHAVES_PERMITIDAS == pessoas.CHAVES_DA_RESPOSTA
    assert socios_e_donos.CONJUNTO == pessoas.CONJUNTO
    assert socios_e_donos.TELEFONE.pattern == pessoa_no_texto.TELEFONE.pattern
    assert ferramentas.CONJUNTOS_DA_FERRAMENTA[FERRAMENTA] == frozenset(
        {pessoas.CONJUNTO}
    )


# ---------------------------------------------------------------- de ponta a ponta, duas organizações


@pytest.fixture
def cenario(banco, monkeypatch, tmp_path):
    cnpj, bruto = montar_de_mentira._acervo(tmp_path / "origem")
    destino = tmp_path / "fora" / "acervo_pessoa"
    montar_de_mentira.montar.carregar(
        cnpj, bruto, destino, montar_de_mentira.AGORA, montar_de_mentira.SEM_OPOSTOS
    )
    monkeypatch.setenv(pessoa.VARIAVEL, str(destino))
    monkeypatch.setattr(acesso, "agora", lambda: aj_api.AGORA)
    acesso.zerar_limites()
    ator = aj_api.admin(banco)
    com = aj_api.organizacao(banco, ator, "Casa Exemplo")
    sem = aj_api.organizacao(banco, ator, "Outra Exemplo")
    aj_api.contrato(banco, ator, com, conjunto=pessoas.CONJUNTO)
    aj_api.contrato(banco, ator, sem, conjunto="links")
    return {
        "com": aj_api.chave(banco, ator, com).valor,
        "sem": aj_api.chave(banco, ator, sem).valor,
    }


@pytest.fixture
def cliente(cenario):
    transporte = httpx.ASGITransport(app=api.criar_app({VARIAVEL_DA_CHAVE: "1"}))
    with aj.conector(transporte) as cliente:
        yield cliente


def test_so_a_organizacao_com_a_permissao_ve_e_recebe_os_socios(cliente, cenario):
    assert FERRAMENTA in aj.nomes_das_ferramentas(cliente, cenario["com"])
    assert FERRAMENTA not in aj.nomes_das_ferramentas(cliente, cenario["sem"])
    corpo = aj.chamar_ok(cliente, cenario["com"], FERRAMENTA, cnpj=SOCIEDADE)
    assert isinstance(corpo, dict)
    assert [p["name"] for p in corpo["partners"]] == ["FULANA EXEMPLO"]
    erro, texto = aj.chamar(cliente, cenario["sem"], FERRAMENTA, cnpj=SOCIEDADE)
    assert erro and "FULANA" not in texto


def test_o_titular_chega_sem_os_digitos_do_cpf(cliente, cenario):
    corpo = aj.chamar_ok(cliente, cenario["com"], FERRAMENTA, cnpj=INDIVIDUAL)
    assert isinstance(corpo, dict)
    assert corpo["owners"] == [{"name": "BELTRANO EXEMPLO"}]


def test_toda_resposta_de_ponta_a_ponta_passa_na_varredura(cliente, cenario):
    """Zero CPF, zero menor de idade e zero endereço ou contato em tudo o que a IA recebe por esta ferramenta."""
    textos = [
        aj.chamar(cliente, chave, FERRAMENTA, cnpj=cnpj)[1]
        for chave in (cenario["com"], cenario["sem"])
        for cnpj in (SOCIEDADE, INDIVIDUAL, "99888777000100")
    ]
    for texto in textos:
        assert not [
            m
            for m in pessoa_no_texto.ONZE_DIGITOS.findall(texto)
            if pessoa_no_texto.cpf_valido(m)
        ]
        assert not pessoa_no_texto.texto_de_pessoa(
            texto
        ) and not pessoa_no_texto.telefone_no_texto(texto)
        assert not re.search(r"(?<!\d)\d{5}-?\d{3}(?!\d)", texto)
        for proibida in ("CRIANCA", "REPRESENTADO", "birth", "address", "phone", "***"):
            assert proibida not in texto
        if texto.startswith("{"):
            assert socios_e_donos.falhas_da_resposta(json.loads(texto)) == []
