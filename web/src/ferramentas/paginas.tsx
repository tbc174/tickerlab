// As páginas das ferramentas grátis e a vitrine delas. Os números dos exemplos do texto saem das
// mesmas contas da calculadora (nada digitado à mão que possa ficar diferente).
import { TopoDaPagina } from "../site/Fundo";
import { AnuncioDaCasa } from "./AnuncioDaCasa";
import { altaParaRecuperar, custoDaTaxa } from "./contas/custos";
import { montante, taxaEquivalente } from "./contas/juros";
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
