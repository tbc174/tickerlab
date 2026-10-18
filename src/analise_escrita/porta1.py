"""Porta 1 (ADR 0093): a análise conferida por código contra a entrada, frase por frase.

Todo número escrito tem de sair das linhas citadas nas notas da frase (ou do fato logo acima, numa
leitura) ou de uma conta declarada que o código refaz; toda data, idem; todo nome próprio tem de
estar na entrada; nada de pessoa, palavra proibida (0085, 0089) nem previsão (0077). Também
reprova a parte que falta, sai de ordem ou vem vazia, e os limites que calam uma lacuna obrigatória.

A parte reprovada vira o molde (sem nova tentativa no mesmo lote): a porta só diz onde e por quê.
"""

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import prod
from typing import Any

from base.dossie import CPF
from src.analise_escrita import numeros, saida
from src.analise_escrita.numeros import DataEscrita, NumeroEscrito
from src.rotulos_ia import mascarar_pessoas

ID_INEXISTENTE = "id_inexistente"
NUMERO, DATA, DATA_FUTURA, CONTA = "numero", "data", "data_futura", "conta"
NOME, PESSOA, PALAVRA, PREVISAO = "nome", "pessoa", "palavra", "previsao"
ESTRUTURA, LACUNA = "estrutura", "lacuna"
CONTAGEM = "contagem"

CONSTANTES_PERMITIDAS = frozenset({100.0})  # "de cada R$ 100"
LADOS_DA_CONTA = 2  # diferença, razão e variação: um lado contra o outro
MENOR_NOME = 2  # uma letra sozinha ("o F de Piotroski") não é nome
PRECISAO_DO_OPERANDO = 0.005  # meia unidade do 3º algarismo, no máximo
FOLGA_DA_CONTA = (
    0.01  # o resultado declarado pode diferir 1% do refeito (arredondamento)
)
CAMPOS_SEM_DADO = frozenset({"id", "secao", "tipo", "so_pro"})
# saída de dinheiro: a ficha guarda com sinal, o texto diz "gastou R$ 0,4 bi" sem o menos
_SAIDA_DE_DINHEIRO = re.compile(
    r"custo|despesa|capex|dividendo|caixa operacional|\bfco\b|depreciac"
)
# siglas, órgãos e nomes de método que o texto pode usar sem estarem na entrada
NOMES_PERMITIDOS = frozenset(
    {
        "cvm", "aneel", "cade", "b3", "bc", "bcb", "brasil", "selic", "ipca",
        "dupont", "piotroski", "altman", "beneish", "roe", "roic", "roa", "ebit", "ebitda",
        "fre", "dfp", "itr", "opa", "ipe", "fca", "cda", "samp", "tickerlab", "odbl", "pwc",
    }
)  # fmt: skip
# sempre proibidas (0089 regras 5 e 7, adjetivos de juízo da 0093, palavras da 0085)
_PROIBIDAS = re.compile(
    r"\b(?:compre|comprem|oportunidades?|imperdive(?:l|is)|garantid[oa]s?|aconselh\w*|invista|"
    r"barat[oa]s?|subvalorizad\w*|sobrevalorizad\w*|fortes?|frac[oa]s?|surpreend\w*|"
    r"decepcion\w*|despenc\w*|dispar(?:ou|aram|ar|a|am)|crise|fraud\w*|corrupcao|cartel|"
    r"conluio|laranja|superfaturamento|direcionamento|suspeit[oa]s?|lucro certo|sem risco|"
    r"risco zero)\b"
)
# proibidas quando afirmam; "nada aqui é recomendação" (a negação antes) passa
_PROIBIDAS_SEM_NEGACAO = re.compile(
    r"\b(?:recomend\w*|preco[- ]alvo|preco justo|potencial de (?:alta|valorizacao))"
)
_NEGACAO = re.compile(r"\b(?:nao|nada|nem|nenhum|nenhuma|sem|nunca)\b")
_RECORDE = re.compile(r"\brecordes?\b")
_PREVISAO = re.compile(
    r"\b(?:vai|vao|irao|tende[m]? a|esperamos|espera-se|prevemos|preve-se|projetamos|"
    r"projeta-se|projecao|projecoes|(?:deve|devem|devera|deverao|deveria|deveriam)\s+"
    r"(?:subir|cair|crescer|aumentar|diminuir|melhorar|piorar|recuar|avancar|voltar|"
    r"continuar|seguir|manter|ficar|chegar))\b"
)
_PALAVRA_COM_MAIUSCULA = re.compile(r"[^\W\d_][\w'’]*")
_FIM_DE_FRASE = re.compile(r"[.:!?]\s*$")
_MARCACAO = re.compile(r"[*_`#>]")


