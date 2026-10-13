"""Só links seguros das fontes públicas (CVM e SEC) viram link ou download (achado S-4, Master v3)."""

import pytest

from src.links_das_fontes import link_da_fonte

CVM = (
    "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&numProtocolo=1"
)
SEC = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"


@pytest.mark.parametrize("link", [CVM, SEC, "https://sec.gov/x", "https://cvm.gov.br/"])
def test_links_da_cvm_e_da_sec_passam_iguais(link):
    assert link_da_fonte(link) == link


def test_http_da_cvm_vira_https():
    assert link_da_fonte(CVM.replace("https://", "http://")) == CVM


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(1)",
        "https://exemplo.com/documento.pdf",
        "https://cvm.gov.br.outro.site/x",  # termina com outro domínio
        "https://falsacvm.gov.br/x",  # parece, mas não é um subdomínio
        "https://www.cvm.gov.br@outro.site/x",  # usuário no endereço
        "https://www.sec.gov:8443/x",  # porta estranha
        "ftp://www.sec.gov/x",
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data/",  # endereço interno de nuvem
        "https://[::1",  # malformado
        "",
        None,
    ],
)
def test_qualquer_outro_endereco_e_recusado(link):
    assert link_da_fonte(link) is None
