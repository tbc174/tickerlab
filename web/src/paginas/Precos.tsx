// Planos: a mesma tabela de limites que o app aplica (src/planos.py) e a cobrança. Era `precos()`.
import { planos } from "../conteudo";
import { AvisoDeAcesso } from "../site/comum";
import { linkDoApp } from "../site/textos";

export const DADOS = {
  caminho: "/precos.html",
  titulo: "Planos",
  descricao:
    "Gratuito, Plus e Pro: o que cada plano do TickerLab inclui, com os mesmos limites do " +
    "app. Assinatura mensal de verdade, sem fidelidade. Cobrança em modo de teste.",
  atual: "/precos.html",
};

function TabelaDePlanos() {
  const linhas = planos.tabela as Record<string, string>[];
  return (
    <div className="tabela">
      <table className="planos">
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
          {linhas.map((linha) => (
            <tr key={linha.Recurso}>
              <th scope="row">{linha.Recurso}</th>
              {planos.nomes.map((nome) => (
                <td key={nome}>{linha[nome]}</td>
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
    <p>
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
    <p>
      <strong>Mensal de verdade:</strong> cancele quando quiser, sem fidelidade e sem prender o
      limite do seu cartão. A assinatura cobra um mês por vez, e não o ano inteiro parcelado em
      12 vezes. O cancelamento é feito no próprio app (Minha conta → Planos e assinatura), sem
      precisar falar com ninguém, e o acesso continua até o fim do mês já pago.
    </p>
  );
}

export function Precos() {
  return (
    <section className="faixa secao estreita">
      <p className="olho">Planos</p>
      <h1>Escolha o nível de pesquisa que faz sentido para você</h1>
      <p className="subtitulo">
        Os limites abaixo são os mesmos que o app aplica. Ao chegar a um limite, nada do que
        você já fez é perdido.
      </p>
      <TabelaDePlanos />
      <h2>Cobrança</h2>
      <MensalDeVerdade />
      <Cobranca />
      <p>
        Quando houver cobrança real, os valores e a renovação aparecem aqui e nos Termos de uso
        antes de qualquer mudança.
      </p>
      <h2>Os números que contam</h2>
      <ul>
        <li>
          <strong>Relatórios:</strong> contam os gerados nas últimas 24 horas. A prévia do PDF
          não conta; excluir um relatório da biblioteca não devolve o limite.
        </li>
        <li>
          <strong>Simulações e favoritos:</strong> o que fica guardado na sua conta.
        </li>
        <li>
          <strong>Ativos na carteira:</strong> quantos ativos uma simulação de carteira aceita.
        </li>
      </ul>
      <AvisoDeAcesso />
      <p>
        <a className="botao primario" href={linkDoApp("planos")}>
          Ver no app
        </a>
      </p>
    </section>
  );
}
