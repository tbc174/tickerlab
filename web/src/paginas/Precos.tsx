// Planos: a mesma tabela de limites que o app aplica (src/planos.py) e a cobrança. Era `precos()`.
// Os cartões e a tabela saem do mesmo planos.json: nenhum número é escrito à mão aqui. O site fala de
// duas colunas, Pessoa e Casa, e de uma faixa "Para conhecer, de graça", sem preço (plano do site para
// quem analisa, D1; ADR 0029, Emenda 1): o Pessoa mostra os limites do plano mais completo de hoje e o
// Casa é o mesmo, por assento, ainda em construção. `src/planos.py` e o Stripe não mudam.
import { planos } from "../conteudo";
import { AvisoDeAcesso, ListaDeCartoes } from "../site/comum";
import { TopoDaPagina } from "../site/Fundo";
import { EMAIL_DE_CONTATO, linkDoApp } from "../site/textos";

export const DADOS = {
  caminho: "/precos.html",
  titulo: "Planos",
  descricao:
    "Para conhecer, de graça; Pessoa e Casa para quem analisa empresas. Os limites são os do " +
    "app. Preço definido antes do lançamento; até lá, toda conta usa tudo.",
  atual: "/precos.html",
};

type Linha = Record<string, string>;
const LINHAS = planos.tabela as Linha[];

// as linhas que todo cartão mostra; o resto fica na tabela completa
const RESUMO = ["Simulações salvas", "Favoritos", "Ativos na carteira", "Relatórios em PDF"];

// o plano mais completo de hoje (o último da tabela) é o que o Pessoa mostra
const COMPLETO = planos.nomes[planos.nomes.length - 1];

/** O que só alguns planos têm (um "Sim" que não é de todos) entra no cartão de quem tem. */
function exclusivos(nome: string): string[] {
  return LINHAS.filter(
    (l) => l[nome] === "Sim" && planos.nomes.some((outro) => l[outro] !== "Sim"),
  ).map((l) => l.Recurso);
}

function selo(nome: string): string {
  if (planos.nomes_em_breve.includes(nome)) return "Assinatura em breve";
  if (planos.nomes_com_cobranca.includes(nome)) return "Modo de teste · sem cobrança real";
  return "Sem cartão";
}

function Gratuito() {
  const gratis = planos.nomes[0];
  return (
    <section className="faixa secao v2-depois-do-topo" aria-labelledby="titulo-gratis">
      <div className="v2-gratis">
        <div>
          <p className="olho">Para conhecer, de graça</p>
          <h2 id="titulo-gratis">O {gratis} não pede cartão</h2>
          <p className="subtitulo">
            Para conhecer o app e fazer as primeiras análises. Quando chegar a um limite, nada do
            que você fez é perdido.
          </p>
          <ul className="v2-gratis-limites">
            {RESUMO.map((recurso) => {
              const linha = LINHAS.find((l) => l.Recurso === recurso);
              return linha ? (
                <li key={recurso}>
                  {recurso}: <b>{linha[gratis]}</b>
                </li>
              ) : null;
            })}
          </ul>
        </div>
        <a className="botao secundario" href={linkDoApp()}>
          Começar grátis
        </a>
      </div>
    </section>
  );
}

function CartaoPessoa() {
  return (
    <article className="v2-plano v2-plano-destaque">
      <header>
        <h3>Pessoa</h3>
        <span className="v2-etiqueta v2-etiqueta-ambar">{selo(COMPLETO)}</span>
      </header>
      <p className="v2-plano-frase">
        Para quem analisa por conta própria: analistas, estudantes e pesquisadores. Hoje mostra os
        limites do nível {COMPLETO}, o mais completo.
      </p>
      <ul>
        {RESUMO.map((recurso) => {
          const linha = LINHAS.find((l) => l.Recurso === recurso);
          return linha ? (
            <li key={recurso}>
              {recurso}: <b>{linha[COMPLETO]}</b>
            </li>
          ) : null;
        })}
        {exclusivos(COMPLETO).map((recurso) => (
          <li key={recurso}>{recurso}</li>
        ))}
      </ul>
      <a className="botao primario" href={linkDoApp("planos")}>
        Ver no app
      </a>
    </article>
  );
}

function CartaoCasa() {
  return (
    <article className="v2-plano">
      <header>
        <h3>Casa</h3>
        <span className="v2-etiqueta">Ainda não está à venda</span>
      </header>
      <p className="v2-plano-frase">
        Para equipes e escritórios que analisam juntos. Cobrança por assento, ainda em construção.
      </p>
      <ul>
        <li>Tudo o que o plano Pessoa inclui, para cada pessoa da equipe</li>
        <li>Cobrança por assento: cada pessoa tem a própria conta</li>
        <li>Em construção: conte para a gente o que a sua equipe precisa</li>
      </ul>
      <a className="botao secundario" href={`mailto:${EMAIL_DE_CONTATO}`}>
        Fale com a gente
      </a>
    </article>
  );
}

/** "Sim" e "Não" viram ✓ e —, com a palavra para quem usa leitor de tela. */
function Celula({ valor }: { valor: string }) {
  if (valor === "Sim")
    return (
      <span className="v2-sim" role="img" aria-label="Sim">
        ✓
      </span>
    );
  if (valor === "Não")
    return (
      <span className="v2-nao" role="img" aria-label="Não">
        —
      </span>
    );
  return <>{valor}</>;
}