@dataclass(frozen=True)
class Reprovacao:
    parte: str
    paragrafo: int | None  # None: a parte inteira (estrutura, lacuna)
    frase: int | None
    regra: str
    detalhe: str


@dataclass(frozen=True)
class Conferencia:
    reprovacoes: tuple[Reprovacao, ...]

    @property
    def partes_reprovadas(self) -> frozenset[str]:
        return frozenset(r.parte for r in self.reprovacoes)

    @property
    def aprovada(self) -> bool:
        return not self.reprovacoes


@dataclass(frozen=True)
class _Numero:
    valor: float
    sem_sinal: bool  # saída de dinheiro: o texto pode escrever sem o menos


@dataclass(frozen=True)
class _Linha:
    numeros: tuple[_Numero, ...]
    datas: tuple[DataEscrita, ...]
    valor: float | None  # o número principal do item, para a conta que só cita o id


@dataclass(frozen=True)
class _Ficha:
    """A entrada já lida: o que cada id oferece e as palavras de toda a entrada."""

    linhas: dict[str, _Linha]
    palavras: frozenset[str]
    corte: date


@dataclass
class _Permitido:
    """O que uma frase pode escrever: os números e as datas das notas e das contas."""

    numeros: list[_Numero]
    datas: list[DataEscrita]


