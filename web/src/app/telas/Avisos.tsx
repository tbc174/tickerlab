// As telas de aviso do app novo: API desligada, fora do ar, carregando, endereço que não existe.
import { Link } from "react-router";
import { linkDoApp } from "../../site/textos";

export function EmPreparacao() {
  return (
    <section className="aviso-do-app">
      <h1>A versão nova do app está em preparação</h1>
      <p>
        As telas novas do TickerLab ainda não foram abertas. Enquanto isso, tudo continua no app de
        sempre, com os mesmos números.
      </p>
      <a className="botao primario" href={linkDoApp()}>
        Ir para o app atual
      </a>
    </section>
  );
}

export function ForaDoAr() {
  return (
    <section className="aviso-do-app">
      <h1>Não consegui falar com o TickerLab agora</h1>
      <p>Tente de novo em instantes. Se continuar, use o app de sempre.</p>
      <a className="botao primario" href={linkDoApp()}>
        Ir para o app atual
      </a>
    </section>
  );
}

export function LoginNaoConfigurado() {
  return (
    <section className="aviso-do-app">
      <h1>O login da versão nova ainda não foi ligado</h1>
      <p>Enquanto isso, use o app de sempre, com os mesmos números.</p>
      <a className="botao primario" href={linkDoApp()}>
        Ir para o app atual
      </a>
    </section>
  );
}

export function Carregando() {
  return (
    <p className="apagado" role="status">
      Carregando…
    </p>
  );
}

export function NaoEncontrada() {
  return (
    <section className="aviso-do-app">
      <h1>Página não encontrada</h1>
      <p>Este endereço não existe na versão nova do app.</p>
      <Link className="botao" to="/">
        Ver as telas novas
      </Link>
    </section>
  );
}
