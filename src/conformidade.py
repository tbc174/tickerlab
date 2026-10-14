"""Privacidade e LGPD: aceite dos termos, exportar os meus dados e apagar a minha conta.

Os textos dos termos e da política ficam em `conteudo/`. Quando mudarem de forma relevante, suba
`VERSAO_DOS_TERMOS`: todo mundo precisa aceitar de novo no próximo acesso.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa

from src import auditoria
from src.banco.compartilhamentos import dados_para_exportar as links_para_exportar
from src.banco.modelo import (
    alertas,
    assinaturas,
    carteiras_do_research,
    envios_da_newsletter,
    envios_de_novidades,
    favoritos,
    inscricoes_da_newsletter,
    inscricoes_de_novidades,
    pdfs_originais,
    preferencias,
    presets,
    relatorios,
    simulacoes,
    usuarios,
    watchlists,
)
from src.banco.origens import buscar_linha as buscar_origem_do_cadastro
from src.banco.pulse import dados_para_exportar as pulse_para_exportar
from src.banco.tentativas import contar_por_ativo
from src.banco.teses import dados_para_exportar as diario_para_exportar
from src.banco.usuarios import Usuario

# versão 2: Plus, relatórios, acesso aberto, Cloudflare. Versão 4: Research completo (carteira,
# alertas, Newsletter por e-mail; o texto 3 entrou sem novo aceite) e cópias de segurança cifradas.
# Versão 5: o PDF original dos relatórios fica guardado na biblioteca (ADR 0021). Versão 6: o
# TickerLab se apresenta como produto por assinatura, não mais como projeto educacional. Versão 7:
# a contagem das tentativas do backtest (ficha "Foi sorte?", só a impressão SHA-256)
# (as Novidades por e-mail, 14/10, entraram sem novo aceite: o consentimento delas é à parte)
VERSAO_DOS_TERMOS = "2026-10-13.7"
PASTA_DOS_TEXTOS = Path(__file__).resolve().parent.parent / "conteudo"
TEXTO_PARA_CONFIRMAR_A_EXCLUSAO = "APAGAR"


def carregar_texto(nome: str) -> str:
    """Lê um texto legal de `conteudo/` (`termos` ou `privacidade`)."""
    if nome not in ("termos", "privacidade"):
        raise ValueError(f"Texto desconhecido: {nome}.")
    return (PASTA_DOS_TEXTOS / f"{nome}.md").read_text(encoding="utf-8")


def precisa_aceitar_os_termos(usuario: Usuario) -> bool:
    return usuario.termos_versao != VERSAO_DOS_TERMOS


def registrar_aceite(conexao: sa.Connection, usuario_id: uuid.UUID) -> None:
    conexao.execute(
        sa.update(usuarios)
        .where(usuarios.c.id == usuario_id)
        .values(termos_versao=VERSAO_DOS_TERMOS, termos_aceitos_em=datetime.now(UTC))
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_TERMOS_ACEITOS,
        usuario_id,
        {"versao": VERSAO_DOS_TERMOS},
    )


def _texto(valor: object) -> object:
    return valor.isoformat() if isinstance(valor, datetime) else valor


def _origem_do_cadastro(conexao: sa.Connection, usuario_id: uuid.UUID) -> dict | None:
    linha = buscar_origem_do_cadastro(conexao, usuario_id)
    if linha is None:
        return None
    primeira_visita = linha.primeira_visita
    return {
        "utm_source": linha.utm_source,
        "utm_medium": linha.utm_medium,
        "utm_campaign": linha.utm_campaign,
        "utm_content": linha.utm_content,
        "ref": linha.ref,
        "primeira_visita": primeira_visita.isoformat() if primeira_visita else None,
        "gravada_em": _texto(linha.gravada_em),
    }


def exportar_meus_dados(conexao: sa.Connection, usuario_id: uuid.UUID) -> dict:
    """Tudo o que o serviço guarda sobre a pessoa, em um dicionário pronto para virar JSON.

    Só entram dados da própria pessoa (filtrados pelo id). Ids internos do Stripe ficam de fora.
    """
    perfil = conexao.execute(
        sa.select(usuarios).where(usuarios.c.id == usuario_id)
    ).first()
    if perfil is None:
        raise LookupError("Usuário não encontrado.")
    prefs = conexao.execute(
        sa.select(preferencias.c.dados).where(preferencias.c.usuario_id == usuario_id)
    ).first()
    assinatura = conexao.execute(
        sa.select(assinaturas).where(assinaturas.c.usuario_id == usuario_id)
    ).first()
    auditoria.registrar(
        conexao, usuario_id, auditoria.ACAO_DADOS_EXPORTADOS, usuario_id, {}
    )
    return {
        "exportado_em": datetime.now(UTC).isoformat(),
        "perfil": {
            "email": perfil.email,
            "nome": perfil.nome,
            "foto_url": perfil.foto_url,
            "papel": perfil.papel,
            "plano": perfil.plano,
            "criado_em": _texto(perfil.criado_em),
            "ultimo_acesso": _texto(perfil.ultimo_acesso),
            "termos_aceitos": {
                "versao": perfil.termos_versao,
                "em": _texto(perfil.termos_aceitos_em),
            },
        },
        "preferencias": dict(prefs.dados) if prefs else {},
        "tentativas_por_ativo": contar_por_ativo(conexao, usuario_id),
        "pulse": pulse_para_exportar(conexao, usuario_id),
        "diario_de_teses": diario_para_exportar(conexao, usuario_id),
        "links_compartilhados": links_para_exportar(conexao, usuario_id),
        "origem_do_cadastro": _origem_do_cadastro(conexao, usuario_id),
        "favoritos": [
            l.ticker
            for l in conexao.execute(
                sa.select(favoritos.c.ticker)
                .where(favoritos.c.usuario_id == usuario_id)
                .order_by(favoritos.c.ordem)
            )
        ],
        "simulacoes": [
            {
                "nome": l.nome,
                "tipo": l.tipo,
                "criada_em": _texto(l.criada_em),
                "parametros": dict(l.parametros),
                "resultado": dict(l.resultado),
            }
            for l in conexao.execute(
                sa.select(simulacoes)
                .where(simulacoes.c.usuario_id == usuario_id)
                .order_by(simulacoes.c.criada_em)
            )
        ],
        "alertas_do_research": [
            {
                "nome": l.nome,
                "regra": dict(l.regra),
                "criado_em": _texto(l.criado_em),
                "atualizado_em": _texto(l.atualizado_em),
            }
            for l in conexao.execute(
                sa.select(alertas)
                .where(alertas.c.usuario_id == usuario_id)
                .order_by(alertas.c.criado_em)
            )
        ],
        "carteira_do_research": [
            {
                "pesos": dict(l.pesos),
                "enviada_em": _texto(l.enviada_em),
                "versao_do_consentimento": l.versao_do_consentimento,
                "consentido_em": _texto(l.consentido_em),
            }
            for l in conexao.execute(
                sa.select(carteiras_do_research).where(
                    carteiras_do_research.c.usuario_id == usuario_id
                )
            )
        ],
        "newsletter_por_email": [
            {
                "lista": l.lista,
                "cadencia": l.cadencia,
                "versao_do_consentimento": l.versao_do_consentimento,
                "inscrito_em": _texto(l.inscrito_em),
            }
            for l in conexao.execute(
                sa.select(inscricoes_da_newsletter).where(
                    inscricoes_da_newsletter.c.usuario_id == usuario_id
                )
            )
        ],
        "envios_da_newsletter": [
            {
                "periodo": l.periodo,
                "situacao": l.situacao,
                "registrado_em": _texto(l.registrado_em),
            }
            for l in conexao.execute(
                sa.select(envios_da_newsletter)
                .where(envios_da_newsletter.c.usuario_id == usuario_id)
                .order_by(envios_da_newsletter.c.registrado_em)
            )
        ],
        "novidades_por_email": [
            {
                "versao_do_consentimento": l.versao_do_consentimento,
                "inscrito_em": _texto(l.inscrito_em),
            }
            for l in conexao.execute(
                sa.select(inscricoes_de_novidades).where(
                    inscricoes_de_novidades.c.usuario_id == usuario_id
                )
            )
        ],
        "envios_de_novidades": [
            {
                "campanha": l.campanha,
                "situacao": l.situacao,
                "registrado_em": _texto(l.registrado_em),
            }
            for l in conexao.execute(
                sa.select(envios_de_novidades)
                .where(envios_de_novidades.c.usuario_id == usuario_id)
                .order_by(envios_de_novidades.c.registrado_em)
            )
        ],
        "listas_do_research": [
            {
                "nome": l.nome,
                "tickers": list(l.tickers),
                "criada_em": _texto(l.criado_em),
                "atualizada_em": _texto(l.atualizado_em),
            }
            for l in conexao.execute(
                sa.select(watchlists)
                .where(watchlists.c.usuario_id == usuario_id)
                .order_by(watchlists.c.criado_em)
            )
        ],
        "parametros_do_research": [
            {
                "escopo": l.escopo,
                "alvo": l.alvo,
                "versao": l.versao,
                "nome": l.nome,
                "parametros": dict(l.parametros),
                "motivo": l.motivo,
                "criado_em": _texto(l.criado_em),
            }
            for l in conexao.execute(
                sa.select(presets)
                .where(presets.c.usuario_id == usuario_id)
                .order_by(presets.c.escopo, presets.c.alvo, presets.c.versao)
            )
        ],
        "relatorios_em_pdf": [
            {
                "tipo": l.tipo,
                "criado_em": _texto(l.criado_em),
                "titulo": l.titulo,
                "parametros": dict(l.parametros) if l.parametros else None,
                "excluido_da_biblioteca_em": _texto(l.apagado_em),
                # o arquivo em si vai no .zip "Baixar meus PDFs guardados"
                "pdf_original": (
                    {
                        "sha256": l.sha256,
                        "tamanho": l.tamanho,
                        "gerado_em": _texto(l.gerado_em),
                    }
                    if l.sha256
                    else None
                ),
            }
            for l in conexao.execute(
                sa.select(
                    relatorios.c.tipo,
                    relatorios.c.criado_em,
                    relatorios.c.titulo,
                    relatorios.c.parametros,
                    relatorios.c.apagado_em,
                    pdfs_originais.c.sha256,
                    pdfs_originais.c.tamanho,
                    pdfs_originais.c.gerado_em,
                )
                .select_from(
                    relatorios.outerjoin(
                        pdfs_originais,
                        (pdfs_originais.c.relatorio_id == relatorios.c.id)
                        & (pdfs_originais.c.usuario_id == usuario_id),
                    )
                )
                .where(relatorios.c.usuario_id == usuario_id)
                .order_by(relatorios.c.criado_em)
            )
        ],
        "assinatura": (
            {
                "status": assinatura.status,
                "periodo_fim": _texto(assinatura.periodo_fim),
                "cancela_no_fim": assinatura.cancela_no_fim,
            }
            if assinatura
            else None
        ),
    }


def apagar_conta(conexao: sa.Connection, usuario_id: uuid.UUID) -> bool:
    """Apaga a pessoa e tudo o que é dela (em cascata) e deixa só um registro sem dado pessoal.

    Devolve se havia o que apagar. A cobrança no Stripe é encerrada por quem chama
    (`cobranca.encerrar_cobranca`), antes desta função, porque envolve a internet.
    """
    existia = (
        conexao.execute(sa.delete(usuarios).where(usuarios.c.id == usuario_id)).rowcount
        > 0
    )
    if existia:
        auditoria.registrar(conexao, None, auditoria.ACAO_CONTA_APAGADA, usuario_id, {})
    return existia
