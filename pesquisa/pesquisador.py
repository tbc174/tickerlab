"""O bot de pesquisa por inteiro, sem a camada MCP: abrir a rodada, buscar página, baixar documento,
extrair texto ou tabela e validar um fato contra o original.

O servidor MCP (`servidor_mcp.py`) só chama estes métodos; assim os testes e o `codex exec` falam
com a mesma coisa, e o núcleo roda sem o pacote `mcp`.
"""

import re
from dataclasses import asdict
from pathlib import Path

from pesquisa import evidencia, leitores
from pesquisa.coletor import AVISO_DE_CONTEUDO, Cliente, Coletor, Renderizador
from pesquisa.memoria import Memoria
from pesquisa.rodada import Limites, Rodada

HASH = re.compile(r"[0-9a-f]{64}")
SEM_RODADA = {
    "ok": False,
    "motivo": "nenhuma rodada aberta: chame iniciar_rodada(hipotese) com UMA hipótese",
}


class Pesquisador:
    """Guarda a memória e os documentos em `pasta`; uma rodada de cada vez."""

    def __init__(
        self,
        pasta: Path,
        cliente: Cliente,
        *,
        renderizador: Renderizador | None = None,
        limites: Limites | None = None,
    ) -> None:
        self.pasta = pasta
        self.cliente = cliente
        self.renderizador = renderizador
        self.limites = limites or Limites()
        self.memoria = Memoria(pasta / "memoria.sqlite")
        self.rodada: Rodada | None = None
        self.coletor: Coletor | None = None

    def iniciar_rodada(self, hipotese: str) -> dict[str, object]:
        """Abre uma rodada nova (a anterior é encerrada): uma hipótese, os limites e o relógio."""
        if not hipotese.strip():
            return {"ok": False, "motivo": "a rodada precisa de uma hipótese escrita"}
        self.rodada = Rodada(hipotese.strip(), self.limites)
        self.coletor = Coletor(
            self.cliente,
            self.memoria,
            self.pasta,
            self.rodada,
            renderizador=self.renderizador,
        )
        return {"ok": True, **self.rodada.resumo(), "aviso": AVISO_DE_CONTEUDO}

    def buscar_pagina(
        self, url: str, renderizar: bool = False, forcar: bool = False
    ) -> dict[str, object]:
        if self.coletor is None:
            return dict(SEM_RODADA)
        return self.coletor.buscar_pagina(url, renderizar=renderizar, forcar=forcar)

    def baixar_documento(self, url: str, forcar: bool = False) -> dict[str, object]:
        if self.coletor is None:
            return dict(SEM_RODADA)
        return self.coletor.baixar_documento(url, forcar=forcar)

    def extrair(
        self,
        sha256: str,
        *,
        motor: str = "auto",
        pagina_inicial: int = 1,
        pagina_final: int | None = None,
        linha_inicial: int = 1,
        planilha: str | None = None,
        contem: list[str] | None = None,
    ) -> dict[str, object]:
        """Lê o texto e as tabelas de um original já baixado, com o lugar de cada trecho."""
        arquivo = self._original(sha256)
        if isinstance(arquivo, dict):
            return arquivo
        if motor not in {"auto", "docling"}:
            return {"ok": False, "motivo": "motor é 'auto' ou 'docling'"}
        if motor == "docling" and not leitores.docling_instalado():
            return {
                "ok": False,
                "motivo": "o Docling não está instalado neste ambiente",
            }
        extracao = leitores.extrair(
            arquivo,
            motor=motor,
            pagina_inicial=max(pagina_inicial, 1),
            pagina_final=pagina_final,
            linha_inicial=max(linha_inicial, 1),
            planilha=planilha,
            contem=tuple(contem or ()),
        )
        return {
            "ok": True,
            "sha256": sha256,
            "tipo": extracao.tipo,
            "motor": extracao.motor,
            "blocos": [asdict(bloco) for bloco in extracao.blocos],
            "tabelas": [asdict(tabela) for tabela in extracao.tabelas],
            "truncado": extracao.truncado,
            "planilhas": extracao.planilhas,
            "avisos": extracao.avisos,
            "aviso": AVISO_DE_CONTEUDO,
        }

    def validar_fato(
        self,
        afirmacao: str,
        valor: str,
        trecho: str,
        sha256: str,
        posicao: str | None = None,
        exigir_no_trecho: list[str] | None = None,
    ) -> dict[str, object]:
        """Confere se o trecho está literalmente no original e se o valor e os itens exigidos
        (CNPJ, ano...) estão dentro dele. Registra o veredito na memória."""
        arquivo = self._original(sha256)
        if isinstance(arquivo, dict):
            return arquivo
        fato = evidencia.Fato(
            afirmacao,
            valor,
            trecho,
            sha256,
            posicao,
            tuple(exigir_no_trecho or ()),
        )
        veredito = evidencia.validar(fato, arquivo)
        rodada = self.rodada
        self.memoria.registrar_fato(
            rodada.identificador if rodada else "sem-rodada",
            rodada.hipotese if rodada else "",
            asdict(fato),
            veredito.situacao,
            veredito.motivos,
        )
        return {"ok": True, **veredito.para_dict()}

    def estado(self) -> dict[str, object]:
        """O que a rodada já gastou e o que a memória guarda."""
        resumo = self.rodada.resumo() if self.rodada else {"rodada": None}
        return {"ok": True, **resumo, "memoria": self.memoria.contagens()}

    def _original(self, sha256: str) -> Path | dict[str, object]:
        """O arquivo com este hash, ou a resposta de erro (hash inválido ou nunca baixado)."""
        sha = sha256.strip().lower()
        if not HASH.fullmatch(sha):
            return {
                "ok": False,
                "motivo": "sha256 inválido (64 caracteres hexadecimais)",
            }
        pasta = self.coletor.documentos if self.coletor else self.pasta / "documentos"
        for candidato in pasta.glob(f"{sha}.*"):
            if candidato.suffix != ".json":
                return candidato
        return {
            "ok": False,
            "motivo": "não há original com este sha256: use baixar_documento ou buscar_pagina",
        }
