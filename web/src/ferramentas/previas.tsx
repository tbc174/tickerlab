// A prévia de cada ferramenta na vitrine: um gráfico pequeno em SVG, feito no build com as mesmas
// contas da ferramenta e o exemplo dela (nada de imagem). É só a forma do resultado: sem números e
// escondida dos leitores de tela (o nome e a descrição do cartão dizem o que a ferramenta faz). As
// que dependem dos dados do dia (CDI, IPCA, câmbio) usam valores de exemplo fixos, porque a página
// sai pronta do build.
import { calcularFinanciamento, EXEMPLO_DO_FINANCIAMENTO } from "./Financiamento";
import { EXEMPLO_DO_FUNDO, curvas } from "./FundosERendaFixa";
import { apurarOAno, EXEMPLO_DO_ANO } from "./CalculadoraDeDarf";
import { EXEMPLO_DO_PRECO_MEDIO, operacoesDosCampos } from "./PrecoMedio";
import { EXEMPLO_DE_APORTES } from "./AportesEMetas";
import { EXEMPLO_DE_JUROS } from "./CalculadoraDeJuros";
import { EXEMPLO_DA_TAXA } from "./CustoDasTaxas";
import { EXEMPLO_DO_JURO_REAL } from "./JuroReal";
import { EXEMPLO_DA_RENDA_FIXA } from "./RendaFixa";
import { EXEMPLO_DA_SORTE, SEMENTE_INICIAL } from "./SorteEmSerie";
import { EXEMPLO_DE_RENDA } from "./ViverDeRenda";
import { evolucao as evolucaoDosAportes } from "./contas/aportes";
import { evolucaoDaTaxa } from "./contas/custos";
import { evolucao as evolucaoDosJuros, taxaPorMes } from "./contas/juros";
import { calcular as calcularPrecoMedio } from "./contas/preco_medio";
import { comparar } from "./contas/renda_fixa";
import { DIAS_POR_ANO, simular as simularASorte } from "./contas/sorte_em_serie";
import { juroReal } from "./contas/taxas";
import { patrimonioNecessario, trajetoria } from "./contas/viver_de_renda";
import { lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";

export interface Previa {
  tipo: "linhas" | "barras";
  series: number[][]; // até 4, uma cor de SERIES cada, na ordem
}

// os dados do dia não existem no build: valores de exemplo, só para a forma
const CDI_DE_EXEMPLO = 0.14;
const IPCA_DE_EXEMPLO = 0.045;
const POUPANCA_DE_EXEMPLO = 0.0067;
const MESES_POR_ANO = 12;
const DIAS_POR_ANO_CORRIDO = 365;
const PONTOS_MAXIMOS = 48;
const LARGURA = 120;
const ALTURA = 40;
const MARGEM = 2;
const BARRA_MAXIMA = 14; // com poucas barras, elas não ocupam o cartão inteiro

const linhas = (...series: number[][]): Previa => ({ tipo: "linhas", series });
const barras = (valores: number[]): Previa => ({ tipo: "barras", series: [valores] });

/** No máximo PONTOS_MAXIMOS pontos, mantendo o primeiro e o último. */
function resumir(valores: number[]): number[] {
  if (valores.length <= PONTOS_MAXIMOS) return valores;
  const passo = (valores.length - 1) / (PONTOS_MAXIMOS - 1);
  return Array.from({ length: PONTOS_MAXIMOS }, (_, k) => valores[Math.round(k * passo)]);
}

/** O número de um campo do exemplo (os exemplos são sempre números válidos). */
const n = (texto: string) => lerNumero(texto) ?? 0;
const fracao = (texto: string) => n(texto) / 100;

function semErro<T>(conta: T | string): T {
  if (typeof conta === "string") throw new Error(`o exemplo da ferramenta não fecha: ${conta}`);
  return conta;
}

/** Uma curva em forma de sino: quantas datas dariam cada resultado (a régua do "quanto daria"). */
const sino = Array.from({ length: 15 }, (_, k) => Math.exp(-(((k - 6) / 3) ** 2)));

export const PREVIAS: Record<string, () => Previa> = {
  "calculadora-de-juros-compostos.html": () => {
    const { capital, taxa, unidadeDaTaxa, prazo, unidadeDoPrazo } = EXEMPLO_DE_JUROS;
    const meses = n(prazo) * (unidadeDoPrazo === "anos" ? MESES_POR_ANO : 1);
    return linhas(evolucaoDosJuros(n(capital), taxaPorMes(fracao(taxa), unidadeDaTaxa), meses).map((l) => l.montante));
  },
  "calculadora-de-aportes-e-metas.html": () => {
    const { inicial, aporte, taxa, unidadeDaTaxa, anos } = EXEMPLO_DE_APORTES;
    const meses = evolucaoDosAportes(n(inicial), n(aporte), taxaPorMes(fracao(taxa), unidadeDaTaxa), n(anos) * MESES_POR_ANO);
    return linhas(
      meses.map((l) => l.saldo),
      meses.map((l) => l.aportado),
    );
  },
  "custo-das-taxas-e-da-queda.html": () => {
    const { capital, retorno, taxa, anos: prazo } = EXEMPLO_DA_TAXA;
    const anos = evolucaoDaTaxa(n(capital), fracao(retorno), fracao(taxa), n(prazo));
    return linhas(
      anos.map((l) => l.sem_taxa),
      anos.map((l) => l.com_taxa),
    );
  },
  "calculadora-viver-de-renda.html": () => {
    // consumindo o patrimônio no prazo do exemplo (só com os juros, a linha seria reta)
    const { renda, taxa, anos } = EXEMPLO_DE_RENDA;
    const patrimonio = patrimonioNecessario(n(renda), fracao(taxa), n(anos));
    return linhas(trajetoria(patrimonio, n(renda), [fracao(taxa)], n(anos) * MESES_POR_ANO));
  },
  "sorte-em-serie.html": () => {
    const r = simularASorte(n(EXEMPLO_DA_SORTE.quantidade), n(EXEMPLO_DA_SORTE.anos) * DIAS_POR_ANO, SEMENTE_INICIAL);
    return linhas(r.curva_da_melhor, r.curva_da_mediana, r.curva_da_pior);
  },
  "calculadora-de-darf.html": () => barras(semErro(apurarOAno(EXEMPLO_DO_ANO)).meses.map((m) => m.darf)),
  "conversor-de-moedas.html": () => linhas([0, 1]), // a conversão é uma reta: o valor vezes a cotação
  "calculadora-de-renda-fixa.html": () => {
    const { valor, prazo, cdb, lci } = EXEMPLO_DA_RENDA_FIXA; // o prazo do exemplo é em anos
    const dias = n(prazo) * DIAS_POR_ANO_CORRIDO;
    const opcoes = comparar(n(valor), dias, [CDI_DE_EXEMPLO], fracao(cdb), fracao(lci), POUPANCA_DE_EXEMPLO);
    return barras(opcoes.map((o) => o.liquido - n(valor)));
  },
  "calculadora-de-juro-real.html": () => {
    const [nominal, inflacao] = [fracao(EXEMPLO_DO_JURO_REAL.nominal), fracao(EXEMPLO_DO_JURO_REAL.inflacao)];
    return barras([nominal, inflacao, juroReal(nominal, inflacao)]);
  },
  "calculadora-de-correcao-pela-inflacao.html": () =>
    linhas(Array.from({ length: 11 }, (_, ano) => (1 + IPCA_DE_EXEMPLO) ** ano)),
  "calculadora-de-preco-medio.html": () =>
    barras(calcularPrecoMedio(operacoesDosCampos(EXEMPLO_DO_PRECO_MEDIO)).map((l) => l.custo_total)),
  "fundo-ou-cdb.html": () => {
    const { fundo, cdb } = curvas(EXEMPLO_DO_FUNDO, CDI_DE_EXEMPLO, 1);
    return linhas(cdb, fundo);
  },
  "simulador-de-financiamento.html": () => {
    const r = semErro(calcularFinanciamento(EXEMPLO_DO_FINANCIAMENTO));
    return linhas(
      r.sac.map((l) => l.parcela),
      r.price.map((l) => l.parcela),
    );
  },
  "quanto-daria.html": () => barras(sino),
};

function escala(series: number[][], tipo: Previa["tipo"]): [number, number] {
  const todos = series.flat();
  const menor = tipo === "barras" ? Math.min(0, ...todos) : Math.min(...todos);
  const maior = Math.max(...todos);
  return [menor, maior > menor ? maior : menor + 1];
}

/** O gráfico pequeno do cartão, na largura do cartão (viewBox) e sem números. */
export function GraficoDaPrevia({ previa }: { previa: Previa }) {
  const series = previa.series.map(resumir);
  const [menor, maior] = escala(series, previa.tipo);
  const y = (v: number) => MARGEM + (ALTURA - 2 * MARGEM) * (1 - (v - menor) / (maior - menor));
  return (
    <svg className="previa" viewBox={`0 0 ${LARGURA} ${ALTURA}`} preserveAspectRatio="none" aria-hidden="true" focusable="false">
      {previa.tipo === "linhas"
        ? series.map((valores, k) => {
            const x = (i: number) => MARGEM + ((LARGURA - 2 * MARGEM) * i) / Math.max(valores.length - 1, 1);
            const pontos = valores.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
            return <polyline key={k} points={pontos} fill="none" stroke={SERIES[k]} strokeWidth="2" vectorEffect="non-scaling-stroke" />;
          })
        : series[0].map((v, i, valores) => {
            const largura = Math.min((LARGURA - 2 * MARGEM) / valores.length, BARRA_MAXIMA + 2);
            const inicio = (LARGURA - largura * valores.length) / 2;
            const topo = Math.min(y(v), y(0));
            return (
              <rect
                key={i}
                x={(inicio + i * largura + 1).toFixed(1)}
                y={topo.toFixed(1)}
                width={Math.max(largura - 2, 1).toFixed(1)}
                height={Math.max(Math.abs(y(0) - y(v)), 1).toFixed(1)}
                rx="1.5"
                fill={SERIES[0]}
              />
            );
          })}
    </svg>
  );
}
