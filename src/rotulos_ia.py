"""Rótulos da fila das 21h feitos por IA e auditados às cegas pelo Tiago (ADR 0072).

A IA recebe o mesmo guia da página de rotulagem (versão `v2`) e devolve nota (1 a 5), tema e, nos
fatos relevantes, assunto. As proteções da ADR ficam aqui, sem rede:

- **sem o nome da empresa:** razão social, códigos de negociação e CNPJ viram `[EMPRESA]`, `[CODIGO]`
  e `[CNPJ]` antes de ir para o modelo, para ele não dar a nota pelo que sabe que aconteceu depois;
- **lista fechada** (saída estruturada) e um **trecho que tem de existir** no que o modelo leu;
  resposta fora disso vira erro, nunca um chute;
- cada rótulo guarda `por: "ia"`, o modelo e a versão do prompt, e nunca se mistura com os humanos.

O modelo foi escolhido pelo Tiago antes da auditoria (14/10/2026: Sonnet 5.5, teto de US$ 60); trocar
de modelo ou de prompt depois de ver a auditoria conta como uma tentativa nova (ADR 0006). Desde a
Emenda 1 (17/10/2026), o **Opus 5.5** rotula às cegas o conjunto de prova com o mesmo pedido, para
conferir o Sonnet no lugar do Tiago; os papéis ficam fixos (`MODELO` e `MODELO_CONFERENTE`).
"""

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass

import anthropic

from base.cnpj import dv_confere, normalizar_cnpj, tem_letra
from src import topicos

MODELO = "claude-sonnet-5-5"  # o rotulador da fila inteira (14/10)
MODELO_CONFERENTE = "claude-opus-5-5"  # o segundo modelo às cegas (Emenda 1, 17/10)
# chave criada fora de um workspace: a API pede o id do workspace em cada pedido (não é segredo)
VARIAVEL_DO_WORKSPACE = "ANTHROPIC_WORKSPACE_ID"
VERSAO_DO_PROMPT = "1"
GUIA = "v2"
MAX_CARACTERES_DO_TEXTO = 6_000  # o começo do documento, como no leitor (ADR 0069)
MAX_TOKENS_DA_RESPOSTA = 2_000  # a resposta é curta; a folga é para o raciocínio
FATO_RELEVANTE = "Fato Relevante"

DESCONTO_DO_LOTE = 0.5  # a Batch API cobra a metade


@dataclass(frozen=True)
class Modelo:
    """Preços em US$ por milhão de tokens. Ler do cache custa uma fração da entrada, que muda por
    modelo; escrever custa 1,25x em todos. A saída por evento é só para a estimativa (o real vem de
    `usage`)."""

    entrada: float
    saida: float
    leitura_do_cache: float
    saida_estimada_por_evento: int


MODELOS = {
    # Sonnet 5.5 (14/10/2026); saída medida no 1º lote (15/10): 59 por evento (167.640 em 2.849)
    MODELO: Modelo(2.00, 10.00, 0.1, 80),
    # Opus 5.5 (skill claude-api, 17/10/2026): cache lido a 0,05x. O raciocínio do Opus não desliga e
    # entra na saída: a estimativa usa o triplo do que o Sonnet gastou, até o piloto medir
    MODELO_CONFERENTE: Modelo(4.00, 20.00, 0.05, 180),
}


def modelo_conhecido(nome: str) -> Modelo:
    """O preço do modelo; um nome fora da lista é erro (nunca o preço de outro)."""
    if nome not in MODELOS:
        raise ValueError(
            f"Modelo sem preço cadastrado: {nome} (conhecidos: {', '.join(MODELOS)})"
        )
    return MODELOS[nome]


EMPRESA, CODIGO, CNPJ = "[EMPRESA]", "[CODIGO]", "[CNPJ]"
SEM_TEXTO = "(sem texto: o documento não pôde ser lido; julgue pelo assunto)"

NOTAS = {
    1: "Rotina",
    2: "Pouco relevante",
    3: "Relevante",
    4: "Muito relevante",
    5: "Muda a tese",
}
TEMAS = (
    "resultado",
    "dividendos",
    "divida",
    "governanca",
    "fusao",
    "operacao",
    "regulatorio",
)
CONFIANCAS = ("alta", "media", "baixa")

