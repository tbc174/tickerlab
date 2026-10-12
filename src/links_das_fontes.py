"""Links dos documentos públicos (CVM e SEC): só endereços seguros viram link ou download.

Os links da SEC são montados pelo próprio app; os da CVM vêm prontos nos arquivos dela. Antes de
um link aparecer na tela, no PDF, no e-mail da Newsletter ou de o app baixar o documento (resumo
dos fatos relevantes), ele passa por aqui: só `https` de um domínio da CVM ou da SEC. Assim, um
endereço estranho num arquivo de fonte (outro site, `javascript:`, um endereço interno) nunca vira
link nem faz o servidor baixar algo de outro lugar.
"""

from urllib.parse import urlsplit

DOMINIOS_DAS_FONTES = ("cvm.gov.br", "sec.gov")
PROTOCOLOS_ACEITOS = (
    "https",
    "http",
)  # http é promovido a https (arquivos antigos da CVM)


def _dominio_das_fontes(host: str) -> bool:
    return any(
        host == dominio or host.endswith("." + dominio)
        for dominio in DOMINIOS_DAS_FONTES
    )


def link_da_fonte(link: str | None) -> str | None:
    """O link em `https`, se for de um domínio da CVM ou da SEC; senão None (não mostrar)."""
    try:
        partes = urlsplit((link or "").strip())
        host = (partes.hostname or "").lower()
    except ValueError:  # endereço malformado (ex.: colchete sem fechar)
        return None
    if partes.scheme.lower() not in PROTOCOLOS_ACEITOS or not _dominio_das_fontes(host):
        return None
    if partes.username or partes.password or partes.port not in (None, 443):
        return None  # "https://cvm.gov.br@outro.site" ou porta estranha
    return partes._replace(scheme="https").geturl()
