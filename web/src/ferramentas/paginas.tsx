// As páginas das ferramentas grátis e a vitrine delas. Os números dos exemplos do texto saem das
// mesmas contas da calculadora (nada digitado à mão que possa ficar diferente).
import { regrasDeImposto } from "../conteudo";
import { TopoDaPagina } from "../site/Fundo";
import { AnuncioDaCasa } from "./AnuncioDaCasa";
import { altaParaRecuperar, custoDaTaxa } from "./contas/custos";
import { montante, taxaEquivalente } from "./contas/juros";
import { duracaoEmMeses, patrimonioNecessario } from "./contas/viver_de_renda";
import { duracaoPorExtenso } from "./ViverDeRenda";
import { simular } from "./contas/sorte_em_serie";
import { SEMENTE_INICIAL } from "./SorteEmSerie";
import { formatarDecimal } from "../app/formatar";
import { formatarPorcentagem, formatarReais } from "./numeros";
import { PaginaDeFerramenta } from "./Pagina";

export interface FerramentaDoSite {
  arquivo: string;
  nome: string;
  descricao: string;
}

// a ordem da vitrine; cada uma tem a sua página e a sua rota (rotas.tsx)
export const FERRAMENTAS_DO_SITE: FerramentaDoSite[] = [
  {
    arquivo: "calculadora-de-juros-compostos.html",
    nome: "Juros simples e compostos",
    descricao: "Quanto um valor rende ao longo do tempo, mês a mês.",
  },
  {
    arquivo: "calculadora-de-aportes-e-metas.html",
    nome: "Aportes e metas",
    descricao: "Quanto você vai ter, quanto guardar por mês e em quanto tempo chega lá.",
  },
  {
    arquivo: "custo-das-taxas-e-da-queda.html",
    nome: "Custo das taxas e da queda",
    descricao: "Quanto 1% ao ano leva em 20 anos, e quanto é preciso subir depois de cair.",
  },
  {
    arquivo: "calculadora-viver-de-renda.html",
    nome: "Viver de renda",
    descricao: "Quanto juntar para tirar um valor por mês, e o risco de começar num ano ruim.",
  },
  {
    arquivo: "sorte-em-serie.html",
    nome: "Sorte em série",
    descricao: "Cem estratégias de cara ou coroa: a melhor parece genial, e é só sorte.",
  },
  {
    arquivo: "calculadora-de-darf.html",
    nome: "Imposto sobre ações (DARF)",
    descricao: "O imposto do mês, a isenção de R$ 20 mil, o prejuízo a compensar e o código do DARF.",
  },
  {
    arquivo: "conversor-de-moedas.html",
    nome: "Conversor de moedas",
    descricao: "Dólar, euro, libra e mais 7 moedas pela PTAX, a cotação oficial do Banco Central.",
  },
  {
    arquivo: "calculadora-de-renda-fixa.html",
    nome: "Renda fixa com IR",
    descricao: "CDB, LCI/LCA, Tesouro Selic e poupança pelo mesmo prazo, já sem o imposto.",
  },
  {
    arquivo: "calculadora-de-juro-real.html",
    nome: "Juro real e taxas",
    descricao: "Quanto rende acima da inflação, e a taxa ao mês ou ao ano equivalente.",
  },
  {
    arquivo: "calculadora-de-correcao-pela-inflacao.html",
    nome: "Correção pela inflação",
    descricao: "Quanto um valor do passado vale hoje, corrigido pelo IPCA.",
  },
];

const codigo = (arquivo: string) => arquivo.replace(/\.html$/, "");

// --- Juros simples e compostos -------------------------------------------------------------
const JUROS = "calculadora-de-juros-compostos.html";

export const DADOS_DOS_JUROS = {
  caminho: `/${JUROS}`,
  titulo: "Calculadora de juros compostos",
  descricao:
    "Calcule quanto um valor rende com juros compostos ou simples, com a taxa ao mês ou ao " +
    "ano e a evolução mês a mês. Grátis e sem cadastro.",
  atual: "/ferramentas.html",
  ferramenta: true,
};