_ASSUNTOS = "\n".join(f"- {codigo}: {nome}" for codigo, nome in topicos.TOPICOS.items())
SISTEMA = f"""Você rotula documentos públicos de companhias abertas brasileiras (CVM), como uma pessoa \
faria na página de rotulagem do TickerLab. O nome, os códigos de negociação e o CNPJ da empresa foram \
trocados por {EMPRESA}, {CODIGO} e {CNPJ}: não tente descobrir qual é a empresa. Julgue só pelo que \
está no documento, como se fosse a data de entrega dele; não use o que aconteceu depois.

Importância (nota de 1 a 5). Pergunte: para quem tem esta ação, este documento muda alguma coisa?
1 Rotina. Obrigação de calendário, formulário padrão, posição mensal de ações de administradores sem \
nada fora do comum.
2 Pouco relevante. Informação útil, mas esperada: convocação de assembleia comum, ata sem surpresas, \
ajuste de estatuto.
3 Relevante. Vale ler: resultado do trimestre, proventos anunciados, emissão de dívida, troca de diretor.
4 Muito relevante. Mexe com o valor da empresa: aquisição, venda de ativo grande, revisão forte de \
metas, renegociação de dívida.
5 Muda a tese. Recuperação judicial, fusão ou OPA, troca de controle, fraude ou reapresentação grave \
de balanço.
Na dúvida entre duas notas, fique com a menor.

Tema: o assunto principal. resultado, dividendos, divida, governanca, fusao (inclui aquisição e OPA), \
operacao (o negócio em si) ou regulatorio.

Assunto (só quando for pedido, nos fatos relevantes): o que a empresa está comunicando, em detalhe. \
Use só os códigos:
{_ASSUNTOS}
Fusão, incorporação de empresa e de ações são FUSAO_INCORPORACAO; OPA para cancelamento de registro é \
FECHAMENTO_CAPITAL; recompra não é aquisição. Sem assunto claro, OUTROS.

Trecho: copie exatamente do documento (ou do assunto) a frase ou parte de frase que mais justifica a \
nota. Não resuma nem traduza.
Confiança: alta, media ou baixa."""


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)
    )


_VARIANTES = {
    "a": "aáàâãä",
    "e": "eéèêë",
    "i": "iíìîï",
    "o": "oóòôõö",
    "u": "uúùûü",
    "c": "cç",
    "n": "nñ",
}
_SUFIXO = re.compile(r"(?i)[\s,.-]*\b(s\.?\s*/?\s*a\.?|ltda\.?)\s*$")
# com letras desde a IN RFB 2.229/2024 (só nos 12 primeiros; os 2 DVs continuam números)
_CNPJ = re.compile(r"\b[0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?\d{2}\b")
_CODIGO = re.compile(r"\b[A-Z]{4}\d{1,2}\b")
_MIN_LETRAS_DO_NOME = 4


def _padrao_do_nome(nome: str) -> re.Pattern[str]:
    # "S.A" no cadastro costuma ser "S.A." no texto: o ponto final vai junto
    fim = r"\.?" if _SUFIXO.search(nome) else ""
    partes = []
    for letra in _sem_acento(nome).lower():
        if letra.isspace():
            partes.append(r"\s+")
        elif letra in _VARIANTES:
            partes.append(f"[{_VARIANTES[letra]}]")
        else:
            partes.append(re.escape(letra))
    return re.compile(r"(?<!\w)" + "".join(partes) + r"(?!\w)" + fim, re.IGNORECASE)


def _comecos(nome: str) -> list[str]:
    """Os começos do nome com pelo menos duas palavras de 4 letras ("Viver Incorporadora"), sem
    terminar num conector ("e", "de"). Uma palavra sozinha não entra: "Banco" ou "Petróleo" apagariam
    o sentido do texto; o teste de identificação da auditoria mede o que escapar."""
    palavras = nome.split()
    comecos = []
    for k in range(2, len(palavras)):
        parte = palavras[:k]
        if len(parte[-1]) >= 3 and sum(len(p) >= 4 for p in parte) >= 2:
            comecos.append(" ".join(parte))
    return comecos


