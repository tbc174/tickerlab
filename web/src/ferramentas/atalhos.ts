// Os valores de hoje em um clique ("Selic hoje", "IPCA esperado 2027"...), a partir do arquivo de
// dados abertos das ferramentas. Cada atalho leva a data e a fonte na dica e avisa quando o dado está
// velho; série que falta no arquivo não vira atalho. O Focus é "expectativa do mercado", nunca
// previsão do TickerLab.
import type { Atalho } from "./campos";
import { em12Meses } from "./contas/inflacao";
import { type DadosDoBc, dataBrasileira, diasUteisDesde, estaVelho } from "./dados";
import { formatarNumero } from "./numeros";

const BANCO_CENTRAL = "Banco Central";
const TESOURO = "Tesouro Nacional";
const ANOS_DE_REFERENCIA_DO_IPCA_MAIS = 10; // o juro real "de longo prazo": o IPCA+ mais perto de 10 anos
const DIAS_POR_ANO = 365.25;

const emPorcento = (fracao: number) => formatarNumero(fracao * 100);

function dica(texto: string, data: string, fonte: string, hoje: Date): string {
  const aviso = estaVelho(data, hoje) ? ` (dado de ${diasUteisDesde(data, hoje)} dias úteis atrás)` : "";
  return `${texto}${aviso} · ${fonte}`;
}

/** Selic e CDI de hoje, em % ao ano. */
export function atalhosDeJuros(dados: DadosDoBc, hoje: Date): Atalho[] {
  const atalhos: Atalho[] = [];
  if (dados.selic_meta) {
    const { ao_ano, data } = dados.selic_meta;
    atalhos.push({ rotulo: "Selic hoje", valor: emPorcento(ao_ano), dica: dica(`Meta da Selic em ${dataBrasileira(data)}`, data, BANCO_CENTRAL, hoje) });
  }
  if (dados.cdi) {
    const { ao_ano, data } = dados.cdi;
    atalhos.push({ rotulo: "CDI hoje", valor: emPorcento(ao_ano), dica: dica(`CDI de ${dataBrasileira(data)}, ao ano`, data, BANCO_CENTRAL, hoje) });
  }
  return atalhos;
}

/** O IPCA dos últimos 12 meses e o esperado pelo Focus para este ano e o próximo, em % ao ano. */
export function atalhosDeInflacao(dados: DadosDoBc, hoje: Date): Atalho[] {
  const atalhos: Atalho[] = [];
  if (dados.ipca && dados.ipca.meses.length >= 12) {
    atalhos.push({
      rotulo: "IPCA 12 meses",
      valor: emPorcento(em12Meses(dados.ipca.meses)),
      dica: `IPCA acumulado em 12 meses até ${dados.ipca.ultimo.slice(5)}/${dados.ipca.ultimo.slice(0, 4)} · ${BANCO_CENTRAL}`,
    });
  }
  const focus = dados.focus?.ipca;
  if (focus) {
    for (const ano of [hoje.getFullYear(), hoje.getFullYear() + 1]) {
      const esperado = focus.anos[String(ano)];
      if (esperado === undefined) continue;
      atalhos.push({
        rotulo: `IPCA esperado ${ano}`,
        valor: emPorcento(esperado),
        dica: dica(`Expectativa do mercado (mediana do Focus) de ${dataBrasileira(focus.data)}`, focus.data, BANCO_CENTRAL, hoje),
      });
    }
  }
  return atalhos;
}

/** O juro real de hoje: a taxa do Tesouro IPCA+ com o vencimento mais perto de 10 anos. */
export function atalhosDeJuroReal(dados: DadosDoBc, hoje: Date): Atalho[] {
  const titulos = dados.tesouro?.titulos.filter((t) => t.titulo === "Tesouro IPCA+") ?? [];
  if (!dados.tesouro || titulos.length === 0) return [];
  const anosAte = (vencimento: string) =>
    (new Date(`${vencimento}T12:00:00`).getTime() - hoje.getTime()) / (DIAS_POR_ANO * 24 * 3600 * 1000);
  const distancia = (vencimento: string) => Math.abs(anosAte(vencimento) - ANOS_DE_REFERENCIA_DO_IPCA_MAIS);
  const escolhido = titulos.reduce((melhor, t) => (distancia(t.vencimento) < distancia(melhor.vencimento) ? t : melhor));
  const { data } = dados.tesouro;
  return [
    {
      rotulo: `Tesouro IPCA+ ${escolhido.vencimento.slice(0, 4)}`,
      valor: emPorcento(escolhido.taxa),
      dica: dica(`Taxa real de compra em ${dataBrasileira(data)}`, data, TESOURO, hoje),
    },
  ];
}
