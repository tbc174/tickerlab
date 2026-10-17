"""A auditoria dos rótulos da IA contra os do Tiago, feitos às cegas (ADR 0072, item 3).

Os rótulos da IA só entram no treino se, no conjunto de prova (pelo menos 300 eventos rotulados pelo
Tiago), passarem em todos os limites de `LIMITES`, escritos antes de existir qualquer rótulo da IA:

- **nota:** kappa ponderado quadrático ≥ 0,60 e diferença de no máximo 1 ponto em ≥ 90%;
- **tema:** kappa ≥ 0,70;
- **assunto** (fatos relevantes): acerto ≥ 80%;
- **empresa reconhecida** (vazamento): a IA, lendo o documento anonimizado, acerta o nome da empresa
  em no máximo 10% dos eventos. Se reconhece, pode estar dando a nota pelo que sabe que aconteceu
  depois. (Troca a comparação das notas 5 da ADR, que reprovaria à toa: os eventos de nota 5 são os
  mais fáceis para qualquer um.)

**Emenda 1 (17/10/2026):** o Tiago sai do caminho. Os mesmos limites de nota, tema e assunto passam
a valer entre o Sonnet (rotulador) e o Opus (segundo modelo às cegas) nos 300 primeiros da fila
(`comparar_modelos`); no `lote-leitor-v1`, os eventos em que os dois concordam no assunto viram a
referência de máquina do leitor (`referencia_do_leitor`). O teste de identificação continua no Sonnet, agora no conjunto de prova
inteiro (`veredito_da_identificacao`), e a **estabilidade** (`estabilidade`) mede o Sonnet contra ele
mesmo em 100 eventos sorteados com semente fixa (`sorteio_da_estabilidade`), sem limite: só se publica.

O kappa mede a concordância descontando a que viria por sorte: 1 é concordância perfeita, 0 é o
mesmo que chutar com as mesmas proporções. O ponderado quadrático pune mais quem erra por 3 pontos do
que quem erra por 1.
"""

import random
import unicodedata
from collections import Counter
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field

LIMITES = {
    "kappa_nota": 0.60,
    "perto_nota": 0.90,
    "kappa_tema": 0.70,
    "acerto_assunto": 0.80,
    "max_identificadas": 0.10,
    "min_eventos": 300,
}
# os limites que a Emenda 1 aplica a Sonnet × Opus (a identificação fica no teste do Sonnet)
LIMITES_DA_COMPARACAO = {k: v for k, v in LIMITES.items() if k != "max_identificadas"}
NOTAS = (1, 2, 3, 4, 5)
PRIMEIROS_DA_FILA = 300  # `ordem` < 300: os mesmos "em comum" da ADR 0060
LOTE_DO_LEITOR = "lote-leitor-v1"
# estabilidade (Emenda 1, item 3): escritos antes de rodar, como o resto (ADR 0006)
EVENTOS_DA_ESTABILIDADE = 100
SEMENTE_DA_ESTABILIDADE = 20261017

# palavras que aparecem no nome de muitas empresas: acertar uma delas não é reconhecer a empresa
GENERICAS = frozenset(
    [
        "banco",
        "brasil",
        "brasileira",
        "brasileiro",
        "brasileiras",
        "brasileiros",
        "companhia",
        "participacoes",
        "holding",
        "industria",
        "industrias",
        "comercio",
        "servicos",
        "energia",
        "eletrica",
        "empreendimentos",
        "incorporadora",
        "construtora",
        "construcoes",
        "investimentos",
        "administracao",
        "gestao",
        "tecnologia",
        "saneamento",
        "seguros",
        "seguradora",
        "financeira",
        "transmissao",
        "distribuicao",
        "geracao",
        "logistica",
        "alimentos",
        "sistemas",
        "nacional",
        "estado",
        "paulo",
        "janeiro",
        "grande",
        "metalurgica",
        "siderurgica",
        "mineracao",
        "petroleo",
    ]
)