def _variantes_do_nome(nomes: list[str]) -> list[str]:
    """Cada nome inteiro, sem o sufixo da sociedade (S.A., S/A, Ltda.) e os começos dele, do maior
    para o menor (o maior troca primeiro)."""
    variantes = set()
    for nome in nomes:
        nome = " ".join(nome.split())
        sem_sufixo = _SUFIXO.sub("", nome)
        for v in (nome, sem_sufixo, *_comecos(sem_sufixo)):
            if sum(c.isalpha() for c in v) >= _MIN_LETRAS_DO_NOME:
                variantes.add(v)
    return sorted(variantes, key=len, reverse=True)


def _mascara_do_cnpj(achado: re.Match[str]) -> str:
    """Só números: máscara sempre, como antes; com letras, só se o DV confere (não é uma palavra)."""
    texto = achado.group()
    completo = normalizar_cnpj(texto)
    if not tem_letra(texto) or (completo is not None and dv_confere(completo)):
        return CNPJ
    return texto


def anonimizar(texto: str, nomes: list[str]) -> str:
    """Troca CNPJ, códigos de negociação (PETR4, TAEE11) e os nomes da empresa pelos marcadores."""
    texto = _CNPJ.sub(_mascara_do_cnpj, texto)
    texto = _CODIGO.sub(CODIGO, texto)
    for variante in _variantes_do_nome(nomes):
        texto = _padrao_do_nome(variante).sub(EMPRESA, texto)
    return texto


def e_fato_relevante(evento: dict) -> bool:
    return evento.get("categoria") == FATO_RELEVANTE


def documento(evento: dict, texto: str) -> str:
    """O que o modelo lê: os dados do IPE e o começo do texto, sem o nome da empresa."""
    nomes = [evento.get("empresa") or ""]
    corpo = anonimizar(texto[: MAX_CARACTERES_DO_TEXTO + 500], nomes)[
        :MAX_CARACTERES_DO_TEXTO
    ]
    return (
        f"Categoria: {evento.get('categoria', '')}\n"
        f"Tipo: {evento.get('tipo', '')}\n"
        f"Espécie: {evento.get('especie', '')}\n"
        f"Assunto: {anonimizar(evento.get('assunto') or '', nomes)}\n"
        f"Data de entrega: {evento.get('entrega', '')}\n"
        f"Setor: {evento.get('setor', '')}\n\n"
        f"Texto do documento (começo):\n{corpo.strip() or SEM_TEXTO}"
    )


def esquema(fato_relevante: bool) -> dict:
    propriedades: dict = {
        "nota": {"type": "integer", "enum": list(NOTAS)},
        "tema": {"type": "string", "enum": list(TEMAS)},
        "trecho": {"type": "string"},
        "confianca": {"type": "string", "enum": list(CONFIANCAS)},
    }
    if fato_relevante:
        propriedades["assunto"] = {"type": "string", "enum": list(topicos.TOPICOS)}
    return {
        "type": "object",
        "properties": propriedades,
        "required": list(propriedades),
        "additionalProperties": False,
    }


def pedido(evento: dict, texto: str, modelo: str = MODELO) -> dict:
    """Os parâmetros de `messages.create` para um evento (os mesmos servem para o lote). Só o modelo
    muda entre o rotulador e o conferente: guia, prompt e texto anonimizado são os mesmos."""
    modelo_conhecido(modelo)
    pede_assunto = e_fato_relevante(evento)
    instrucao = "Rotule este documento (nota, tema" + (
        ", assunto" if pede_assunto else ""
    )
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": [
            {"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": esquema(pede_assunto)},
        },
        "messages": [
            {
                "role": "user",
                "content": f"{instrucao}, trecho e confiança).\n\n{documento(evento, texto)}",
            }
        ],
    }


