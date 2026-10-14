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

O kappa mede a concordância descontando a que viria por sorte: 1 é concordância perfeita, 0 é o
mesmo que chutar com as mesmas proporções. O ponderado quadrático pune mais quem erra por 3 pontos do
que quem erra por 1.
"""

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
NOTAS = (1, 2, 3, 4, 5)

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
    notas_h = [humanos[i]["nota"] for i in prova]
    notas_ia = [ia[i]["nota"] for i in prova]
    veredito.kappa_nota = kappa_ponderado(notas_h, notas_ia)
    veredito.perto_nota = perto(notas_h, notas_ia)
    veredito.kappa_tema = kappa(
        [humanos[i]["tema"] for i in prova], [ia[i]["tema"] for i in prova]
    )
    assuntos_h = [humanos[i].get("assunto") for i in prova]
    veredito.acerto_assunto = acerto(assuntos_h, [ia[i].get("assunto") for i in prova])
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
    if identificadas is None:
        veredito.incompleto = True
        veredito.motivos.append("falta o teste de identificação da empresa")
    else:
        conferidas = [identificadas[i] for i in prova if i in identificadas]
        if len(conferidas) < len(prova):
            veredito.incompleto = True
            veredito.motivos.append(
                f"identificação conferida em {len(conferidas)} de {len(prova)}"
            )
        if conferidas:
            veredito.identificadas = sum(conferidas) / len(conferidas)
            if veredito.identificadas > LIMITES["max_identificadas"]:
                veredito.motivos.append(
                    f"a IA reconheceu a empresa em {veredito.identificadas:.0%} "
                    f"(máximo {LIMITES['max_identificadas']:.0%}): possível olhar o futuro"
                )
    return veredito
