"""Uma base do CNPJ de exemplo (o formato de `scripts.carga_receita_mes`), para montar a vista nos testes.

Duas empresas fechadas: uma limitada com matriz e filial, um sócio pessoa física administrador desde 03/2019 e
um sócio pessoa jurídica; e um MEI com endereço completo e contatos na base (a vista não pode levar nada disso).
O nome do sócio pessoa física fica no restrito, como na base de verdade.
"""

import json
from pathlib import Path

import pandas as pd

from base import cnpj as cnpj_da_base

LIMITADA = "12345678"
MEI = "98765432"
SOCIO_PJ = "33000167"
NOME_DO_SOCIO = "FULANA DE TAL SOBRENOME"
ID_DO_SOCIO = "f0a1b2c3d4e5f6a7"
RUA_DO_MEI = "RUA DA CASA DO MEI"
CEP_DO_MEI = "01310100"
TELEFONE_DO_MEI = "998887766"
EMAIL_DO_MEI = "mei@exemplo.com.br"
MESES = ("2023-09", "2023-10", "2024-08", "2024-09")
ULTIMO_MES = MESES[-1]


def cnpj(raiz: str, ordem: str = "0001") -> str:
    base = raiz + ordem
    return base + cnpj_da_base.digitos_verificadores(base)


def _data(texto: str | None) -> pd.Timestamp:
    return pd.Timestamp(texto) if texto else pd.NaT


def _estabelecimento(raiz: str, ordem: str, **campos) -> dict:
    linha = {
        "cnpj": cnpj(raiz, ordem),
        "cnpj_basico": raiz,
        "matriz": ordem == "0001",
        "situacao_cadastral": "02",
        "data_situacao_cadastral": _data("2010-02-01"),
        "motivo_situacao": "00",
        "pais": "",
        "data_inicio_atividade": _data("2010-02-01"),
        "cnae_principal": "6201501",
        "cnae_secundaria": "6202300",
        "tipo_logradouro": "RUA",
        "logradouro": "DAS EMPRESAS",
        "numero": "100",
        "complemento": "SALA 1",
        "bairro": "CENTRO",
        "cep": "01001000",
        "uf": "SP",
        "municipio": "7107",
        "situacao_especial": "",
        "data_situacao_especial": pd.NaT,
        "dv_confere": True,
    }
    return linha | campos


def _estabelecimentos() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _estabelecimento(LIMITADA, "0001"),
            _estabelecimento(
                LIMITADA,
                "0002",
                situacao_cadastral="08",
                data_situacao_cadastral=_data("2024-09-02"),
                motivo_situacao="01",
                uf="RJ",
                municipio="6001",
            ),
            _estabelecimento(
                MEI,
                "0001",
                cnae_principal="9602501",
                logradouro=RUA_DO_MEI,
                cep=CEP_DO_MEI,
                situacao_especial="RECUPERACAO JUDICIAL",
                motivo_situacao="63",
                ddd_1="11",
                telefone_1=TELEFONE_DO_MEI,
                correio_eletronico=EMAIL_DO_MEI,
            ),
        ]
    )


def _simples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj_basico": LIMITADA,
                "optante_simples": True,
                "data_opcao_simples": _data("2024-08-01"),
                "data_exclusao_simples": pd.NaT,
                "optante_mei": False,
                "data_opcao_mei": pd.NaT,
                "data_exclusao_mei": pd.NaT,
            },
            {
                "cnpj_basico": MEI,
                "optante_simples": True,
                "data_opcao_simples": _data("2019-03-12"),
                "data_exclusao_simples": pd.NaT,
                "optante_mei": True,
                "data_opcao_mei": _data("2019-03-12"),
                "data_exclusao_mei": pd.NaT,
            },
        ]
    )


def _qsa() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj_basico": LIMITADA,
                "tipo_socio": "2",
                "qualificacao": "05",
                "data_entrada": _data("2019-03-15"),
                "pais": "",
                "raiz_socio_pj": "",
                "id_pessoa": ID_DO_SOCIO,
            },
            {
                "cnpj_basico": LIMITADA,
                "tipo_socio": "1",
                "qualificacao": "22",
                "data_entrada": _data("2024-08-05"),
                "pais": "",
                "raiz_socio_pj": SOCIO_PJ,
                "id_pessoa": "",
            },
        ]
    )


def _gravar_por_prefixo(tabela: pd.DataFrame, pasta: Path, coluna: str) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for prefixo, parte in tabela.groupby(tabela[coluna].str[:2]):
        parte.to_parquet(pasta / f"{prefixo}.parquet", index=False)


