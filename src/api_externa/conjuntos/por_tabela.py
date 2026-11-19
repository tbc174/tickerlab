"""A leitura das tabelas do registro `src/api_externa/tabelas_por_cnpj.py`, uma entrada por vez (linha 978, lote 1).

`LeitorPorTabela(porta, permitido, linhas_maximas).bloco(nome, cnpj, como_era_em)` lê as entradas de um bloco
(da análise completa ou da rota do fundo) para o CNPJ e devolve, em tipos simples, `{chave: corpo}` de cada entrada
que tem algum campo liberado pelo portão. O corpo de cada entrada diz se achou a empresa (`achou`), as fontes, o que
a base cobre e os itens, cada campo no envelope com a fonte e o dia em que ficou público.

- **Sem olhar o futuro:** a porta só traz o que era público no dia (o `publico_em` dela, que é o `disponivel_em`
  ou, na tabela publicada por mês, o último dia do mês dele) e, de cada chave do contrato, a revisão mais nova já
  vista; a "data mais nova" de uma lista é a mais nova entre essas linhas. O envelope diz esse mesmo dia.
- **Sem pessoa:** as views da porta já tiram as linhas marcadas como pessoa; os campos que a trava do D2.4 nega
  pelo nome nem estão no registro. A linha que saiu do arquivo da fonte (`consta` falso) não sai. Na entrada com
  `marca_de_pessoa` (CGU, IBAMA e MTE), só sai a linha com a marca falsa (MEI, empresário individual e a linha sem
  a marca ficam de fora, também da contagem), e todo texto servido passa pela varredura de CPF e e-mail: se achar,
  a leitura levanta `RespostaComPessoaProibida` (a rota responde 503), nunca um "não achou".
- **Bloco fechado não vaza:** entrada sem campo liberado não aparece, nem a chave dela; bloco sem entrada liberada
  volta None.
- Tabela que não está na base (ou sem uma coluna que a entrada usa) responde "não achou", com a cobertura.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.rede import views
from src.api_externa.conjuntos import Permitido
from src.api_externa.envelope import campo
from src.api_externa.pessoas import RespostaComPessoaProibida
from src.api_externa.tabelas_por_cnpj import CNPJ, FUNDO, RAIZ, TabelaPorCnpj, do_bloco
from src.pessoa_no_texto import texto_de_pessoa

PUBLICO_EM = "disponivel_em"
PUBLICO_EM_NA_PORTA = "publico_em"  # o dia com que a porta corta o futuro (o fim do mês, na tabela mensal)
VISTO_EM = "visto_em"
CONSTA = "consta"
DESCENDENTE = "-"


@dataclass(frozen=True)
class LidoPorTabela:
    """O que sai de um bloco: o corpo (uma chave por entrada liberada), as fontes usadas e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def vazio(corpo: dict) -> bool:
    """Se nenhuma entrada do bloco achou a empresa (a análise põe o bloco em "não achado")."""
    return not any(sub.get("achou") for sub in corpo.values() if isinstance(sub, dict))


def pares(entrada: TabelaPorCnpj) -> tuple[tuple[str, str], ...]:
    """Os pares (fonte, campo) da entrada: o bloco abre se o portão libera algum deles."""
    return tuple((fonte, nome) for fonte in entrada.fontes for nome in entrada.campos)


def _simples(valor: object) -> object:
    """O valor em tipo simples (vira JSON); vazio, NaN ou texto em branco é ausente (None)."""
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor.strip() or None
    if isinstance(valor, pd.Timestamp | datetime):
        return None if pd.isna(valor) else valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if pd.isna(valor):  # type: ignore[arg-type]
        return None
    if hasattr(valor, "item"):  # o número do numpy vira o do Python
        return valor.item()  # type: ignore[attr-defined]
    return valor


def _dia(valor: object) -> date | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _de_empresa(marca: object) -> bool:
    """A marca de pessoa diz, sem dúvida, que a linha é de empresa: só o falso; vazio ou outro valor fica de fora."""
    return _simples(marca) is False