def hash_da_entrada(parametros: dict) -> str:
    """SHA-256 do pedido inteiro: prova de que o rótulo saiu daquela entrada (ADR 0055, exigência 13)."""
    return hashlib.sha256(
        json.dumps(parametros, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class RotuloDaIA:
    evento_id: str
    nota: int
    tema: str
    assunto: str | None
    trecho: str
    confianca: str

    def para_guardar(self, modelo: str = MODELO) -> dict:
        return {
            **asdict(self),
            "por": "ia",
            "modelo": modelo,
            "versao_do_prompt": VERSAO_DO_PROMPT,
            "guia": GUIA,
        }


@dataclass(frozen=True)
class ErroDeRotulo:
    evento_id: str
    motivo: str


def _junto(texto: str) -> str:
    return " ".join(texto.split())


def interpretar(resposta: str, evento: dict, texto: str) -> RotuloDaIA | ErroDeRotulo:
    """A resposta do modelo vira rótulo só se respeitar a lista fechada e o trecho literal."""
    evento_id = str(evento.get("id", ""))

    def erro(motivo: str) -> ErroDeRotulo:
        return ErroDeRotulo(evento_id, motivo)

    try:
        dados = json.loads(resposta)
    except json.JSONDecodeError:
        return erro("resposta não é JSON")
    if not isinstance(dados, dict):
        return erro("resposta não é um objeto")
    nota, tema, confianca = dados.get("nota"), dados.get("tema"), dados.get("confianca")
    if not isinstance(nota, int) or isinstance(nota, bool) or nota not in NOTAS:
        return erro(f"nota fora da escala: {nota!r}")
    if tema not in TEMAS:
        return erro(f"tema fora da lista: {tema!r}")
    if confianca not in CONFIANCAS:
        return erro(f"confiança fora da lista: {confianca!r}")
    assunto = None
    if e_fato_relevante(evento):
        assunto = dados.get("assunto")
        if assunto not in topicos.TOPICOS:
            return erro(f"assunto fora da lista: {assunto!r}")
    trecho = _junto(str(dados.get("trecho") or ""))
    if not trecho or trecho not in _junto(documento(evento, texto)):
        return erro("trecho não está no documento")
    return RotuloDaIA(evento_id, nota, tema, assunto, trecho, confianca)


def de_mensagem(
    stop_reason: str | None, texto: str, evento: dict, texto_do_documento: str
) -> RotuloDaIA | ErroDeRotulo:
    """O rótulo de uma resposta da API: recusa ou resposta cortada vira erro."""
    if stop_reason != "end_turn":
        return ErroDeRotulo(str(evento.get("id", "")), f"parada: {stop_reason}")
    return interpretar(texto, evento, texto_do_documento)


def custo_em_dolares(
    tokens_entrada: int, tokens_saida: int, lote: bool = True, modelo: str = MODELO
) -> float:
    """O custo pelos preços do modelo; pela Batch API, a metade."""
    preco = modelo_conhecido(modelo)
    custo = (tokens_entrada * preco.entrada + tokens_saida * preco.saida) / 1_000_000
    return custo * (DESCONTO_DO_LOTE if lote else 1.0)


# --- teste de identificação (auditoria, ADR 0072): a IA reconhece a empresa pelo texto? ----------

SISTEMA_DA_IDENTIFICACAO = f"""O documento abaixo é de uma companhia aberta brasileira e foi \
anonimizado ({EMPRESA}, {CODIGO}, {CNPJ}). Diga qual companhia você acha que é, pelo nome. Se não \
tiver um bom palpite, responda NAO_SEI. Responda só o nome."""
NAO_SEI = "NAO_SEI"


def pedido_de_identificacao(evento: dict, texto: str) -> dict:
    """O mesmo documento que o rotulador lê, perguntando qual é a empresa."""
    return {
        "model": MODELO,
        "max_tokens": 1_000,
        "system": [
            {
                "type": "text",
                "text": SISTEMA_DA_IDENTIFICACAO,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "output_config": {
            "effort": "low",
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {"empresa": {"type": "string"}},
                    "required": ["empresa"],
                    "additionalProperties": False,
                },
            },
        },
        "messages": [{"role": "user", "content": documento(evento, texto)}],
    }


def palpite_da_identificacao(stop_reason: str | None, resposta: str) -> str:
    """O nome que a IA chutou (NAO_SEI se recusou, cortou ou respondeu fora do formato)."""
    if stop_reason != "end_turn":
        return NAO_SEI
    try:
        dados = json.loads(resposta)
    except json.JSONDecodeError:
        return NAO_SEI
    palpite = str(dados.get("empresa") or "").strip() if isinstance(dados, dict) else ""
    return palpite or NAO_SEI


def cliente() -> anthropic.Anthropic:
    """O cliente da API (a chave vem de ANTHROPIC_API_KEY), com o cabeçalho do workspace quando a
    chave não é de um workspace (ANTHROPIC_WORKSPACE_ID no `.env`)."""
    workspace = os.environ.get(VARIAVEL_DO_WORKSPACE, "").strip()
    if workspace:
        return anthropic.Anthropic(
            default_headers={"anthropic-workspace-id": workspace}
        )
    return anthropic.Anthropic()