def _mudanca(mes: str, tipo: str, chaves: dict, antes: dict, depois: dict) -> dict:
    pares = {f"{c}_antes": v for c, v in antes.items()} | {
        f"{c}_depois": v for c, v in depois.items()
    }
    return {"mes": mes, "tipo": tipo, **chaves, "ordem": 0, **pares}


def _mudancas_dos_estabelecimentos() -> dict[str, pd.DataFrame]:
    filial = {"cnpj": cnpj(LIMITADA, "0002")}
    matriz = {"cnpj": cnpj(LIMITADA, "0001")}
    comum = {
        "situacao_cadastral": "02",
        "cnae_principal": "6201501",
        "uf": "SP",
        "municipio": "7107",
    }
    return {
        "2024-09": pd.DataFrame(
            [
                _mudanca(
                    "2024-09",
                    "mudou",
                    filial,
                    comum | {"logradouro": "A"},
                    comum | {"situacao_cadastral": "08", "logradouro": "A"},
                ),
                # só o endereço fino mudou: a vista não leva o endereço, então não leva a linha
                _mudanca(
                    "2024-09",
                    "mudou",
                    matriz,
                    comum | {"logradouro": "VELHA"},
                    comum | {"logradouro": "NOVA"},
                ),
            ]
        )
    }


def _mudancas_do_simples() -> dict[str, pd.DataFrame]:
    campos = {"optante_simples": False, "optante_mei": False}
    return {
        "2024-08": pd.DataFrame(
            [
                _mudanca(
                    "2024-08",
                    "mudou",
                    {"cnpj_basico": LIMITADA},
                    campos,
                    campos | {"optante_simples": True},
                )
            ]
        )
    }


def _mudancas_do_qsa() -> dict[str, pd.DataFrame]:
    def socio(tipo_socio, raiz_pj, id_pessoa):
        return {
            "cnpj_basico": LIMITADA,
            "tipo_socio": tipo_socio,
            "raiz_socio_pj": raiz_pj,
            "id_pessoa": id_pessoa,
        }

    vazio = {"qualificacao": None, "data_entrada": pd.NaT}
    pf = {"qualificacao": "05", "data_entrada": _data("2019-03-15")}
    return {
        # fora da janela de 12 meses (2024-09 menos 12 meses)
        "2023-09": pd.DataFrame(
            [_mudanca("2023-09", "saiu", socio("1", "11111111", ""), pf, vazio)]
        ),
        "2024-08": pd.DataFrame(
            [
                _mudanca(
                    "2024-08",
                    "entrou",
                    socio("1", SOCIO_PJ, ""),
                    vazio,
                    {"qualificacao": "22", "data_entrada": _data("2024-08-05")},
                )
            ]
        ),
        # o mesmo sócio com outro pseudônimo: sem o id, nada mudou (sai e entra igual)
        "2024-09": pd.DataFrame(
            [
                _mudanca("2024-09", "saiu", socio("2", "", "velho"), pf, vazio),
                _mudanca("2024-09", "entrou", socio("2", "", ID_DO_SOCIO), vazio, pf),
            ]
        ),
    }


def gravar_base(pasta: Path) -> Path:
    """A base do CNPJ de exemplo em `pasta` (vigente, mudanças e manifesto); devolve a pasta."""
    vigente = pasta / "vigente"
    _gravar_por_prefixo(
        _estabelecimentos(), vigente / "estabelecimentos", "cnpj_basico"
    )
    _gravar_por_prefixo(_simples(), vigente / "simples", "cnpj_basico")
    _gravar_por_prefixo(_qsa(), vigente / "qsa", "cnpj_basico")
    mudancas = {
        "estabelecimentos": _mudancas_dos_estabelecimentos(),
        "simples": _mudancas_do_simples(),
        "qsa": _mudancas_do_qsa(),
    }
    for tabela, por_mes in mudancas.items():
        (pasta / "mudancas" / tabela).mkdir(parents=True, exist_ok=True)
        for mes, linhas in por_mes.items():
            linhas.to_parquet(
                pasta / "mudancas" / tabela / f"{mes}.parquet", index=False
            )
    manifesto = {"meses": {mes: {"arquivos": {}} for mes in MESES}}
    (pasta / "manifesto.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return pasta


def gravar_restrito(pasta: Path) -> Path:
    """O restrito com o nome do sócio pessoa física (o que nunca pode sair com o portão fechado)."""
    destino = pasta / "pessoas" / LIMITADA[:2]
    destino.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "id_pessoa": ID_DO_SOCIO,
                "cnpj_basico": LIMITADA,
                "nome": NOME_DO_SOCIO,
                "cpf_mascarado": "***123456**",
            }
        ]
    ).to_parquet(destino / "parte.parquet", index=False)
    return pasta