def _varrer(entrada: TabelaPorCnpj, item: dict[str, dict]) -> None:
    """Na entrada com marca de pessoa, nenhum texto servido traz CPF ou e-mail; achou, a resposta cai (o caminho
    diz onde, nunca o valor)."""
    if not entrada.marca_de_pessoa:
        return
    falhas = [
        f"{entrada.chave}.{nome}"
        for nome, envelope in item.items()
        if isinstance(valor := envelope.get("valor"), str) and texto_de_pessoa(valor)
    ]
    if falhas:
        raise RespostaComPessoaProibida(falhas)


def _so_caracteres(valor: object) -> str:
    return "".join(c for c in str(valor) if c.isalnum()).upper()


def _colunas_da_view(porta: Porta, tabela: str) -> set[str]:
    linhas = porta.con.execute(f'DESCRIBE SELECT * FROM "{tabela}"').fetchall()
    return {str(linha[0]) for linha in linhas}


def _coluna_da_ordem(nome: str) -> str:
    return nome.removeprefix(DESCENDENTE)


def _ordenar(tabela: pd.DataFrame, entrada: TabelaPorCnpj) -> pd.DataFrame:
    """Da data do fato mais nova à mais velha e, no empate, pela ordem da entrada; a ordem é total (o resto das
    colunas desempata), para a mesma base dar sempre a mesma lista."""
    chaves = [entrada.data_do_fato, *(_coluna_da_ordem(o) for o in entrada.ordem)]
    sentidos = [False, *(not o.startswith(DESCENDENTE) for o in entrada.ordem)]
    resto = [c for c in tabela.columns if c not in chaves]
    return tabela.sort_values(
        [*chaves, *resto],
        ascending=[*sentidos, *([True] * len(resto))],
        na_position="last",
        kind="stable",
    )


