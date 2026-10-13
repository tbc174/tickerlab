"""Novidades (o que entrou e o que foi corrigido em cada atualização): um lugar só para a página do
site e para a nota da versão no GitHub."""

from datetime import date

from scripts import nota_da_versao
from src import novidades


def test_atualizacoes_do_mais_novo_ao_mais_velho_e_completas():
    datas = [a.data for a in novidades.ATUALIZACOES]
    assert datas == sorted(datas, reverse=True)
    assert len(set(datas)) == len(datas)  # uma atualização por dia
    for a in novidades.ATUALIZACOES:
        assert a.titulo and a.novidades
        assert all(t.endswith(".") for t in (*a.novidades, *a.correcoes)), a.data


def test_textos_publicos_nao_prometem_nem_recomendam():
    proibidos = ("recomend", "garant", "lucro certo", "rentabilidade garantida")
    for a in novidades.ATUALIZACOES:
        texto = " ".join((a.titulo, a.resumo, *a.novidades, *a.correcoes)).lower()
        assert not any(p in texto for p in proibidos), a.data


def test_como_lista_e_json_simples():
    (primeira, *_) = novidades.como_lista()
    assert set(primeira) == {"data", "titulo", "resumo", "novidades", "correcoes"}
    assert primeira["data"] == novidades.ATUALIZACOES[0].data.isoformat()


def test_nota_da_versao_em_markdown():
    texto = nota_da_versao.nota(novidades.ATUALIZACOES[0])
    assert texto.startswith("## ")
    assert "### Novidades" in texto and "- " in texto
    assert "tickerlab.com.br/novidades.html" in texto


def test_nota_de_um_dia_sem_atualizacao_falha():
    assert nota_da_versao.main(["1999-01-01"]) == 1
    assert nota_da_versao.main([date(2026, 10, 13).isoformat()]) == 0


def test_nota_da_versao_grava_em_utf8_com_saida(tmp_path):
    """No Windows a saída padrão não é UTF-8: `--saida` grava o arquivo sem depender do terminal."""
    arquivo = tmp_path / "nota.md"
    dia = novidades.ATUALIZACOES[0].data
    assert nota_da_versao.main([dia.isoformat(), "--saida", str(arquivo)]) == 0
    texto = arquivo.read_bytes().decode("utf-8")
    assert texto == nota_da_versao.nota(novidades.ATUALIZACOES[0])
    assert "\r\n" not in texto
