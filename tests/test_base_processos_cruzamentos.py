"""Processos citados nas notas da DFP e contagens por companhia (plano dos processos judiciais, PR 1c)."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import numero_cnj, processos
from base.parquet import gravar_tabela

AGORA = datetime(2026, 11, 4, 12, tzinfo=UTC)
CNPJ = "00.000.000/0001-91"


def _numero(sequencial: int, segmento: str = "8", tribunal: str = "26") -> str:
    """Um número CNJ com o dígito certo, com a máscara."""
    partes = (f"{sequencial:07d}", "2019", segmento, tribunal, "0100")
    digito = numero_cnj.digito_esperado(*partes)
    return numero_cnj.decodificar(f"{partes[0]}{digito}{''.join(partes[1:])}").formatado


def _sem_mascara(numero: str) -> str:
    return numero_cnj.decodificar(numero).algarismos


def _errado(numero: str) -> str:
    """O mesmo número com o dígito verificador trocado."""
    digito = numero[8:10]
    return numero[:8] + f"{(int(digito) + 1) % 100:02d}" + numero[10:]


def _pagina(texto: str, pagina: int = 1, versao: int = 1, **outros) -> dict:
    return {
        "cnpj": CNPJ,
        "empresa": "ENERGIA EXEMPLO S.A.",
        "referencia": date(2025, 12, 31),
        "versao": versao,
        "pagina": pagina,
        "texto": texto,
        "disponivel_em": date(2026, 3, 20),
        "link": "http://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&numProtocolo=1",
        "ano_do_arquivo": 2025,
        "origem_sha256": "a" * 64,
        "origem_coletada_em": "2026-03-21T03:00:00+00:00",
    } | outros


def test_numeros_no_texto_so_os_que_conferem():
    civel, federal, sem_mascara = _numero(1), _numero(2, "4", "03"), _numero(3)
    texto = (
        f"Ação anulatória (processo nº {civel}), execução fiscal {federal}, "
        f"autos {_sem_mascara(sem_mascara)} e o número com erro {_errado(_numero(4))}; "
        f"o mesmo {civel} de novo."
    )
    assert processos.numeros_no_texto(texto) == sorted({civel, federal, sem_mascara})


def test_numeros_no_texto_deixa_a_justica_do_trabalho_de_fora():
    """A Justiça do Trabalho fica fora da base inteira (Res. CNJ 121/2010), também na citação."""
    assert processos.numeros_no_texto(f"reclamação {_numero(5, '5', '02')}") == []


def test_numeros_no_texto_aceita_o_numero_quebrado_pelo_pdf():
    numero = _numero(6)
    quebrado = numero.replace("-", " - ").replace(".2019.", ".2019.\n")
    assert processos.numeros_no_texto(quebrado) == [numero]


def test_tabela_das_citacoes_uma_linha_por_numero_e_pagina():
    a, b = _numero(7), _numero(8, "4", "01")
    notas = pd.DataFrame(
        [
            _pagina(f"{a} e {a}", pagina=40),
            _pagina(f"{a} e {b}", pagina=41),
            _pagina("sem processo", pagina=42),
            # a reapresentação é outro documento: cita de novo, com a própria entrega
            _pagina(f"{a}", pagina=40, versao=2, disponivel_em=date(2026, 5, 2)),
        ]
    )

    citacoes = processos.tabela_das_citacoes(notas)

    assert citacoes[["numero_processo", "pagina", "versao"]].values.tolist() == [
        [a, 40, 1],
        [a, 41, 1],
        [b, 41, 1],
        [a, 40, 2],
    ]
    assert "texto" not in citacoes
    linha = citacoes.iloc[2]
    assert (linha["justica"], linha["ano_do_processo"]) == ("Justiça Federal", 2019)
    assert citacoes["disponivel_em"].tolist()[-1] == date(2026, 5, 2)
    assert citacoes["cnpj"].unique().tolist() == [CNPJ]


def test_tabela_das_citacoes_vazia_tem_as_colunas():
    citacoes = processos.tabela_das_citacoes(pd.DataFrame([_pagina("nada")]))
    assert citacoes.empty
    assert list(citacoes.columns) == processos.COLUNAS_DAS_CITACOES


@pytest.mark.parametrize(
    "corte", ["2026-03-19", "2026-03-20", "2026-04-30", "2026-05-02"]
)
def test_cortar_o_futuro_nao_muda_as_citacoes(corte: str):
    a = _numero(9)
    paginas = [
        _pagina(a, pagina=10),
        _pagina(a, pagina=10, versao=2, disponivel_em=date(2026, 5, 2)),
        _pagina(
            _numero(10),
            pagina=11,
            cnpj="11.111.111/0001-11",
            disponivel_em=date(2026, 4, 1),
        ),
    ]
    dia = date.fromisoformat(corte)

    def ate(tabela: pd.DataFrame) -> pd.DataFrame:
        return tabela[tabela["disponivel_em"] <= dia].reset_index(drop=True)

    com_tudo = processos.tabela_das_citacoes(pd.DataFrame(paginas))
    so_o_passado = processos.tabela_das_citacoes(
        pd.DataFrame([p for p in paginas if p["disponivel_em"] <= dia])
    )
    pd.testing.assert_frame_equal(ate(com_tudo), ate(so_o_passado), check_dtype=False)


def _partes(*linhas: tuple[str, str, str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "numero_processo": numero,
                "tipo_parte": processos.COMPANHIA,
                "cnpj": cnpj,
                "polo": polo,
                "disponivel_em": pd.Timestamp(dia),
            }
            for numero, cnpj, polo, dia in linhas
        ]
    )


def test_contagens_por_companhia_e_ano():
    a, b, c = _numero(11), _numero(12), _numero(13)
    partes = pd.concat(
        [
            _partes(
                (a, CNPJ, "passivo", "2025-03-01"),
                (
                    a,
                    CNPJ,
                    "passivo",
                    "2026-01-10",
                ),  # a mesma ligação, outra comunicação
                (b, CNPJ, "ativo", "2026-02-01"),
                (c, CNPJ, "passivo", "2026-06-01"),
                (c, "11.111.111/0001-11", "ativo", "2026-06-01"),
            ),
            pd.DataFrame(
                [
                    {
                        "numero_processo": a,
                        "tipo_parte": processos.ORGAO_PUBLICO,
                        "cnpj": None,
                        "polo": "ativo",
                        "disponivel_em": pd.Timestamp("2025-03-01"),
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    dos_processos = pd.DataFrame(
        {
            "numero_processo": [a, b, c],
            "ramo": ["execucao_fiscal", "conhecimento", None],
        }
    )
    citacoes = pd.DataFrame(
        {"numero_processo": [c], "cnpj": [CNPJ], "disponivel_em": [date(2026, 3, 20)]}
    )

    contagem = processos.contagens(
        partes, dos_processos, citacoes, como_era_em="2026-12-31"
    )

    da_companhia = contagem[contagem["cnpj"] == CNPJ].set_index("ano")
    assert da_companhia.loc[2025, ["processos", "como_re", "como_autora"]].tolist() == [
        1,
        1,
        0,
    ]
    assert da_companhia.loc[2026, ["processos", "como_re", "como_autora"]].tolist() == [
        2,
        1,
        1,
    ]
    assert da_companhia.loc[2025, "execucao_fiscal"] == 1
    assert da_companhia.loc[2026, "sem_ramo"] == 1
    assert da_companhia.loc[2026, "citados_na_dfp"] == 1
    # a contagem de um dia só usa o que já era público nele
    antes = processos.contagens(
        partes, dos_processos, citacoes, como_era_em="2026-03-01"
    )
    da_companhia = antes[antes["cnpj"] == CNPJ].set_index("ano")
    assert da_companhia.loc[2026, ["processos", "citados_na_dfp"]].tolist() == [1, 0]


def test_montar_citacoes_le_as_notas_pela_porta(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    pasta = tmp_path / "base"
    numero = _numero(14)
    gravar_tabela(
        pd.DataFrame([_pagina(f"processo {numero}")]).assign(
            montado_em=AGORA.isoformat(), versao_do_codigo="x"
        ),
        pasta / "notas_dfp" / "2025",
        [{"url": "http://exemplo/enet", "sha256": "b" * 64}],
        ["cnpj", "referencia", "versao", "pagina"],
    )

    resumo = processos.montar_citacoes(pasta, AGORA)
    de_novo = processos.montar_citacoes(pasta, AGORA)

    assert resumo == {"paginas": 1, "citacoes": 1, "processos": 1, "companhias": 1}
    assert de_novo == processos.JA_MONTADO
    gravada = pd.read_parquet(pasta / "processos_nas_notas" / "dfp.parquet")
    assert gravada["numero_processo"].tolist() == [numero]
    assert gravada["versao_do_codigo"].iloc[0] == "0123abc"
    manifesto = json.loads(
        (pasta / "processos_nas_notas" / "dfp.json").read_text(encoding="utf-8")
    )
    assert manifesto["conferencia_do_contrato"]["aprovada"]
    assert "notas_dfp/2025" in json.dumps(manifesto["origens"])


def test_montar_citacoes_sem_notas_nao_grava(tmp_path: Path):
    assert processos.montar_citacoes(tmp_path / "base", AGORA) == {}
    assert not (tmp_path / "base" / "processos_nas_notas").exists()
