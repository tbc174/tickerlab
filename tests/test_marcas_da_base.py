"""O levantamento das marcas de licença das tabelas da base (ADR 0008, Emenda 1; ADR 0102): só lê."""

import pandas as pd

from base.parquet import gravar_tabela
from scripts import marcas_da_base

URL_CVM = "https://dados.cvm.gov.br/dados/x.zip"
URL_WAYBACK = "https://web.archive.org/web/2025/x"
URL_B3 = "https://arquivos.b3.com.br/rapinegocios/tickercsv/2026-10-15"


def _gravar(destino, url):
    tabela = pd.DataFrame({"chave": ["1"]})
    return gravar_tabela(tabela, destino, [{"url": url, "sha256": "a" * 64}], ["chave"])


def test_lista_as_barradas_primeiro_e_junta_os_anos(tmp_path, capsys):
    base = tmp_path / "base"
    _gravar(base / "demonstracoes" / "2023", URL_CVM)
    _gravar(base / "demonstracoes" / "2024", URL_CVM)
    _gravar(base / "ma" / "datas" / "negocios", URL_WAYBACK)
    _gravar(base / "b3" / "negocios", URL_B3)
    (base / "demonstracoes" / "2024.v2.parquet").write_bytes(
        b""
    )  # versão antiga: fica de fora
    assert marcas_da_base.main(["--base", str(base)]) == 0
    linhas = capsys.readouterr().out.splitlines()
    # fora dos usos (a B3) primeiro; a marca das outras é informação (ADR 0102)
    assert linhas[0].startswith("nao_comercial  b3/negocios  [b3=nao_comercial]")
    assert linhas[1].startswith("vendavel       demonstracoes  [cvm=vendavel]")
    assert linhas[2].startswith(
        "nao_comercial  ma/datas/negocios  [wayback=nao_comercial]"
    )
    assert (
        linhas[-1] == "3 tabelas; 1 fora dos usos (B3); a base inteira: nao_comercial"
    )


def test_so_barradas(tmp_path):
    base = tmp_path / "base"
    _gravar(base / "cadastro" / "cadastro", URL_CVM)
    texto = marcas_da_base.em_texto(
        marcas_da_base.licencas_por_tabela(base), so_barradas=True
    )
    assert texto == "1 tabelas; 0 fora dos usos (B3); a base inteira: vendavel"