class LeitorPorTabela:
    """Lê as entradas de um bloco do registro de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = max(linhas_maximas, 1)

    def _servidos(self, entrada: TabelaPorCnpj) -> dict[str, tuple[str, ...]]:
        """Os campos liberados de cada fonte da entrada, na ordem do registro (fonte sem campo fica de fora)."""
        por_fonte = {
            fonte: tuple(n for n in entrada.campos if self.permitido(fonte, n, False))
            for fonte in entrada.fontes
        }
        return {fonte: nomes for fonte, nomes in por_fonte.items() if nomes}

    def _colunas(self, entrada: TabelaPorCnpj, existentes: set[str]) -> list[str]:
        pedidas = [
            *entrada.campos,
            entrada.data_do_fato,
            *(_coluna_da_ordem(o) for o in entrada.ordem),
            *entrada.uma_por,
            *([entrada.coluna_da_fonte] if entrada.coluna_da_fonte else []),
            *([entrada.marca_de_pessoa] if entrada.marca_de_pessoa else []),
            PUBLICO_EM,
            PUBLICO_EM_NA_PORTA,
            VISTO_EM,
            CONSTA,
            CNPJ,
        ]
        return [c for c in dict.fromkeys(pedidas) if c in existentes]

    def _linhas(
        self, entrada: TabelaPorCnpj, cnpj: str, como_era_em: date
    ) -> pd.DataFrame:
        """As linhas da raiz como eram no dia, sem as que saíram do arquivo; na rota do fundo, só as do CNPJ
        inteiro. Vazia se a tabela (ou a coluna da raiz) não está na base."""
        if entrada.tabela not in views(self.porta.con):
            return pd.DataFrame()
        existentes = _colunas_da_view(self.porta, entrada.tabela)
        precisa = {
            RAIZ,
            PUBLICO_EM,
            entrada.data_do_fato,
            *(_coluna_da_ordem(o) for o in entrada.ordem),
            *entrada.uma_por,
            *([CNPJ] if entrada.onde_sai == FUNDO else []),
            *([entrada.coluna_da_fonte] if entrada.coluna_da_fonte else []),
            *([entrada.marca_de_pessoa] if entrada.marca_de_pessoa else []),
        }
        if not precisa <= existentes:
            return (
                pd.DataFrame()
            )  # tabela de contrato incompleto: responde "não achou", não derruba a rota
        tabela = self.porta.ler(
            entrada.tabela,
            como_era_em=como_era_em,
            filtros={RAIZ: [cnpj[: cnpj_.TAMANHO_DA_RAIZ]]},
            colunas=self._colunas(entrada, existentes),
        )
        if CONSTA in tabela.columns:
            tabela = tabela[tabela[CONSTA].fillna(True).astype(bool)]
        if entrada.marca_de_pessoa:
            tabela = tabela[
                tabela[entrada.marca_de_pessoa].map(_de_empresa).astype(bool)
            ]
        if entrada.onde_sai == FUNDO:
            tabela = tabela[tabela[CNPJ].map(_so_caracteres) == cnpj]
        return tabela

    def _lista(self, entrada: TabelaPorCnpj, tabela: pd.DataFrame) -> pd.DataFrame:
        """As linhas da lista: na ordem, só a data mais nova (se a entrada pede) e uma por chave de `uma_por`."""
        if tabela.empty:
            return tabela
        tabela = _ordenar(tabela, entrada)
        if entrada.so_a_data_mais_nova:
            mais_nova = tabela[entrada.data_do_fato].dropna().max()
            tabela = tabela[tabela[entrada.data_do_fato] == mais_nova]
        if entrada.uma_por:
            tabela = tabela.drop_duplicates(list(entrada.uma_por), keep="first")
        return tabela

    def _fonte_da_linha(self, entrada: TabelaPorCnpj, linha: dict) -> str | None:
        if entrada.coluna_da_fonte is None:
            return entrada.fontes[0]
        return dict(entrada.fonte_pelo_valor).get(
            str(_simples(linha.get(entrada.coluna_da_fonte)))
        )

    def _item(
        self, entrada: TabelaPorCnpj, linha: dict, servidos: dict[str, tuple[str, ...]]
    ) -> tuple[str, dict] | None:
        fonte = self._fonte_da_linha(entrada, linha)
        if fonte is None or fonte not in servidos:
            return None  # linha de uma fonte que o portão não libera (ou que o registro não conhece)
        publico_em = _dia(linha.get(PUBLICO_EM_NA_PORTA, linha[PUBLICO_EM]))
        if publico_em is None:
            return None
        visto_em = _dia(linha.get(VISTO_EM))
        item = {
            nome: campo(valor, fonte=fonte, publico_em=publico_em, visto_em=visto_em)
            for nome in servidos[fonte]
            if (valor := _simples(linha.get(nome))) is not None
        }
        _varrer(entrada, item)
        return (fonte, item) if item else None

    def _entrada(
        self,
        entrada: TabelaPorCnpj,
        cnpj: str,
        como_era_em: date,
        servidos: dict[str, tuple[str, ...]],
    ) -> tuple[dict, set[str], int]:
        lista = self._lista(entrada, self._linhas(entrada, cnpj, como_era_em))
        itens: list[dict] = []
        fontes: set[str] = set()
        for linha in lista.to_dict("records"):
            lido = self._item(entrada, linha, servidos)
            if lido is not None:
                fontes.add(lido[0])
                itens.append(lido[1])
        pagina = itens[: self.linhas_maximas]
        corpo = {
            "achou": bool(itens),
            "fontes": sorted(servidos),
            "cobertura": entrada.cobertura,
            "itens": pagina,
            "cortada": len(itens) > len(pagina),
        }
        return corpo, fontes, len(pagina)

    def bloco(self, nome: str, cnpj: str, como_era_em: date) -> LidoPorTabela | None:
        """As entradas liberadas do bloco para o CNPJ, como eram no dia; None se nenhuma tem campo liberado."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        cnpj = normal
        corpo: dict[str, dict] = {}
        fontes: set[str] = set()
        linhas = 0
        for entrada in do_bloco(nome):
            servidos = self._servidos(entrada)
            if not servidos:
                continue
            sub, usadas, servidas = self._entrada(entrada, cnpj, como_era_em, servidos)
            corpo[entrada.chave] = sub
            fontes |= usadas
            linhas += servidas
        if not corpo:
            return None
        return LidoPorTabela(corpo, fontes, linhas)