export function PaginaDosJuros() {
  const em10 = montante(10000, 0.1, 10);
  const em30 = montante(10000, 0.1, 30);
  return (
    <PaginaDeFerramenta
      titulo="Calculadora de juros compostos"
      subtitulo="Quanto um valor rende ao longo do tempo, com juros simples ou compostos. Grátis e sem cadastro."
      ilha="juros"
      codigo={codigo(JUROS)}
      anuncio="ficha"
      foraDaConta={[
        "imposto de renda",
        "taxas e custos",
        "inflação: o resultado está em reais do futuro, que compram menos que os de hoje",
      ]}
    >
      <h2>O que são juros compostos</h2>
      <p>
        Nos juros compostos, o juro de cada mês é calculado sobre o valor do mês anterior, que já
        inclui os juros que vieram antes: é o juro sobre juro. Nos juros simples, o juro é sempre
        calculado sobre o valor aplicado no começo, e por isso é o mesmo todo mês.
      </p>
      <p>
        A conta dos compostos é <code>valor final = valor aplicado × (1 + taxa)^prazo</code>, com a
        taxa e o prazo na mesma unidade (ao mês com meses, ao ano com anos).
      </p>
      <h2>Por que o prazo pesa mais que a taxa</h2>
      <p>
        No começo, a diferença entre os dois tipos de juros é pequena; com o tempo, ela cresce cada
        vez mais rápido. Com R$ 10.000 a 10% ao ano, os juros simples dão R$ 20.000 em 10 anos e os
        compostos, {formatarReais(em10)}. Em 30 anos, são R$ 40.000 contra {formatarReais(em30)}.
      </p>
      <h2>Taxa ao mês ou ao ano</h2>
      <p>
        12% ao ano não é o mesmo que 1% ao mês: 1% ao mês, composto por 12 meses, dá{" "}
        {formatarPorcentagem(taxaEquivalente(0.01, 1, 12))} ao ano. Quando você escolhe uma taxa ao
        ano, a calculadora usa a taxa mensal equivalente, a que dá o mesmo resultado em 12 meses.
      </p>
    </PaginaDeFerramenta>
  );
}

// --- Aportes e metas -------------------------------------------------------------------------
const APORTES = "calculadora-de-aportes-e-metas.html";

export const DADOS_DOS_APORTES = {
  caminho: `/${APORTES}`,
  titulo: "Calculadora de aportes e metas",
  descricao:
    "Simule aportes mensais: quanto você vai ter, quanto guardar por mês para chegar a uma meta " +
    "e em quanto tempo chega lá. Grátis e sem cadastro.",
  atual: "/ferramentas.html",
  ferramenta: true,
};

export function PaginaDosAportes() {
  return (
    <PaginaDeFerramenta
      titulo="Calculadora de aportes e metas"
      subtitulo="Quanto você vai ter guardando todo mês, quanto guardar para chegar a uma meta e em quanto tempo. Grátis e sem cadastro."
      ilha="aportes"
      codigo={codigo(APORTES)}
      anuncio="cadastro"
      foraDaConta={[
        "imposto de renda",
        "taxas e custos",
        "um rendimento que muda: a conta usa o mesmo todo mês, e na vida real ele sobe e desce",
      ]}
    >
      <h2>Dinheiro de hoje ou do futuro</h2>
      <p>
        Daqui a 20 anos, R$ 200 mil vão comprar bem menos do que hoje. Se você usar no rendimento a
        taxa <strong>acima da inflação</strong> (o juro real, por exemplo 4% ao ano em vez de 8%), o
        resultado sai em dinheiro de hoje, e a meta também fica em dinheiro de hoje.
      </p>
      <h2>O que vem do bolso e o que vem dos juros</h2>
      <p>
        O resultado separa o que você guardou do que os juros trouxeram. Nos primeiros anos, quase
        tudo vem do bolso; os juros só passam a pesar com o tempo, porque rendem sobre um saldo cada
        vez maior.
      </p>
      <h2>Aporte no começo ou no fim do mês</h2>
      <p>
        A calculadora considera que o aporte entra no fim de cada mês, como quem investe depois de
        receber o salário. Começar um mês antes faz diferença pequena; começar anos antes faz
        diferença grande.
      </p>
    </PaginaDeFerramenta>
  );
}

