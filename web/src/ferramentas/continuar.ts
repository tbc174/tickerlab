// "Continue a conta": as ferramentas que cada página sugere no fim, e os números que o link leva. Os
// campos de cada ferramenta já vivem no endereço (endereco.ts); no clique, o link copia os que a
// pessoa preencheu para o nome que a outra ferramenta lê. Só vai o que tem a mesma unidade dos dois
// lados (a taxa só quando é ao ano, onde a outra é ao ano); a outra página ainda confere tudo ao ler
// (só número, só opção da lista). Nada sai do navegador.

/** [chave daqui, chave de lá, só se a chave daqui tiver este valor]. */
export type Levar = [string, string, [string, string]?];

export interface Continuacao {
  para: string; // o arquivo da outra ferramenta
  texto: string;
  levar: Levar[];
  fixos?: Record<string, string>; // vão sempre: a escolha que faz sentido vindo daqui (a unidade, o ativo)
}

const SO_AO_ANO: [string, string] = ["unidadeDaTaxa", "ano"];

export const CONTINUACOES: Record<string, Continuacao[]> = {
  "calculadora-de-juros-compostos.html": [
    {
      para: "calculadora-de-aportes-e-metas.html",
      texto: "E guardando um pouco todo mês?",
      levar: [
        ["capital", "inicial"],
        ["taxa", "taxa"],
        ["unidadeDaTaxa", "unidadeDaTaxa"],
      ],
    },
    {
      para: "custo-das-taxas-e-da-queda.html",
      texto: "Quanto 1% de taxa ao ano tira disso?",
      levar: [
        ["capital", "taxa.capital"],
        ["taxa", "taxa.retorno", SO_AO_ANO],
      ],
    },
    {
      para: "calculadora-de-juro-real.html",
      texto: "Quanto rende acima da inflação?",
      levar: [
        ["taxa", "real.nominal", SO_AO_ANO],
        ["inflacao", "real.inflacao"],
      ],
    },
  ],
  "calculadora-de-aportes-e-metas.html": [
    {
      para: "calculadora-viver-de-renda.html",
      texto: "Quanto juntar para viver de renda?",
      levar: [],
    },
    {
      para: "custo-das-taxas-e-da-queda.html",
      texto: "Quanto as taxas levam no caminho?",
      levar: [
        ["inicial", "taxa.capital"],
        ["taxa", "taxa.retorno", SO_AO_ANO],
        ["anos", "taxa.anos"],
      ],
    },
    {
      para: "calculadora-de-juros-compostos.html",
      texto: "E sem guardar mais nada?",
      levar: [
        ["inicial", "capital"],
        ["taxa", "taxa"],
        ["unidadeDaTaxa", "unidadeDaTaxa"],
        ["anos", "prazo"],
      ],
      fixos: { unidadeDoPrazo: "anos" },
    },
  ],
  "custo-das-taxas-e-da-queda.html": [
    {
      para: "fundo-ou-cdb.html",
      texto: "Um fundo com taxa contra um CDB",
      levar: [
        ["taxa.capital", "valor"],
        ["taxa.taxa", "administracao"],
      ],
    },
    {
      para: "calculadora-de-renda-fixa.html",
      texto: "A renda fixa já sem o imposto",
      levar: [["taxa.capital", "valor"]],
    },
    { para: "sorte-em-serie.html", texto: "O fundo que bateu o mercado foi sorte?", levar: [] },
  ],
  "calculadora-viver-de-renda.html": [
    { para: "calculadora-de-aportes-e-metas.html", texto: "Em quanto tempo chego lá?", levar: [] },
    {
      para: "calculadora-de-juro-real.html",
      texto: "Qual rendimento acima da inflação dá para esperar?",
      levar: [],
    },
  ],
  "sorte-em-serie.html": [
    { para: "quanto-daria.html", texto: "A data em que você investiu foi de sorte?", levar: [] },
    { para: "custo-das-taxas-e-da-queda.html", texto: "Quanto a taxa do gestor leva", levar: [] },
  ],
  "calculadora-de-darf.html": [
    { para: "calculadora-de-preco-medio.html", texto: "O preço médio e o resultado de cada venda", levar: [] },
    { para: "calculadora-de-renda-fixa.html", texto: "Na renda fixa, o imposto sai na fonte", levar: [] },
  ],
  "conversor-de-moedas.html": [
    {
      para: "quanto-daria.html",
      texto: "Quanto daria ter guardado em dólar?",
      levar: [], // o valor daqui está na moeda estrangeira; lá é em reais
      fixos: { ativo: "dolar" },
    },
    {
      para: "calculadora-de-correcao-pela-inflacao.html",
      texto: "Quanto um valor do passado vale hoje",
      levar: [],
    },
  ],
  "calculadora-de-renda-fixa.html": [
    {
      para: "fundo-ou-cdb.html",
      texto: "E um fundo, com as taxas e o come-cotas?",
      levar: [
        ["valor", "valor"],
        ["cdb", "cdb"],
      ],
    },
    { para: "calculadora-de-juro-real.html", texto: "Quanto o CDI rende acima da inflação?", levar: [] },
    {
      para: "quanto-daria.html",
      texto: "Quanto o CDI deu desde uma data do passado?",
      levar: [["valor", "valor"]],
      fixos: { ativo: "cdi" },
    },
  ],
  "calculadora-de-juro-real.html": [
    { para: "calculadora-de-correcao-pela-inflacao.html", texto: "Quanto a inflação comeu de um valor", levar: [] },
    { para: "calculadora-de-renda-fixa.html", texto: "A renda fixa já sem o imposto", levar: [] },
  ],
  "calculadora-de-correcao-pela-inflacao.html": [
    {
      para: "quanto-daria.html",
      texto: "E se esse dinheiro estivesse aplicado?",
      levar: [
        ["valor", "valor"],
        ["mesInicial", "mes"],
        ["anoInicial", "ano"],
      ],
    },
    { para: "calculadora-de-juro-real.html", texto: "Quanto rende acima da inflação?", levar: [] },
  ],
  "calculadora-de-preco-medio.html": [
    { para: "calculadora-de-darf.html", texto: "O imposto da venda e o DARF", levar: [] },
    { para: "quanto-daria.html", texto: "A data da compra foi de sorte?", levar: [] },
  ],
  "fundo-ou-cdb.html": [
    {
      para: "calculadora-de-renda-fixa.html",
      texto: "LCI, Tesouro e poupança pelo mesmo prazo",
      levar: [
        ["valor", "valor"],
        ["anos", "prazo"],
        ["cdb", "cdb"],
      ],
      fixos: { unidade: "anos" },
    },
    {
      para: "custo-das-taxas-e-da-queda.html",
      texto: "Quanto a taxa de administração leva em 20 anos",
      levar: [
        ["valor", "taxa.capital"],
        ["administracao", "taxa.taxa"],
      ],
    },
  ],
  "simulador-de-financiamento.html": [
    {
      para: "calculadora-de-juros-compostos.html",
      texto: "A mesma taxa a seu favor, num investimento",
      levar: [
        ["taxa", "taxa"],
        ["unidadeDaTaxa", "unidadeDaTaxa"],
      ],
    },
    { para: "calculadora-de-aportes-e-metas.html", texto: "Quanto guardar para dar a entrada", levar: [] },
  ],
  "quanto-daria.html": [
    { para: "sorte-em-serie.html", texto: "Cem estratégias de cara ou coroa", levar: [] },
    {
      para: "calculadora-de-correcao-pela-inflacao.html",
      texto: "O mesmo valor corrigido pela inflação",
      levar: [
        ["valor", "valor"],
        ["mes", "mesInicial"],
        ["ano", "anoInicial"],
      ],
    },
  ],
};

