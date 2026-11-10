"""O que o conector remoto faz com a resposta antes de entregá-la à IA (linha 570): pessoa, texto e tamanho.

Riscos: um campo de pessoa física passar (a resposta inteira tem de ser recusada, sem o valor no aviso),
texto invisível levar instrução escondida à IA e uma resposta grande demais estourar a conversa. E o
contrário: o filtro barrar um campo legítimo da API (todos os nomes de saída de hoje passam).
"""

import ast
from pathlib import Path

import pytest

from conector_remoto import pessoa, saida
from conector_remoto.acesso import FORMATO_DA_CHAVE
from src import chaves_da_api
from src.api_externa.nomes import IDENTIFICADORES, NOMES_DE_FORA
from src.portao_externo import PALAVRAS_QUE_NUNCA_SAEM

PASTA_DO_CONECTOR = Path(__file__).resolve().parent.parent / "conector_remoto"

# ---------------------------------------------------------------- pessoa física


def test_toda_palavra_do_portao_esta_no_filtro():
    assert PALAVRAS_QUE_NUNCA_SAEM <= pessoa.PALAVRAS_EM_PORTUGUES


@pytest.mark.parametrize("nome", sorted({*NOMES_DE_FORA.values(), *IDENTIFICADORES}))
def test_nenhum_nome_de_saida_da_api_parece_pessoa(nome):
    # se este teste falhar, ou a API passou a servir pessoa, ou a palavra do filtro é larga demais
    assert not pessoa.chave_de_pessoa(nome)


@pytest.mark.parametrize(
    "chave",
    [
        "partners", "shareholder_name", "cpf", "socios", "boardDirectors", "beneficial_owner",
        "natural_person", "administrator_since", "email", "phone_number", "street_address",
        "credit_score", "PD", "birth_date", "qsa",
    ],
)  # fmt: skip
def test_chave_de_pessoa_e_achada_em_qualquer_forma(chave):
    assert pessoa.chave_de_pessoa(chave)


@pytest.mark.parametrize(
    "texto",
    [
        "123.456.789-09",
        "sócio ***123456**",
        "***.123.456-**",
        "fale com ana@exemplo.com.br",
    ],
)
def test_cpf_inteiro_ou_mascarado_e_email_no_texto(texto):
    assert pessoa.texto_de_pessoa(texto)


@pytest.mark.parametrize(
    "texto",
    ["11.111.111/0001-91", "2026-10-31", "ALFA TECNOLOGIA S.A.", "R$ 1.234.567,89"],
)
def test_cnpj_data_e_numero_nao_sao_pessoa(texto):
    assert not pessoa.texto_de_pessoa(texto)


def test_o_aviso_diz_onde_e_nunca_o_valor():
    corpo = {
        "companies": [
            {"cnpj": "11111111000191", "legal_name": {"value": "ALFA"}},
            {"cnpj": "22222222000191", "partners": [{"name": "FULANO DE TAL"}]},
        ],
        "notes": ["contato: alguem@exemplo.com"],
    }
    with pytest.raises(pessoa.RespostaComPessoa) as recusa:
        pessoa.exigir_sem_pessoa(corpo)
    assert recusa.value.caminhos == ["companies[1].partners", "notes[0]"]
    assert "FULANO" not in str(recusa.value) and "alguem" not in str(recusa.value)


def test_resposta_sem_pessoa_passa_inteira():
    corpo = {"companies": [{"cnpj": "11111111000191", "legal_name": {"value": "ALFA"}}]}
    assert saida.preparar_saida(corpo) == corpo


# ---------------------------------------------------------------- texto e tamanho


def test_limpa_invisiveis_e_mantem_quebra_de_linha_e_acento():
    sujo = {"name\u200b": ["Fábrica\u202e de\x00 Pão\n\tLtda\ufeff\U000e0041"]}
    assert saida.limpar_texto(sujo) == {"name": ["Fábrica de Pão\n\tLtda"]}


def test_numero_booleano_e_nulo_passam_como_vieram():
    assert saida.limpar_texto([1, 2.5, True, None]) == [1, 2.5, True, None]


def test_resposta_grande_demais_e_recusada():
    corpo = {"notes": ["x" * saida.TETO_DE_CARACTERES]}
    with pytest.raises(saida.RespostaGrandeDemais) as grande:
        saida.preparar_saida(corpo)
    assert grande.value.tamanho > saida.TETO_DE_CARACTERES


def test_acento_conta_um_caractere():
    assert saida.tamanho_em_caracteres("ção") == len('"ção"')


# ---------------------------------------------------------------- o conector fica de fora do app


def _importados(arquivo: Path) -> set[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes |= {apelido.name.split(".")[0] for apelido in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module and not no.level:
            nomes.add(no.module.split(".")[0])
    return nomes


@pytest.mark.parametrize(
    "arquivo", sorted(PASTA_DO_CONECTOR.glob("*.py")), ids=lambda a: a.name
)
def test_o_conector_nao_importa_o_app(arquivo):
    # o contêiner do conector não leva src/, base/ nem telas/: nada de acervo, banco ou segredo do app
    assert not _importados(arquivo) & {
        "src",
        "base",
        "telas",
        "trader",
        "scripts",
        "app",
    }


def test_formato_da_chave_e_o_da_api():
    assert FORMATO_DA_CHAVE.pattern == chaves_da_api.FORMATO.pattern