def _iguais_na_ordem(a: Sequence, b: Sequence) -> None:
    if len(a) != len(b) or not a:
        raise ValueError(
            "As duas listas precisam ter o mesmo tamanho e não podem ser vazias."
        )


def kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    """Kappa de Cohen (categorias sem ordem, como o tema)."""
    _iguais_na_ordem(a, b)
    n = len(a)
    observada = sum(x == y for x, y in zip(a, b, strict=True)) / n
    conta_a, conta_b = Counter(a), Counter(b)
    esperada = sum(conta_a[c] * conta_b[c] for c in conta_a) / n**2
    if esperada == 1:  # todos na mesma categoria: só há concordância ou não
        return 1.0 if observada == 1 else 0.0
    return (observada - esperada) / (1 - esperada)


def kappa_ponderado(
    a: Sequence[int], b: Sequence[int], categorias: Sequence[int] = NOTAS
) -> float:
    """Kappa com peso quadrático (para a nota, que tem ordem): errar por 2 pesa 4 vezes errar por 1."""
    _iguais_na_ordem(a, b)
    n, k = len(a), len(categorias)
    posicao = {c: i for i, c in enumerate(categorias)}
    peso = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
    conta_a, conta_b = Counter(a), Counter(b)
    observada = sum(peso[posicao[x]][posicao[y]] for x, y in zip(a, b, strict=True)) / n
    esperada = sum(
        peso[posicao[x]][posicao[y]] * conta_a[x] * conta_b[y] for x in conta_a for y in conta_b
    ) / n**2  # fmt: skip
    if esperada == 0:
        return 1.0 if observada == 0 else 0.0
    return 1 - observada / esperada


def perto(a: Sequence[int], b: Sequence[int], diferenca: int = 1) -> float:
    """A fração de pares com diferença de no máximo `diferenca` pontos."""
    _iguais_na_ordem(a, b)
    return sum(abs(x - y) <= diferenca for x, y in zip(a, b, strict=True)) / len(a)


def iguais(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    """A fração de pares iguais."""
    _iguais_na_ordem(a, b)
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def acerto(a: Sequence[str | None], b: Sequence[str | None]) -> float | None:
    """A fração de iguais entre os pares em que o humano deu resposta (None se não houver nenhum)."""
    pares = [(x, y) for x, y in zip(a, b, strict=True) if x is not None]
    if not pares:
        return None
    return sum(x == y for x, y in pares) / len(pares)


def _palavras(texto: str) -> set[str]:
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFD", texto.lower())
        if not unicodedata.combining(c)
    )
    return {p for p in "".join(c if c.isalnum() else " " for c in sem_acento).split()}


def identificou(palpite: str, nome: str) -> bool:
    """O palpite da IA tem uma palavra que distingue o nome da empresa (4 letras ou mais, não genérica)?"""
    distintas = {p for p in _palavras(nome) if len(p) >= 4 and p not in GENERICAS}
    return bool(distintas & _palavras(palpite))


def conjunto_de_prova(eventos: list[dict]) -> tuple[list[str], list[str]]:
    """Os ids dos 300 primeiros da fila (fora o lote do leitor) e os do `lote-leitor-v1`."""
    primeiros = [
        e["id"]
        for e in eventos
        if e["ordem"] < PRIMEIROS_DA_FILA and e.get("amostra") != LOTE_DO_LEITOR
    ]
    lote = [e["id"] for e in eventos if e.get("amostra") == LOTE_DO_LEITOR]
    return primeiros, lote


@dataclass
class Veredito:
    n: int
    kappa_nota: float | None = None
    perto_nota: float | None = None
    kappa_tema: float | None = None
    acerto_assunto: float | None = None
    n_assunto: int = 0
    identificadas: float | None = None
    incompleto: bool = False
    motivos: list[str] = field(default_factory=list)

    @property
    def passou(self) -> bool:
        return not self.incompleto and not self.motivos