# --- leitura da entrada ---------------------------------------------------------------------------
def normalizar(texto: str) -> str:
    """Minúsculas e sem acento: as regras de palavra comparam assim."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


def _e_numero(valor: object) -> bool:
    return isinstance(valor, int | float) and not isinstance(valor, bool)


def _valores(dado: object, saida_de_dinheiro: bool) -> Iterator[tuple[object, bool]]:
    """Cada valor solto da linha, com a marca de saída de dinheiro (pela chave ou pelo rótulo)."""
    if isinstance(dado, dict):
        rotulos = " ".join(normalizar(v) for v in dado.values() if isinstance(v, str))
        no_rotulo = saida_de_dinheiro or bool(_SAIDA_DE_DINHEIRO.search(rotulos))
        for chave, valor in dado.items():
            if chave in CAMPOS_SEM_DADO:
                continue
            marca = no_rotulo or bool(_SAIDA_DE_DINHEIRO.search(normalizar(chave)))
            yield from _valores(valor, marca)
    elif isinstance(dado, list):
        for valor in dado:
            yield from _valores(valor, saida_de_dinheiro)
    else:
        yield dado, saida_de_dinheiro


def _ano(valor: float) -> DataEscrita | None:
    if valor == int(valor) and numeros.PRIMEIRO_ANO <= valor <= numeros.ULTIMO_ANO:
        return DataEscrita(int(valor), None, None, str(int(valor)))
    return None


def _ler_linha(linha: dict[str, Any]) -> _Linha:
    saida_de_dinheiro = bool(_SAIDA_DE_DINHEIRO.search(normalizar(linha["id"])))
    achados: list[_Numero] = []
    datas: list[DataEscrita] = []
    for valor, sem_sinal in _valores(linha, saida_de_dinheiro):
        if _e_numero(valor):
            achados.append(_Numero(float(valor), sem_sinal))  # type: ignore[arg-type]
            ano = _ano(float(valor))  # type: ignore[arg-type]
            datas += [ano] if ano else []
        elif isinstance(valor, str):
            escritos, escritas = numeros.ler(valor)
            achados += [_Numero(n.valor, sem_sinal) for n in escritos]
            datas += escritas
    principal = linha.get("valor")
    return _Linha(
        tuple(achados),
        tuple(datas),
        float(principal) if _e_numero(principal) else None,
    )


def _textos(dado: object) -> Iterator[str]:
    if isinstance(dado, dict):
        for chave, valor in dado.items():
            yield str(chave)
            yield from _textos(valor)
    elif isinstance(dado, list):
        for valor in dado:
            yield from _textos(valor)
    elif isinstance(dado, str):
        yield dado


def _palavras(texto: str) -> set[str]:
    return {normalizar(p).strip("'’") for p in _PALAVRA_COM_MAIUSCULA.findall(texto)}


def ler_ficha(entrada: dict[str, Any]) -> _Ficha:
    linhas = {linha["id"]: _ler_linha(linha) for linha in entrada["linhas"]}
    palavras: set[str] = set()
    for texto in _textos(entrada):
        palavras |= _palavras(texto)
    return _Ficha(
        linhas,
        frozenset(palavras),
        date.fromisoformat(entrada["corte"]),
    )


# --- contas ---------------------------------------------------------------------------------------
def _precisao(valor: float) -> float:
    """Meia unidade do último algarismo do número declarado (0,089 → 0,0005)."""
    expoente = Decimal(repr(valor)).normalize().as_tuple().exponent
    return 0.5 * 10.0 ** int(expoente)


def _tolerancia_do_operando(valor: float) -> float:
    """O operando é o número da linha, ou ele arredondado com pelo menos 3 algarismos: 0,2643 vale
    por 0,264332; 0,3 não (arredondado demais, aceitaria qualquer número perto)."""
    precisao = _precisao(valor)
    if precisao <= PRECISAO_DO_OPERANDO * abs(valor):
        return precisao
    return numeros.FOLGA_DO_PONTO_FLUTUANTE * max(1.0, abs(valor))


def _bate(valor: float, candidato: _Numero, tolerancia: float) -> bool:
    if abs(valor - candidato.valor) <= tolerancia:
        return True
    return candidato.sem_sinal and abs(valor - abs(candidato.valor)) <= tolerancia


def _valor_do_operando(
    operando: saida.Operando, resultados: list[float], ficha: _Ficha
) -> tuple[float | None, str]:
    """O valor que entra na conta, ou None e o motivo de não valer."""
    if operando.conta is not None:
        return resultados[operando.conta], ""
    if operando.id is None:
        valor = operando.valor
        if valor in CONSTANTES_PERMITIDAS:
            return valor, ""
        return None, f"constante {valor} fora das permitidas"
    linha = ficha.linhas.get(operando.id)
    if linha is None:
        return None, f"{operando.id} não existe na entrada"
    if operando.valor is None:
        if linha.valor is None:
            return None, f"{operando.id} não tem um valor só"
        return linha.valor, ""
    tolerancia = _tolerancia_do_operando(operando.valor)
    if any(_bate(operando.valor, n, tolerancia) for n in linha.numeros):
        return operando.valor, ""
    return None, f"{operando.valor} não está em {operando.id}"


def refazer(operacao: str, valores: list[float]) -> float | None:
    """A conta feita pelo código; None quando não tem como (divisão por zero, faltou operando)."""
    if operacao == CONTAGEM:
        return float(len(valores))
    if operacao == "soma":
        return sum(valores)
    if operacao == "produto":
        return prod(valores)
    if len(valores) != LADOS_DA_CONTA:
        return None
    a, b = valores
    if operacao == "diferenca":
        return a - b
    divisor = a if operacao == "variacao" else b
    if divisor == 0:
        return None
    return a / b if operacao == "razao" else (b - a) / a


def _conferir_contagem(conta: saida.Conta, ficha: _Ficha) -> str:
    """Contar linhas ("3 trocas de auditor"): cada operando é um id que existe, e a conta é quantos."""
    fora = [o.id for o in conta.de if o.id is None or o.id not in ficha.linhas]
    if fora:
        return f"contagem com operando fora da entrada: {fora}"
    if conta.resultado != len(conta.de):
        return f"contagem dá {len(conta.de)}, não {conta.resultado:g}"
    return ""


def _conferir_conta(
    conta: saida.Conta, resultados: list[float], ficha: _Ficha
) -> tuple[list[float], str]:
    """Os operandos válidos e o motivo de reprovar ("" se a conta confere)."""
    if conta.operacao == CONTAGEM:
        return [], _conferir_contagem(conta, ficha)
    valores: list[float] = []
    for operando in conta.de:
        valor, motivo = _valor_do_operando(operando, resultados, ficha)
        if valor is None:
            return valores, motivo
        valores.append(valor)
    refeito = refazer(conta.operacao, valores)
    if refeito is None:
        return valores, f"{conta.operacao} sem como refazer"
    folga = max(FOLGA_DA_CONTA * abs(refeito), _precisao(conta.resultado))
    if abs(conta.resultado - refeito) > folga:
        return valores, f"{conta.operacao} dá {refeito:.6g}, não {conta.resultado:.6g}"
    return valores, ""


# --- o que cada frase pode escrever ---------------------------------------------------------------
def _permitido_pela_frase(
    frase: saida.Frase, ficha: _Ficha
) -> tuple[_Permitido, list[tuple[str, str]]]:
    permitido = _Permitido([], [])
    falhas: list[tuple[str, str]] = []
    for nota in frase.notas:
        linha = ficha.linhas.get(nota)
        if linha is None:
            falhas.append((ID_INEXISTENTE, nota))
            continue
        permitido.numeros += linha.numeros
        permitido.datas += linha.datas
    resultados: list[float] = []
    for conta in frase.contas:
        valores, motivo = _conferir_conta(conta, resultados, ficha)
        if motivo:
            falhas.append((CONTA, motivo))
        permitido.numeros += [_Numero(v, True) for v in (*valores, conta.resultado)]
        resultados.append(conta.resultado)
    return permitido, falhas


def _escalas_da_frase(texto: str) -> list[float]:
    """ "de R$ 45,1 para R$ 45,6 bilhões": o primeiro número usa a escala do segundo."""
    palavras = set(re.findall(r"\w+", texto.lower()))
    return [escala for nome, escala in numeros.ESCALAS.items() if nome in palavras]


def _numero_confere(
    escrito: NumeroEscrito, escalas: list[float], permitido: _Permitido
) -> bool:
    sem_escala = escrito.trecho[-1].isdigit()
    leituras = [escrito] + [
        NumeroEscrito(
            escrito.valor * e, escrito.tolerancia * e, escrito.trecho, escrito.com_sinal
        )
        for e in (escalas if sem_escala else [])
    ]
    return any(
        leitura.bate_com(n.valor, sem_sinal=n.sem_sinal)
        for leitura in leituras
        for n in permitido.numeros
    )


def _ano_confere(ano: int, permitido: _Permitido, ficha: _Ficha) -> bool:
    """Ano solto ("desde 2021") vale no ano do corte ou entre o menor e o maior ano das notas: a
    tabela das ofertas com 2017 e 2023 sustenta "nenhuma entre 2018 e 2022"."""
    anos = [d.ano for d in permitido.datas]
    return ano == ficha.corte.year or bool(anos) and min(anos) <= ano <= max(anos)


def _falhas_de_numero_e_data(
    texto: str, permitido: _Permitido, ficha: _Ficha
) -> Iterator[tuple[str, str]]:
    escritos, datas = numeros.ler(_MARCACAO.sub("", texto))
    escalas = _escalas_da_frase(texto)
    for escrito in escritos:
        if not _numero_confere(escrito, escalas, permitido):
            yield NUMERO, escrito.trecho
    for data in datas:
        if data.depois_de(ficha.corte):
            yield DATA_FUTURA, data.trecho
        so_o_ano = data.mes is None and data.trecho.isdigit()
        if so_o_ano and _ano_confere(data.ano, permitido, ficha):
            continue
        if not so_o_ano and any(data.bate_com(d) for d in permitido.datas):
            continue
        yield DATA, data.trecho


# --- palavras, nomes e pessoas --------------------------------------------------------------------
def _nomes_fora(texto: str, ficha: _Ficha) -> Iterator[str]:
    """Palavras com maiúscula fora do começo de frase que a entrada não tem."""
    limpo = _MARCACAO.sub("", texto)
    for achado in _PALAVRA_COM_MAIUSCULA.finditer(limpo):
        palavra = achado.group(0).strip("'’")
        antes = limpo[: achado.start()]
        comeco = not antes.strip() or _FIM_DE_FRASE.search(antes)
        if len(palavra) < MENOR_NOME or not palavra[0].isupper() or comeco:
            continue
        normal = normalizar(palavra)
        if normal not in ficha.palavras and normal not in NOMES_PERMITIDOS:
            yield palavra


def _falhas_de_palavra(texto: str, tem_numero: bool) -> Iterator[tuple[str, str]]:
    normal = normalizar(_MARCACAO.sub("", texto))
    proibidas = _PROIBIDAS.findall(normal)
    for achado in _PROIBIDAS_SEM_NEGACAO.finditer(normal):
        if not _NEGACAO.search(normal[: achado.start()]):
            proibidas.append(achado.group(0))
    if not tem_numero:
        proibidas += _RECORDE.findall(normal)
    if proibidas:
        yield PALAVRA, ", ".join(proibidas)
    previsoes = [p.group(0) for p in _PREVISAO.finditer(normal)]
    if previsoes:
        yield PREVISAO, ", ".join(previsoes)


def _falhas_de_pessoa(texto: str) -> Iterator[tuple[str, str]]:
    if mascarar_pessoas(texto) != texto or CPF.search(texto):
        yield PESSOA, "nome de pessoa ou CPF"


# --- a análise ------------------------------------------------------------------------------------
def _falhas_da_frase(
    frase: saida.Frase, acima: _Permitido, ficha: _Ficha
) -> tuple[list[tuple[str, str]], _Permitido]:
    permitido, falhas = _permitido_pela_frase(frase, ficha)
    junto = _Permitido(permitido.numeros + acima.numeros, permitido.datas + acima.datas)
    falhas += _falhas_de_numero_e_data(frase.texto, junto, ficha)
    nomes = list(_nomes_fora(frase.texto, ficha))
    falhas += [(NOME, ", ".join(nomes))] if nomes else []
    falhas += _falhas_de_pessoa(frase.texto)
    tem_numero = bool(numeros.numeros(frase.texto))
    falhas += _falhas_de_palavra(frase.texto, tem_numero)
    return falhas, permitido


def falhas_da_frase(frase: saida.Frase, ficha: _Ficha) -> list[tuple[str, str]]:
    """As (regra, trecho) que reprovam a frase sozinha, sem o fato acima: o molde usa para deixar
    de fora a frase da ficha que a porta reprovaria ("não dizem o que vai acontecer")."""
    return _falhas_da_frase(frase, _Permitido([], []), ficha)[0]


def _juntar(falhas: list[tuple[str, str]]) -> dict[str, str]:
    """Uma reprovação por regra em cada frase, com todos os trechos."""
    por_regra: dict[str, list[str]] = {}
    for regra, detalhe in falhas:
        por_regra.setdefault(regra, []).append(detalhe)
    return {regra: "; ".join(trechos) for regra, trechos in por_regra.items()}


def _conferir_parte(parte: saida.Parte, ficha: _Ficha) -> Iterator[Reprovacao]:
    do_fato = _Permitido([], [])  # o que a leitura pode repetir: o fato logo acima
    for i, paragrafo in enumerate(parte.paragrafos):
        do_paragrafo = _Permitido([], [])
        acima = do_fato if paragrafo.tipo == saida.LEITURA else _Permitido([], [])
        for j, frase in enumerate(paragrafo.frases):
            falhas, permitido = _falhas_da_frase(frase, acima, ficha)
            for regra, detalhe in _juntar(falhas).items():
                yield Reprovacao(parte.chave, i, j, regra, f"{frase.texto} [{detalhe}]")
            do_paragrafo.numeros += permitido.numeros
            do_paragrafo.datas += permitido.datas
        if paragrafo.tipo == saida.FATO:
            do_fato = do_paragrafo


def _conferir_estrutura(analise: saida.Analise) -> Iterator[Reprovacao]:
    chaves = [p.chave for p in analise.partes]
    for chave in saida.PARTES:
        if chave not in chaves:
            yield Reprovacao(chave, None, None, ESTRUTURA, "parte faltando")
    vistas: list[str] = []
    for parte in analise.partes:
        if parte.chave in vistas:
            yield Reprovacao(parte.chave, None, None, ESTRUTURA, "parte repetida")
        elif not any(p.frases for p in parte.paragrafos):
            yield Reprovacao(parte.chave, None, None, ESTRUTURA, "parte vazia")
        vistas.append(parte.chave)
    esperada = [c for c in saida.PARTES if c in chaves]
    unicas = list(dict.fromkeys(chaves))
    for chave, devia in zip(unicas, esperada, strict=True):
        if chave != devia:
            yield Reprovacao(
                chave, None, None, ESTRUTURA, f"fora de ordem (devia: {devia})"
            )


def _conferir_lacunas(
    analise: saida.Analise, entrada: dict[str, Any]
) -> Iterator[Reprovacao]:
    citadas = {
        nota
        for parte in analise.partes
        for paragrafo in parte.paragrafos
        for frase in paragrafo.frases
        for nota in frase.notas
    }
    for obrigatoria in entrada.get("obrigatorias", []):
        if obrigatoria not in citadas:
            detalhe = f"o texto cala o que a base não tem: {obrigatoria}"
            yield Reprovacao("limites", None, None, LACUNA, detalhe)


def conferir(analise: saida.Analise, entrada: dict[str, Any]) -> Conferencia:
    """Todas as reprovações da análise contra a entrada (nenhuma: aprovada na porta 1)."""
    ficha = ler_ficha(entrada)
    reprovacoes = [*_conferir_estrutura(analise), *_conferir_lacunas(analise, entrada)]
    for parte in analise.partes:
        reprovacoes += _conferir_parte(parte, ficha)
    return Conferencia(tuple(reprovacoes))