// --- Custo das taxas e da queda ------------------------------------------------------------
const CUSTOS = "custo-das-taxas-e-da-queda.html";
const QUEDAS_COMUNS = [-0.1, -0.2, -0.3, -0.5, -0.8];

export const DADOS_DOS_CUSTOS = {
  caminho: `/${CUSTOS}`,
  titulo: "Custo das taxas e da queda",
  descricao:
    "Calcule quanto uma taxa de administração leva do seu patrimônio em 20 anos e quanto um " +
    "investimento precisa subir para recuperar uma queda. Grátis e sem cadastro.",
  atual: "/ferramentas.html",
  ferramenta: true,
};

export function PaginaDosCustos() {
  const exemplo = custoDaTaxa(100000, 0.08, 0.01, 20);
  return (
    <PaginaDeFerramenta
      titulo="Custo das taxas e da queda"
      subtitulo="Duas contas que parecem pequenas e não são: a taxa cobrada todo ano e a alta que uma queda pede. Grátis e sem cadastro."
      ilha={[
        ["taxa", "Quanto a taxa leva"],
        ["queda", "Quanto subir depois de cair"],
      ]}
      codigo={codigo(CUSTOS)}
      anuncio="ficha"
      foraDaConta={[
        "imposto de renda",
        "taxa de performance e outros custos além da taxa anual",
        "rendimento que muda de um ano para outro: a conta usa o mesmo todo ano",
      ]}
    >
      <h2>Por que 1% ao ano não é pouco</h2>
      <p>
        A taxa de administração é cobrada todo ano sobre todo o patrimônio, inclusive sobre o que
        ela já deixou de render. Com R$ 100.000 rendendo 8% ao ano por 20 anos, uma taxa de 1% ao ano
        leva {formatarReais(exemplo.ficou_com_a_taxa)}: {formatarPorcentagem(exemplo.fracao_do_resultado)}{" "}
        do que você teria sem ela.
      </p>
      <h2>Quedas e recuperações</h2>
      <p>
        Uma queda e uma alta do mesmo tamanho não se anulam: depois de cair 50%, R$ 100 viram R$ 50,
        e para voltar a R$ 100 é preciso subir 100%. Por isso o tamanho da maior queda importa tanto
        quanto o retorno médio de um investimento ou de uma estratégia.
      </p>
      <table>
        <thead>
          <tr>
            <th scope="col">Queda</th>
            <th scope="col">Alta para voltar</th>
          </tr>
        </thead>
        <tbody>
          {QUEDAS_COMUNS.map((queda) => (
            <tr key={queda}>
              <td>{formatarPorcentagem(queda)}</td>
              <td>+{formatarPorcentagem(altaParaRecuperar(queda))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </PaginaDeFerramenta>
  );
}

// --- Viver de renda ------------------------------------------------------------------------
const RENDA = "calculadora-viver-de-renda.html";

export const DADOS_DA_RENDA = {
  caminho: `/${RENDA}`,
  titulo: "Calculadora para viver de renda",
  descricao:
    "Quanto juntar para viver de renda, em dinheiro de hoje: só com os juros ou gastando o " +
    "principal, e o que muda se o primeiro ano for ruim. Grátis e sem cadastro.",
  atual: "/ferramentas.html",
  ferramenta: true,
};

export function PaginaDaRenda() {
  const em30 = patrimonioNecessario(5000, 0.04, 30);
  const comQueda = duracaoEmMeses(em30, 5000, [-0.3, 0.04]);
  return (
    <PaginaDeFerramenta
      titulo="Calculadora para viver de renda"
      subtitulo="Quanto juntar para tirar um valor por mês, em dinheiro de hoje, e o risco que a média esconde. Grátis e sem cadastro."
      ilha="renda"
      codigo={codigo(RENDA)}
      anuncio="ficha"
      foraDaConta={[
        "imposto de renda e taxas",
        "inflação diferente da sua: a conta usa um rendimento acima da inflação e uma renda sempre com o mesmo poder de compra",
        "anos bons e ruins de verdade: além do exemplo da queda no primeiro ano, a conta usa o mesmo rendimento todo ano",
      ]}
    >
      <h2>Em dinheiro de hoje</h2>
      <p>
        Daqui a 30 anos, R$ 5.000 vão comprar bem menos. Por isso a calculadora trabalha com o
        rendimento <strong>acima da inflação</strong> (o juro real): o patrimônio e a renda saem no
        poder de compra de hoje, e a renda acompanha a inflação o tempo todo.
      </p>
      <h2>Só com os juros ou gastando o principal</h2>
      <p>
        Só com os juros, o patrimônio nunca acaba, mas é preciso juntar mais. Gastando também o
        que juntou, precisa de menos: com R$ 5.000 por mês e 4% ao ano acima da inflação, por 30
        anos, são {formatarReais(em30)}.
      </p>
      <h2>O risco que a média esconde</h2>
      <p>
        O mesmo rendimento médio pode dar resultados bem diferentes conforme a ordem dos anos. Se o
        primeiro ano cair 30%, quem está retirando todo mês vende na baixa, e o dinheiro planejado
        para 30 anos dura {duracaoPorExtenso(comQueda)}. A mesma queda perto do fim quase não faz
        diferença. É o chamado risco de sequência.
      </p>
      <h2>E a “regra dos 4%”?</h2>
      <p>
        A regra diz que dá para retirar 4% do patrimônio do primeiro ano, corrigidos pela inflação,
        por cerca de 30 anos. Ela veio de estudos com ações e títulos dos Estados Unidos no século
        20; aqui ela aparece só como comparação, não como garantia.
      </p>
    </PaginaDeFerramenta>
  );
}

// --- Sorte em série ------------------------------------------------------------------------
const SORTE = "sorte-em-serie.html";

export const DADOS_DA_SORTE = {
  caminho: `/${SORTE}`,
  titulo: "Sorte em série",
  descricao:
    "Simule 100 estratégias de cara ou coroa e veja a melhor parecer genial por puro acaso: o " +
    "problema de testar muitas ideias e mostrar só a melhor. Grátis e sem cadastro.",
  atual: "/ferramentas.html",
  ferramenta: true,
};

export function PaginaDaSorte() {
  const exemplo = simular(100, 250, SEMENTE_INICIAL);
  return (
    <PaginaDeFerramenta
      titulo="Sorte em série"
      subtitulo="Cem estratégias que decidem no cara ou coroa. Nenhuma tem vantagem, e mesmo assim a melhor parece genial."
      ilha="sorte"
      codigo={codigo(SORTE)}
      anuncio="ficha"
      foraDaConta={[
        "custos e impostos: com eles, as estratégias de moeda ficariam ainda pior",
        "mercados de verdade, que têm tendência, quedas fortes e dias parados; aqui todo dia é +1% ou -1%",
      ]}
    >
      <h2>O que a simulação mostra</h2>
      <p>
        No exemplo da página, com 100 estratégias de moeda por um ano, a melhor rendeu{" "}
        {formatarPorcentagem(exemplo.retorno_da_melhor)} com Sharpe de{" "}
        {formatarDecimal(exemplo.sharpe_da_melhor)}, e {exemplo.com_sharpe_acima_de_1} delas passaram
        de Sharpe 1, um número que muita gente chama de estratégia boa. Nenhuma tinha vantagem
        nenhuma: era tudo sorte.
      </p>
      <h2>Por que isso importa</h2>
      <p>
        Quem testa muitas regras de compra e venda, ou muitos ajustes da mesma regra, e mostra só a
        melhor, está fazendo a mesma coisa que esta página: escolhendo a moeda que deu mais caras.
        Quanto mais tentativas, melhor parece a campeã, mesmo sem vantagem nenhuma. Na estatística,
        isso se chama problema das comparações múltiplas.
      </p>
      <h2>Como o TickerLab desconta a sorte</h2>
      <p>
        A ficha “Foi sorte?” do TickerLab conta quantas tentativas você fez e testa o resultado
        contra estratégias sorteadas como estas, com custos e fora do período em que a regra foi
        ajustada. Só passa o que resiste quando a sorte sai da conta.
      </p>
      <h2>E por que menos da metade terminou no lucro?</h2>
      <p>
        Ganhar 1% e depois perder 1% não volta ao começo: R$ 100 viram R$ 101 e depois R$ 99,99. Com
        altas e baixas do mesmo tamanho, o vaivém sozinho corrói o resultado.
      </p>
    </PaginaDeFerramenta>
  );
}

// --- Imposto sobre ações (DARF) -------------------------------------------------------------
const DARF = "calculadora-de-darf.html";
const REGRAS_DO_DARF = [
  "aliquota_comum",
  "aliquota_day_trade",
  "isencao_vendas_no_mes",
  "irrf_comum",
  "irrf_day_trade",
  "codigo_do_darf",
  "darf_minimo",
];

export const DADOS_DO_DARF = {
  caminho: `/${DARF}`,
  titulo: "Calculadora de DARF de ações",
  descricao:
    "Calcule o imposto sobre ações do mês: swing trade e day trade, isenção de R$ 20 mil, " +
    "prejuízo a compensar, IR retido e o DARF 6015. Regras da Receita, grátis e sem cadastro.",
  atual: "/ferramentas.html",
  ferramenta: true,
};

/** "15%", "R$ 20.000", "6015": o valor de uma regra como a pessoa lê. */
function valorDaRegra(valor: number | string, chave: string): string {
  if (typeof valor === "string") return valor;
  return chave.startsWith("aliquota") || chave.startsWith("irrf")
    ? formatarPorcentagem(valor, 3)
    : formatarReais(valor);
}

export function PaginaDoDarf() {
  const regras = REGRAS_DO_DARF.map((chave) => regrasDeImposto.regras.find((r) => r.chave === chave)!);
  const conferida = regras[0].conferida_em.split("-").reverse().join("/");
  return (
    <PaginaDeFerramenta
      titulo="Calculadora de DARF de ações"
      subtitulo="O imposto de um mês de operações com ações na B3, com as regras da Receita Federal. Grátis e sem cadastro."
      ilha="darf"
      codigo={codigo(DARF)}
      anuncio="ficha"
      foraDaConta={[
        "FII, ETF, BDR, opções, termo e futuros, que têm regras próprias",
        "o cálculo do preço médio: o resultado de cada mês entra pronto, com corretagem e taxas descontadas",
        "a declaração anual: o prejuízo e o IR retido também vão para o Demonstrativo de Renda Variável",
      ]}
      fonte={`Receita Federal, Perguntas e Respostas IRPF 2026, e Lei 9.430/1996; regras conferidas em ${conferida}`}
    >
      <h2>As regras que a calculadora usa</h2>
      <ul>
        {regras.map((r) => (
          <li key={r.chave}>
            {r.descricao}: <strong>{valorDaRegra(r.valor, r.chave)}</strong> (
            <a href={r.fonte} rel="noopener">
              {r.onde}
            </a>
            )
          </li>
        ))}
      </ul>
      <h2>A isenção de R$ 20 mil</h2>
      <p>
        Vale para quem vendeu até R$ 20.000 em ações no mês, somando todas as vendas comuns (não o
        lucro). Não vale para day trade, ETF, FII nem fundos. O lucro isento não gasta o prejuízo
        que você tem para compensar: ele continua guardado para um mês com imposto.
      </p>
      <h2>Prejuízo, IR retido e DARF pequeno</h2>
      <p>
        O prejuízo de um mês abate o lucro dos meses seguintes, sem prazo, mas só do mesmo tipo:
        day trade com day trade, operações comuns com comuns. O IR retido na fonte (o “dedo-duro”)
        abate o imposto do mês, e o que sobra fica para depois. Se o DARF der menos de R$ 10, não
        se paga: o valor soma ao imposto do mês seguinte.
      </p>
      <p>
        A calculadora ajuda a conferir a conta e não substitui um contador nem a orientação da
        Receita Federal.
      </p>
    </PaginaDeFerramenta>
  );
}

// --- Ferramentas com dados do Banco Central --------------------------------------------------
const FONTE_DO_BC = "Banco Central do Brasil (dados abertos), atualizados uma vez por dia útil";
const pagina = (arquivo: string, titulo: string, descricao: string) => ({
  caminho: `/${arquivo}`,
  titulo,
  descricao,
  atual: "/ferramentas.html",
  ferramenta: true,
});

const MOEDAS = "conversor-de-moedas.html";
export const DADOS_DO_CONVERSOR = pagina(
  MOEDAS,
  "Conversor de moedas pela PTAX",
  "Converta real, dólar, euro, libra, iene e mais moedas pela PTAX, a cotação oficial do Banco " +
    "Central. Grátis e sem cadastro.",
);

export function PaginaDoConversor() {
  return (
    <PaginaDeFerramenta
      titulo="Conversor de moedas pela PTAX"
      subtitulo="Real, dólar, euro, libra, iene e mais 6 moedas, pela cotação oficial do Banco Central. Grátis e sem cadastro."
      ilha="moedas"
      codigo={codigo(MOEDAS)}
      anuncio="cadastro"
      foraDaConta={[
        "o spread e o IOF que bancos e casas de câmbio cobram: o valor que você paga é maior",
        "a cotação de agora: a PTAX é a oficial de fechamento de um dia útil, divulgada por volta das 13h",
      ]}
      fonte={FONTE_DO_BC}
    >
      <h2>O que é a PTAX</h2>
      <p>
        É a cotação oficial que o Banco Central calcula a cada dia útil, pela média do que os bancos
        negociaram em quatro momentos do dia, e divulga por volta das 13h. É a usada em contratos e
        na declaração do Imposto de Renda. Antes do fechamento do dia, vale a do dia útil anterior.
      </p>
      <h2>Por que o cartão e a casa de câmbio cobram mais</h2>
      <p>
        Quem vende moeda cobra uma margem (o spread) e há o IOF. Por isso o valor de uma compra no
        exterior ou de uma troca em espécie fica acima do que o conversor mostra.
      </p>
      <h2>Entre duas moedas estrangeiras</h2>
      <p>
        A conta passa pelo real: euro para dólar usa a PTAX do euro e a do dólar, a chamada
        cotação cruzada.
      </p>
    </PaginaDeFerramenta>
  );
}

const RENDA_FIXA = "calculadora-de-renda-fixa.html";
export const DADOS_DA_RENDA_FIXA = pagina(
  RENDA_FIXA,
  "Calculadora de renda fixa com IR",
  "Compare CDB, LCI/LCA, Tesouro Selic e poupança pelo mesmo prazo, com o CDI de hoje e o imposto " +
    "de renda pela tabela regressiva. Grátis e sem cadastro.",
);

export function PaginaDaRendaFixa() {
  const tabela = regrasDeImposto.renda_fixa;
  return (
    <PaginaDeFerramenta
      titulo="Calculadora de renda fixa com IR"
      subtitulo="CDB, LCI/LCA, Tesouro Selic e poupança pelo mesmo prazo, com o CDI de hoje e já sem o imposto. Grátis e sem cadastro."
      ilha="rendaFixa"
      codigo={codigo(RENDA_FIXA)}
      anuncio="cadastro"
      foraDaConta={[
        "o CDI de amanhã: a conta usa o de hoje durante todo o prazo",
        "a taxa de custódia da B3 no Tesouro e o IOF dos resgates em menos de 30 dias",
        "o risco de cada emissor e a garantia do FGC",
      ]}
      fonte={FONTE_DO_BC}
    >
      <h2>Como a conta é feita</h2>
      <p>
        O CDB e a LCI rendem um percentual do CDI, aplicado à taxa de cada dia útil. O Tesouro Selic
        rende a Selic de cada dia, que na prática anda junto com o CDI. A poupança rende só no
        aniversário, a cada 30 dias. Os dias corridos viram dias úteis pela proporção de 252 em 365.
      </p>
      <h2>A tabela regressiva do IR</h2>
      <ul>
        {tabela.map((faixa, i) => (
          <li key={i}>
            {faixa.ate_dias === null
              ? `acima de ${tabela[i - 1].ate_dias} dias`
              : `até ${faixa.ate_dias} dias`}
            : {formatarPorcentagem(faixa.aliquota)} sobre o rendimento
          </li>
        ))}
      </ul>
      <p>
        LCI, LCA e poupança são isentas para pessoa física. O imposto é sobre o rendimento, não
        sobre o valor aplicado.
      </p>
    </PaginaDeFerramenta>
  );
}

const JURO_REAL = "calculadora-de-juro-real.html";
export const DADOS_DO_JURO_REAL = pagina(
  JURO_REAL,
  "Calculadora de juro real",
  "Calcule o juro real (acima da inflação) pela fórmula de Fisher, com o IPCA de 12 meses, e " +
    "converta taxas ao mês e ao ano. Grátis e sem cadastro.",
);

export function PaginaDoJuroReal() {
  return (
    <PaginaDeFerramenta
      titulo="Calculadora de juro real"
      subtitulo="Quanto um investimento rende acima da inflação, e a taxa ao mês ou ao ano equivalente. Grátis e sem cadastro."
      ilha={[
        ["juroReal", "Juro real"],
        ["equivalente", "Taxa ao mês ou ao ano"],
      ]}
      codigo={codigo(JURO_REAL)}
      anuncio="ficha"
      foraDaConta={["imposto de renda e taxas", "a inflação de cada pessoa, que pode ser diferente do IPCA"]}
      fonte={FONTE_DO_BC}
    >
      <h2>Por que não é só subtrair</h2>
      <p>
        O juro real sai da divisão, não da subtração: (1 + taxa) ÷ (1 + inflação) − 1. Com 13,75% de
        rendimento e 5% de inflação, o ganho real é de 8,33%, não de 8,75%. A diferença cresce
        quanto maiores as taxas.
      </p>
      <h2>Taxa ao mês e ao ano</h2>
      <p>
        1% ao mês, composto, dá 12,68% ao ano, não 12%. Para comparar duas taxas, ponha as duas no
        mesmo prazo pela taxa equivalente.
      </p>
    </PaginaDeFerramenta>
  );
}

const INFLACAO = "calculadora-de-correcao-pela-inflacao.html";
export const DADOS_DA_INFLACAO = pagina(
  INFLACAO,
  "Correção pela inflação (IPCA)",
  "Corrija um valor pelo IPCA, mês a mês desde o Plano Real, com os números do Banco Central. " +
    "Grátis e sem cadastro.",
);

export function PaginaDaInflacao() {
  return (
    <PaginaDeFerramenta
      titulo="Correção pela inflação (IPCA)"
      subtitulo="Quanto um valor do passado vale hoje em poder de compra, corrigido pelo IPCA. Grátis e sem cadastro."
      ilha="inflacao"
      codigo={codigo(INFLACAO)}
      anuncio="cadastro"
      foraDaConta={[
        "outros índices, como o IGP-M (a FGV não permite o uso comercial)",
        "valores de antes de julho de 1994, em outra moeda",
      ]}
      fonte={FONTE_DO_BC}
    >
      <h2>Como a correção é feita</h2>
      <p>
        O valor é multiplicado pela inflação de cada mês do período, do mês inicial ao final, os
        dois incluídos, como na Calculadora do Cidadão do Banco Central. O IPCA de um mês sai por
        volta do dia 10 do mês seguinte.
      </p>
      <h2>Para que serve</h2>
      <p>
        Para comparar valores de épocas diferentes no mesmo poder de compra: um salário, um aluguel,
        o preço de compra de um imóvel ou o resultado de um investimento.
      </p>
    </PaginaDeFerramenta>
  );
}

// --- Vitrine -------------------------------------------------------------------------------
export const DADOS_DA_VITRINE = {
  caminho: "/ferramentas.html",
  titulo: "Ferramentas grátis",
  descricao:
    "Calculadoras grátis e sem cadastro do TickerLab: juros compostos, aportes e metas, custo das " +
    "taxas e mais, com cada conta explicada em português.",
  atual: "/ferramentas.html",
};

export function Vitrine() {
  return (
    <>
      <TopoDaPagina
        olho="Ferramentas"
        titulo="Ferramentas grátis"
        subtitulo="Calculadoras abertas para todos, sem cadastro, com cada conta explicada."
      />
      <section className="faixa secao" aria-label="Ferramentas">
        <div className="grade tres">
          {FERRAMENTAS_DO_SITE.map((f) => (
            <article className="cartao" key={f.arquivo}>
              <h2 className="ferramenta-nome">{f.nome}</h2>
              <p>{f.descricao}</p>
              <a className="seta" href={`/${f.arquivo}`}>
                Abrir a ferramenta
              </a>
            </article>
          ))}
        </div>
      </section>
      <section className="faixa secao">
        <AnuncioDaCasa destino="ficha" ferramenta="vitrine" />
      </section>
    </>
  );
}