def auditar(
    humanos: dict[str, dict], ia: dict[str, dict], identificadas: dict[str, bool] | None
) -> Veredito:
    """O veredito da ADR 0072 sobre os eventos que o Tiago rotulou (pulados não contam)."""
    prova = sorted(
        i for i, h in humanos.items() if not h.get("pulado") and h.get("nota")
    )
    faltam = [i for i in prova if i not in ia or "erro" in ia[i]]
    if faltam:
        raise ValueError(
            f"A IA não tem rótulo válido para {len(faltam)} eventos de prova: {faltam[:5]}"
        )
    veredito = Veredito(n=len(prova))
    if len(prova) < LIMITES["min_eventos"]:
        veredito.incompleto = True
        veredito.motivos.append(
            f"só {len(prova)} eventos de prova (mínimo {LIMITES['min_eventos']})"
        )
        return veredito
    _medir(humanos, ia, prova, veredito)
    if identificadas is None:
        veredito.incompleto = True
        veredito.motivos.append("falta o teste de identificação da empresa")
    else:
        identificacao = veredito_da_identificacao(identificadas, prova)
        veredito.identificadas = identificacao.identificadas
        veredito.incompleto |= identificacao.incompleto
        veredito.motivos += identificacao.motivos
    return veredito


def _medir(
    referencia: dict[str, dict],
    outro: dict[str, dict],
    ids: list[str],
    veredito: Veredito,
) -> None:
    """Nota, tema e assunto de `outro` contra `referencia` nos `ids`, com os motivos de reprovação."""
    notas_h = [referencia[i]["nota"] for i in ids]
    notas_ia = [outro[i]["nota"] for i in ids]
    veredito.kappa_nota = kappa_ponderado(notas_h, notas_ia)
    veredito.perto_nota = perto(notas_h, notas_ia)
    veredito.kappa_tema = kappa(
        [referencia[i]["tema"] for i in ids], [outro[i]["tema"] for i in ids]
    )
    assuntos_h = [referencia[i].get("assunto") for i in ids]
    veredito.acerto_assunto = acerto(assuntos_h, [outro[i].get("assunto") for i in ids])
    veredito.n_assunto = sum(a is not None for a in assuntos_h)

    if veredito.kappa_nota < LIMITES["kappa_nota"]:
        veredito.motivos.append(
            f"kappa da nota {veredito.kappa_nota:.2f} < {LIMITES['kappa_nota']}"
        )
    if veredito.perto_nota < LIMITES["perto_nota"]:
        veredito.motivos.append(
            f"nota a até 1 ponto em {veredito.perto_nota:.0%} < {LIMITES['perto_nota']:.0%}"
        )
    if veredito.kappa_tema < LIMITES["kappa_tema"]:
        veredito.motivos.append(
            f"kappa do tema {veredito.kappa_tema:.2f} < {LIMITES['kappa_tema']}"
        )
    if (
        veredito.acerto_assunto is not None
        and veredito.acerto_assunto < LIMITES["acerto_assunto"]
    ):
        veredito.motivos.append(
            f"acerto do assunto {veredito.acerto_assunto:.0%} < {LIMITES['acerto_assunto']:.0%}"
        )


def valido(rotulos: dict[str, dict], i: str) -> bool:
    return i in rotulos and "erro" not in rotulos[i]


def comparar_modelos(
    rotulador: dict[str, dict], conferente: dict[str, dict], primeiros: list[str]
) -> Veredito:
    """Sonnet × Opus nos 300 primeiros da fila (Emenda 1): os limites de nota, tema e assunto. Evento
    sem rótulo válido de um dos dois deixa o veredito incompleto (a medição sai só dos que têm)."""
    veredito = Veredito(n=len(primeiros))
    ids = [i for i in primeiros if valido(rotulador, i) and valido(conferente, i)]
    if len(primeiros) < PRIMEIROS_DA_FILA:
        veredito.incompleto = True
        veredito.motivos.append(
            f"só {len(primeiros)} eventos de prova (mínimo {PRIMEIROS_DA_FILA})"
        )
    if faltam := len(primeiros) - len(ids):
        veredito.incompleto = True
        veredito.motivos.append(
            f"{faltam} eventos sem rótulo válido dos dois modelos: rode os pendentes de novo"
        )
    if ids:
        _medir(rotulador, conferente, ids, veredito)
    return veredito


