"""O teste dos 29 negócios: `compradores_do_setor` acha o comprador real por um movimento ANTERIOR ao negócio?

Nasceu da simulação 1 do bot Analista (25/11/2026, pedido à Diretoria): com 29 negócios reais, a lista acertou o
comprador por movimento anterior em 5 (17%). As causas que a simulação mediu viram aqui 29 casos de mentira, um por
negócio, com as mesmas proporções (5 acertos, 2 fracos, 12 só pelo próprio negócio, 10 sem aparecer). Não há nome
nem CNPJ real: as raízes são de ninguém, e é só empresa (nada de pessoa física, em dado, saída ou texto).

A regra de acerto é a do bot: o comprador aparece na lista (limite 50, janela de 5 anos) com PELO MENOS UMA prova que
não é o próprio negócio (outra empresa do setor) e que é de antes da data do negócio. Vale a lista da subclasse com a
UF do alvo ou a da classe sem UF (o bot olhava as duas).

O placar de partida, 5, é uma trava: cada conserto da fila (1042: empresa baixada; 1044: ordem e corte) sobe o placar, e
o teste diz quanto. O que continua fora (alvo S.A., negócio antes da janela, comprador acima do alvo) fica como
"fora de alcance" de propósito: é de outras linhas (1031, 1032, 1043).
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.porta import Porta
from src.api_externa.conjuntos import compradores
from tests.test_api_externa_compradores import CARIMBOS, _gravar

HOJE = date(2026, 11, 10)
SUBCLASSE, CLASSE = "6201501", "62015"
SP, MG = "SP", "MG"
LIMITE_DA_LISTA = 50
ANOS_DA_JANELA = 5
RUIDO = 60  # holdings com uma entrada recente cada: mais que os 50 da lista, como as centenas do setor real
ABERTAS_BARULHENTAS = (
    3  # companhias abertas de outro setor com uma controlada no CNAE e uma entrada
)


@dataclass(frozen=True)
class Caso:
    """Um negócio: o alvo (empresa do setor), o comprador real, o dia do negócio e por que a lista erra ou acerta."""

    nome: str
    alvo: str
    comprador: str
    negocio: date
    grupo: str


# os grupos do placar, na ordem do pedido da simulação
ACERTA_COM_UF = "acerta com a UF do alvo"
ACERTA_SEM_UF = "acerta só sem a UF"
FRACO = "controlada sem data de antes do negócio"
SO_O_PROPRIO_NEGOCIO = "só pelo próprio negócio"
CORTADO_PELOS_50 = "entrada antiga empurrada para fora dos 50"
EMPRESA_BAIXADA = "entrou em empresa depois baixada"
FORA_DE_ALCANCE = "fora de alcance destas linhas"
GRUPOS_QUE_ERRAM_PARA_SEMPRE = (FRACO, SO_O_PROPRIO_NEGOCIO, FORA_DE_ALCANCE)


class _Contador:
    """Raízes de mentira, uma faixa por tipo de empresa (o prefixo diz quem é)."""

    def __init__(self) -> None:
        self.proximos: dict[str, int] = {}

    def raiz(self, faixa: str) -> str:
        n = self.proximos.get(faixa, 0)
        self.proximos[faixa] = n + 1
        return f"{faixa}{n:06d}"


class Mundo:
    """A base de mentira: o setor com as empresas ativas, as baixadas, as entradas e as controladas."""

    def __init__(self) -> None:
        self.c = _Contador()
        self.estabelecimentos: list[tuple] = []
        self.entradas: list[tuple] = []
        self.controladas: list[tuple] = []
        self.nomes: dict[str, str] = {}
        self.casos: list[Caso] = []
        self._montar()

    # -- peças ---------------------------------------------------------------------------------
    def empresa(self, faixa: str, uf: str = SP, situacao: str = "02") -> str:
        """Uma empresa do setor (ativa ou, com situacao 08, baixada), aberta em 2005, com nome."""
        raiz = self.c.raiz(faixa)
        self.nomes[raiz] = f"EMPRESA {raiz} LTDA"
        for mes, publico in (("2026-09", "2026-09-30"), ("2026-10", "2026-10-31")):
            self.estabelecimentos.append(
                (raiz, situacao, "2005-01-01", f"{SUBCLASSE}", uf, mes, publico)
            )
        return raiz

    def comprador(self, faixa: str = "30") -> str:
        raiz = self.c.raiz(faixa)
        self.nomes[raiz] = f"COMPRADORA {raiz} PARTICIPACOES S.A."
        return raiz

    def entrar(self, comprador: str, alvo: str, quando: str) -> None:
        """O comprador entrou como sócio do alvo em `quando` (AAAA-MM-DD); a Receita publica no mês seguinte."""
        mes_da_base = (pd.Timestamp(quando) + pd.offsets.MonthBegin(1)).strftime(
            "%Y-%m"
        )
        publico = (pd.Timestamp(mes_da_base + "-01") + pd.offsets.MonthEnd(0)).strftime(
            "%Y-%m-%d"
        )
        self.entradas.append((comprador, alvo, quando, mes_da_base, publico, "entrou"))

    def controlar(self, aberta: str, alvo: str, referencia: str) -> None:
        self.controladas.append((aberta, alvo, referencia))

    def caso(
        self, nome: str, grupo: str, alvo: str, comprador: str, negocio: str
    ) -> None:
        self.casos.append(
            Caso(nome, alvo, comprador, date.fromisoformat(negocio), grupo)
        )

    # -- os 29 negócios -----------------------------------------------------------------------
    def _montar(self) -> None:
        self._ruido()
        self._acertos()
        self._so_o_proprio_negocio()
        self._fracos()
        self._cortados_pelos_50()
        self._empresas_baixadas()
        self._fora_de_alcance()
        assert len(self.casos) == 29

    def _ruido(self) -> None:
        """Holding com uma entrada recente (2026-04 em diante) e companhia aberta com controlada: o barulho do topo."""
        for i in range(RUIDO):
            self.entrar(
                self.comprador("31"), self.empresa("20"), f"2026-0{4 + i % 5}-1{i % 9}"
            )
        for i in range(ABERTAS_BARULHENTAS):
            aberta = self.comprador("32")
            self.controlar(aberta, self.empresa("20"), "2025-12-31")
            self.entrar(aberta, self.empresa("20"), f"2026-0{5 + i}-20")

    def _acertos(self) -> None:
        """5 acertos de hoje: o comprador tem várias entradas antes do negócio (2 na UF do alvo, 3 só fora dela)."""
        for i in range(2):
            comprador, alvo = self.comprador(), self.empresa("21")
            for _ in range(3):
                self.entrar(comprador, self.empresa("20"), f"2024-0{3 + i}-10")
            self.caso(
                f"acerta com UF {i + 1}", ACERTA_COM_UF, alvo, comprador, "2026-08-20"
            )
        for i in range(3):
            comprador, alvo = self.comprador(), self.empresa("21")
            for _ in range(3):
                self.entrar(comprador, self.empresa("20", uf=MG), f"2024-0{6 + i}-10")
            self.caso(
                f"acerta só sem UF {i + 1}",
                ACERTA_SEM_UF,
                alvo,
                comprador,
                "2026-08-20",
            )

    def _so_o_proprio_negocio(self) -> None:
        """12 negócios em que o comprador só aparece por ter entrado no próprio alvo (e depois dele, o teste fica inflado)."""
        for i in range(12):
            comprador, alvo = self.comprador(), self.empresa("21")
            self.entrar(comprador, alvo, f"2026-10-0{1 + i % 9}")
            self.caso(
                f"só o negócio {i + 1}",
                SO_O_PROPRIO_NEGOCIO,
                alvo,
                comprador,
                f"2026-10-0{1 + i % 9}",
            )

    def _fracos(self) -> None:
        """2 acertos fracos: a companhia aberta aparece por uma controlada cuja data (a do FRE) é depois do negócio."""
        for i in range(2):
            aberta, alvo = self.comprador("32"), self.empresa("21")
            self.controlar(aberta, self.empresa("20"), "2026-09-30")
            self.caso(f"controlada sem data {i + 1}", FRACO, alvo, aberta, "2026-06-15")

    def _cortados_pelos_50(self) -> None:
        """2 negócios com uma entrada antiga (2023) numa empresa ativa do setor: a lista de 50 só tem holding mais nova."""
        for i in range(2):
            comprador, alvo = self.comprador(), self.empresa("21")
            self.entrar(comprador, self.empresa("20"), f"2023-1{i}-10")
            self.caso(
                f"cortado pelos 50 {i + 1}",
                CORTADO_PELOS_50,
                alvo,
                comprador,
                "2026-08-20",
            )

    def _empresas_baixadas(self) -> None:
        """5 negócios em que o comprador tem 2 entradas anteriores, em empresas do setor hoje baixadas (situação 08)."""
        for i in range(5):
            comprador, alvo = self.comprador(), self.empresa("21")
            for _ in range(2):
                self.entrar(
                    comprador, self.empresa("22", situacao="08"), f"2024-0{2 + i}-10"
                )
            self.caso(
                f"empresa baixada {i + 1}",
                EMPRESA_BAIXADA,
                alvo,
                comprador,
                "2026-08-20",
            )

    def _fora_de_alcance(self) -> None:
        """3 negócios que estas linhas não resolvem: alvo S.A. sem o comprador no quadro, negócio antes da janela de 5
        anos e comprador que entrou na holding acima do alvo."""
        alvo = self.empresa("21")
        self.caso("alvo S.A.", FORA_DE_ALCANCE, alvo, self.comprador(), "2026-08-20")
        comprador, alvo = self.comprador(), self.empresa("21")
        self.entrar(
            comprador, self.empresa("20"), "2021-05-10"
        )  # antes de 10/11/2021, o início da janela
        self.caso("antes da janela", FORA_DE_ALCANCE, alvo, comprador, "2021-06-01")
        comprador, alvo = self.comprador(), self.empresa("21")
        self.caso("acima do alvo", FORA_DE_ALCANCE, alvo, comprador, "2026-08-20")

    # -- as tabelas -----------------------------------------------------------------------------
    def gravar(self, base: Path) -> None:
        estabelecimentos = pd.DataFrame(
            self.estabelecimentos,
            columns=["cnpj_basico", "situacao_cadastral", "data_inicio_atividade", "cnae_principal", "uf",
                     "mes_do_retrato", "disponivel_em"],
        )  # fmt: skip
        estabelecimentos["cnpj"] = estabelecimentos["cnpj_basico"] + "000100"
        estabelecimentos["matriz"] = True
        estabelecimentos["municipio"] = "7107"
        estabelecimentos["data_inicio_atividade"] = pd.to_datetime(
            estabelecimentos["data_inicio_atividade"]
        )
        estabelecimentos["disponivel_em"] = pd.to_datetime(
            estabelecimentos["disponivel_em"]
        ).dt.date
        _gravar(
            base / compradores.ESTABELECIMENTOS / "11.parquet",
            estabelecimentos.assign(**CARIMBOS),
        )
        _gravar(base / compradores.EMPRESAS / "11.parquet", self._empresas())
        _gravar(
            base / compradores.ENTRADAS / "parte.parquet", self._tabela_de_entradas()
        )
        _gravar(
            base / compradores.CONTROLADAS / "2025.parquet",
            self._tabela_de_controladas(),
        )

    def _empresas(self) -> pd.DataFrame:
        linhas = [
            (raiz, nome, mes, publico)
            for mes, publico in (("2026-09", "2026-09-30"), ("2026-10", "2026-10-31"))
            for raiz, nome in self.nomes.items()
        ]
        tabela = pd.DataFrame(
            linhas,
            columns=["cnpj_basico", "razao_social", "mes_do_retrato", "disponivel_em"],
        )
        tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
        return tabela.assign(natureza_juridica="2062", porte="demais", capital_social=1_000_000.0,
                             n_estabelecimentos=1, **CARIMBOS)  # fmt: skip

    def _tabela_de_entradas(self) -> pd.DataFrame:
        tabela = pd.DataFrame(
            self.entradas,
            columns=[
                "raiz_socio_pj",
                "cnpj_basico",
                "data_entrada",
                "mes_do_retrato",
                "disponivel_em",
                "movimento",
            ],
        )
        tabela["data_entrada"] = pd.to_datetime(tabela["data_entrada"]).dt.date
        tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
        return tabela.assign(qualificacao="22", **CARIMBOS)

    def _tabela_de_controladas(self) -> pd.DataFrame:
        companhias = [(aberta, alvo, ref) for aberta, alvo, ref in self.controladas]
        return pd.DataFrame({
            "cnpj_companhia": [a + "000199" for a, _, _ in companhias],
            "referencia": pd.to_datetime([r for _, _, r in companhias]).date,
            "versao": [1] * len(companhias),
            "conhecido_em": pd.to_datetime(["2026-05-30"] * len(companhias)).date,
            "origem_coletada_em": pd.to_datetime(["2026-06-01"] * len(companhias)).date,
            "cnpj": [al + "000100" for _, al, _ in companhias],
            "tipo": ["controlada"] * len(companhias),
            "participacao": [100.0] * len(companhias),
        }).assign(**CARIMBOS)  # fmt: skip


# ------------------------------------------------------------------ a régua do bot


def _dia_da_prova(sinal: str, exemplo: dict) -> date | None:
    campo = "data_entrada" if sinal == compradores.ENTROU else "referencia"
    valor = (exemplo.get(campo) or {}).get("valor")
    return date.fromisoformat(valor) if valor else None


def acertou(lista: list[dict], caso: Caso) -> bool:
    """O comprador do caso está na lista com uma prova de antes do negócio numa empresa do setor que não é o alvo."""
    for comprador in lista:
        if comprador["raiz_do_cnpj"] != caso.comprador:
            continue
        for sinal, prova in comprador["provas"].items():
            for exemplo in prova["exemplos"]:
                empresa = exemplo["empresa_do_setor"]["raiz_do_cnpj"]
                dia = _dia_da_prova(sinal, exemplo)
                if empresa != caso.alvo and dia is not None and dia < caso.negocio:
                    return True
    return False


def _lista(
    leitor: compradores.LeitorDeCompradores, cnae: str, uf: str | None
) -> list[dict]:
    pedido = compradores.PedidoDeCompradores(cnae, uf, ANOS_DA_JANELA, LIMITE_DA_LISTA)
    servido = leitor.compradores(pedido, HOJE)
    assert servido is not None
    return servido.corpo["compradores"]


def placar(pasta: Path) -> dict[str, list[str]]:
    """Os nomes dos casos que acertaram, por grupo (a lista com UF e a lista sem UF, como o bot fazia)."""
    mundo = Mundo()
    leitor = compradores.LeitorDeCompradores(
        Porta(pasta), lambda *_: True, compradores.LIMITE_MAXIMO
    )
    com_uf, sem_uf = _lista(leitor, SUBCLASSE, SP), _lista(leitor, CLASSE, None)
    acertos: dict[str, list[str]] = {}
    for caso in mundo.casos:
        if acertou(com_uf, caso) or acertou(sem_uf, caso):
            acertos.setdefault(caso.grupo, []).append(caso.nome)
    return acertos


@pytest.fixture
def pasta(tmp_path):
    base = tmp_path / "base"
    Mundo().gravar(base)
    compradores.zerar_o_cache()
    yield base
    compradores.zerar_o_cache()


def total(acertos: dict[str, list[str]]) -> int:
    return sum(len(nomes) for nomes in acertos.values())


# ------------------------------------------------------------------ o placar


def test_o_placar_de_partida_e_5_de_29(pasta):
    """A trava: com a regra de hoje o placar é o da simulação (5 de 29), todos do grupo que já aparece sem ajuda."""
    acertos = placar(pasta)
    assert total(acertos) == 5
    assert len(acertos[ACERTA_COM_UF]) == 2 and len(acertos[ACERTA_SEM_UF]) == 3


def test_o_teste_tem_29_negocios_nas_proporcoes_do_pedido():
    casos = Mundo().casos
    por_grupo = {g: sum(c.grupo == g for c in casos) for g in {c.grupo for c in casos}}
    assert len(casos) == 29
    assert por_grupo == {
        ACERTA_COM_UF: 2, ACERTA_SEM_UF: 3, FRACO: 2, SO_O_PROPRIO_NEGOCIO: 12,
        CORTADO_PELOS_50: 2, EMPRESA_BAIXADA: 5, FORA_DE_ALCANCE: 3,
    }  # fmt: skip


def test_o_que_estas_linhas_nao_resolvem_nunca_acerta(pasta):
    acertos = placar(pasta)
    assert not set(acertos) & set(GRUPOS_QUE_ERRAM_PARA_SEMPRE)
