// Planos: a mesma tabela de limites que o app aplica (src/planos.py) e a cobrança. Era `precos()`.
// Os cartões e a tabela saem do mesmo planos.json: nenhum número é escrito à mão aqui.
import { planos } from "../conteudo";
import { AvisoDeAcesso, ListaDeCartoes } from "../site/comum";
import { TopoDaPagina } from "../site/Fundo";
import { linkDoApp } from "../site/textos";

export const DADOS = {
  caminho: "/precos.html",
  titulo: "Planos",
  descricao:
    "Gratuito, Plus e Pro: o que cada plano do TickerLab inclui, com os mesmos limites do " +
    "app. Assinatura mensal, sem fidelidade. Cobrança em modo de teste.",
  atual: "/precos.html",
};

type Linha = Record<string, string>;
const LINHAS = planos.tabela as Linha[];

// as linhas que todo cartão mostra; o resto fica na tabela completa
const RESUMO = ["Simulações salvas", "Favoritos", "Ativos na carteira", "Relatórios em PDF"];

const FRASES: Record<string, string> = {
  Gratuito: "Para conhecer o app e fazer as primeiras análises.",
  Plus: "Para quem estuda com frequência e guarda o que faz.",
  Pro: "Para quem quer tudo, inclusive aprendizado de máquina.",
};

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

function Botao({ nome }: { nome: string }) {
  if (planos.nomes_em_breve.includes(nome))
    return (
      <span className="botao secundario v2-desligado" aria-disabled="true">
        Em breve
      </span>
    );
  if (planos.nomes_com_cobranca.includes(nome))
    return (
      <a className="botao primario" href={linkDoApp("planos")}>
        Ver no app
      </a>
    );
  return (
    <a className="botao secundario" href={linkDoApp()}>
      Começar grátis
    </a>
  );
}

function CartaoDoPlano({ nome, destaque }: { nome: string; destaque: boolean }) {
  return (
    <article className={destaque ? "v2-plano v2-plano-destaque" : "v2-plano"}>
      <header>
        <h3>{nome}</h3>
        <span className={destaque ? "v2-etiqueta v2-etiqueta-ambar" : "v2-etiqueta"}>
          {selo(nome)}
        </span>
      </header>
      {FRASES[nome] ? <p className="v2-plano-frase">{FRASES[nome]}</p> : null}
      <ul>
        {RESUMO.map((recurso) => {
          const linha = LINHAS.find((l) => l.Recurso === recurso);
          return linha ? (
            <li key={recurso}>
              {recurso}: <b>{linha[nome]}</b>
            </li>
          ) : null;
        })}
        {exclusivos(nome).map((recurso) => (
          <li key={recurso}>{recurso}</li>
        ))}
      </ul>
      <Botao nome={nome} />
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
            <th scope="col">Recurso</th>
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
      O plano Gratuito não pede cartão. A assinatura do {planos.nomes_com_cobranca.join(" e do ")}{" "}
      funciona em <strong>modo de teste</strong> do Stripe: nenhum dinheiro real é cobrado
      enquanto o projeto estiver em demonstração.{" "}
      {emBreve.length
        ? `O ${emBreve.join(" e o ")} já tem os limites definidos; a assinatura dele chega em breve.`
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
        titulo="Escolha o nível de pesquisa que faz sentido para você"
        subtitulo={
          "Os limites abaixo são os mesmos que o app aplica. Ao chegar a um limite, nada do " +
          "que você já fez é perdido."
        }
      >
        <AvisoDeAcesso />
      </TopoDaPagina>

      <section className="faixa secao v2-depois-do-topo" aria-label="Os planos">
        <div className="v2-planos">
          {planos.nomes.map((nome, i) => (
            <CartaoDoPlano key={nome} nome={nome} destaque={i === planos.nomes.length - 1} />
          ))}
        </div>
      </section>

      <MensalDeVerdade />

      <section className="faixa secao" aria-labelledby="titulo-comparar">
        <p className="olho">Lado a lado</p>
        <h2 id="titulo-comparar">Tudo o que cada plano inclui</h2>
        <TabelaDePlanos />
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