def referencia_do_leitor(
    rotulador: dict[str, dict], conferente: dict[str, dict], lote: list[str]
) -> list[dict]:
    """Os eventos do lote do leitor em que os dois modelos concordam no assunto (ADR 0069, Emenda 1:
    "referência de máquina", não humana). Nota e tema vão junto só quando também concordam."""
    referencia = []
    for i in lote:
        if not (valido(rotulador, i) and valido(conferente, i)):
            continue
        a, b = rotulador[i], conferente[i]
        if a.get("assunto") is None or a.get("assunto") != b.get("assunto"):
            continue
        referencia.append(
            {
                "evento_id": i,
                "assunto": a["assunto"],
                "nota": a["nota"] if a["nota"] == b["nota"] else None,
                "tema": a["tema"] if a["tema"] == b["tema"] else None,
            }
        )
    return referencia


def veredito_da_identificacao(
    identificadas: dict[str, bool], ids: list[str]
) -> Veredito:
    """O teste de identificação da Emenda 1 nos eventos de prova `ids`: o Sonnet reconheceu a empresa
    em mais de 10% deles reprova (vazamento do futuro); evento sem resposta deixa incompleto."""
    veredito = Veredito(n=len(ids))
    conferidas = [identificadas[i] for i in ids if i in identificadas]
    if len(conferidas) < len(ids):
        veredito.incompleto = True
        veredito.motivos.append(
            f"identificação conferida em {len(conferidas)} de {len(ids)}"
        )
    if conferidas:
        veredito.identificadas = sum(conferidas) / len(conferidas)
        if veredito.identificadas > LIMITES["max_identificadas"]:
            veredito.motivos.append(
                f"a IA reconheceu a empresa em {veredito.identificadas:.0%} "
                f"(máximo {LIMITES['max_identificadas']:.0%}): possível olhar o futuro"
            )
    return veredito


def sorteio_da_estabilidade(eventos: list[dict], rotulos: dict[str, dict]) -> list[str]:
    """Os eventos que o Sonnet rotula de novo: 100 sorteados com a semente fixa entre os que têm
    rótulo válido dele, na fila inteira. Os candidatos vão em ordem de id, para o sorteio não
    depender da ordem do arquivo."""
    candidatos = sorted(e["id"] for e in eventos if valido(rotulos, e["id"]))
    n = min(EVENTOS_DA_ESTABILIDADE, len(candidatos))
    return random.Random(SEMENTE_DA_ESTABILIDADE).sample(candidatos, n)


def estabilidade(
    primeira: dict[str, dict], segunda: dict[str, dict], ids: list[str]
) -> dict:
    """A concordância do Sonnet com ele mesmo nos sorteados: igual e kappa na nota e no tema, ±1 na
    nota e igual no assunto (fatos relevantes). A segunda rodada com erro conta à parte. A emenda
    não põe limite: o número é publicado, nunca aprova nem reprova."""
    pares = [i for i in ids if valido(primeira, i) and valido(segunda, i)]
    medida: dict = {
        "sorteados": len(ids),
        "pares": len(pares),
        "erros": sum(i in segunda and "erro" in segunda[i] for i in ids),
    }
    if not pares:
        return medida
    notas = [primeira[i]["nota"] for i in pares], [segunda[i]["nota"] for i in pares]
    temas = [primeira[i]["tema"] for i in pares], [segunda[i]["tema"] for i in pares]
    assuntos = (
        [primeira[i].get("assunto") for i in pares],
        [segunda[i].get("assunto") for i in pares],
    )
    return medida | {
        "nota_igual": iguais(*notas),
        "perto_nota": perto(*notas),
        "kappa_nota": kappa_ponderado(*notas),
        "tema_igual": iguais(*temas),
        "kappa_tema": kappa(*temas),
        "assunto_igual": acerto(*assuntos),
        "n_assunto": sum(a is not None for a in assuntos[0]),
    }