/** O endereço da outra ferramenta com os números que estão em `busca` (o endereço desta). */
export function enderecoDaContinuacao(c: Pick<Continuacao, "para" | "levar" | "fixos">, busca: string): string {
  const daqui = new URLSearchParams(busca);
  const la = new URLSearchParams();
  for (const [de, para, se] of c.levar) {
    const valor = daqui.get(de);
    if (valor === null || (se && daqui.get(se[0]) !== se[1])) continue;
    la.set(para, valor);
  }
  for (const [chave, valor] of Object.entries(c.fixos ?? {})) la.set(chave, valor);
  const texto = la.toString();
  return `/${c.para}${texto ? `?${texto}` : ""}`;
}

/** No navegador: antes de seguir um link "continue a conta", põe nele os números de agora. */
export function ligarContinuacoes(raiz: Document = document): void {
  const atualizar = (evento: Event) => {
    const link = (evento.target as Element | null)?.closest?.<HTMLAnchorElement>("a[data-levar]");
    if (!link) return;
    const { para, levar, fixos } = JSON.parse(link.dataset.levar!) as Continuacao;
    link.setAttribute("href", enderecoDaContinuacao({ para, levar, fixos }, window.location.search));
  };
  // o clique, o botão do meio e o teclado passam por um destes antes de seguir o link
  for (const tipo of ["pointerdown", "focusin", "click"]) raiz.addEventListener(tipo, atualizar, true);
}