function TabelaDePlanos() {
  return (
    <div className="tabela">
      <table className="planos v2-comparativo">
        <thead>
          <tr>
            <th scope="col" rowSpan={2}>
              Recurso
            </th>
            <th scope="colgroup">Para conhecer, de graça</th>
            <th scope="colgroup" colSpan={planos.nomes.length - 1}>
              Pessoa
            </th>
          </tr>
          <tr>
            {planos.nomes.map((nome) => (
              <th key={nome} scope="col">
                {nome}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {LINHAS.map((linha) => (
            <tr key={linha.Recurso}>
              <th scope="row">{linha.Recurso}</th>
              {planos.nomes.map((nome) => (
                <td key={nome}>
                  <Celula valor={linha[nome]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Cobranca() {
  const emBreve = planos.nomes_em_breve;
  return (
    <p className="subtitulo">
      O Gratuito não pede cartão. A assinatura do Pessoa ({planos.nomes_com_cobranca.join(" e ")}{" "}
      na tabela) funciona em <strong>modo de teste</strong> do Stripe: nenhum dinheiro real é
      cobrado enquanto o projeto estiver em demonstração.{" "}
      {emBreve.length
        ? `O nível ${emBreve.join(" e o ")} já tem os limites definidos; a assinatura dele chega em breve.`
        : null}
    </p>
  );
}

// Diferencial da ADR 0054: muita plataforma anuncia "mensal" e cobra o ano inteiro parcelado.
function MensalDeVerdade() {
  return (
    <div className="escura v2-mensal">
      <section className="faixa secao" aria-labelledby="titulo-cobranca">
        <p className="olho">Cobrança</p>
        <h2 id="titulo-cobranca">Mensal de verdade</h2>
        <ul className="v2-promessas">
          <li>
            <b>Cancele quando quiser</b>
            <span>no próprio app, sem falar com ninguém</span>
          </li>
          <li>
            <b>Sem fidelidade</b>
            <span>um mês por vez, não o ano parcelado em 12</span>
          </li>
          <li>
            <b>Sem prender o limite do cartão</b>
            <span>e o acesso vai até o fim do mês já pago</span>
          </li>
        </ul>
        <p className="subtitulo">
          A assinatura cobra um mês por vez, e não o ano inteiro parcelado em 12 vezes. O
          cancelamento é feito em Minha conta → Planos e assinatura.
        </p>
        <Cobranca />
        <p className="subtitulo">
          Quando houver cobrança real, os valores e a renovação aparecem aqui e nos Termos de uso
          antes de qualquer mudança.
        </p>
      </section>
    </div>
  );
}

const OS_NUMEROS_QUE_CONTAM: [string, string][] = [
  [
    "Relatórios",
    "Contam os gerados nas últimas 24 horas. A prévia do PDF não conta; excluir um relatório " +
      "da biblioteca não devolve o limite.",
  ],
  ["Simulações e favoritos", "O que fica guardado na sua conta."],
  ["Ativos na carteira", "Quantos ativos uma simulação de carteira aceita."],
];

export function Precos() {
  return (
    <>
      <TopoDaPagina
        olho="Planos"
        titulo="Comece de graça; escolha o plano quando precisar"
        subtitulo={
          "Os limites abaixo são os mesmos que o app aplica. Ao chegar a um limite, nada do " +
          "que você já fez é perdido."
        }
      >
        <AvisoDeAcesso />
      </TopoDaPagina>

      <Gratuito />

      <section className="faixa secao" aria-labelledby="titulo-pessoa-casa">
        <p className="olho">Pessoa e Casa</p>
        <h2 id="titulo-pessoa-casa">Um plano para você, um para a sua equipe</h2>
        <p className="subtitulo">
          O preço dos planos é definido antes do lançamento. Até lá, toda conta usa os limites do
          Pro, de graça: você conhece o app inteiro sem pagar nada.
        </p>
        <div className="v2-planos">
          <CartaoPessoa />
          <CartaoCasa />
        </div>
      </section>

      <MensalDeVerdade />

      <section className="faixa secao" aria-labelledby="titulo-comparar">
        <p className="olho">Lado a lado</p>
        <h2 id="titulo-comparar">Tudo o que cada plano inclui</h2>
        <TabelaDePlanos />
        <p className="subtitulo">
          O Casa tem os mesmos limites do Pessoa, por assento, e está em construção.
        </p>
      </section>

      <section className="faixa secao" aria-labelledby="titulo-contam">
        <p className="olho">Detalhes</p>
        <h2 id="titulo-contam">Os números que contam</h2>
        <div className="grade tres">
          <ListaDeCartoes itens={OS_NUMEROS_QUE_CONTAM} />
        </div>
      </section>

      <div className="escura v2-final-fundo">
        <div className="v2-horizonte v2-horizonte-alto" aria-hidden="true" />
        <section className="faixa secao final" aria-labelledby="titulo-final">
          <h2 id="titulo-final">Comece pelo Gratuito</h2>
          <p className="subtitulo">
            Sem cartão. Quando chegar a um limite, nada do que você fez é perdido.
          </p>
          <a className="botao primario" href={linkDoApp()}>
            Abrir o app
          </a>
        </section>
      </div>
    </>
  );
}
