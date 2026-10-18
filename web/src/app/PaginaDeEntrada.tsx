// A página de quem ainda não entrou: sem a moldura do app (o menu só leva a telas que pedem login, e o
// rodapé falava de fonte de preço a quem ainda nem viu um número). A marca e o que o TickerLab é de um
// lado; o cartão do outro, com o login, o "Entrando…" ou o aceite dos termos. No celular, uma coluna.
import type { ReactNode } from "react";
import { conteudoDoApp } from "../conteudo";
import { ASSINATURA } from "../site/textos";
import { FundoDoApp } from "./FundoDoApp";
import { Logo } from "./Logo";

export function PaginaDeEntrada({ children }: { children: ReactNode }) {
  return (
    <FundoDoApp telaCheia>
      <div className="entrada faixa">
        <header className="entrada-topo">
          <Logo />
        </header>
        <div className="entrada-corpo">
          <aside className="entrada-marca" aria-label="O que é o TickerLab">
            <p className="entrada-assinatura">{ASSINATURA}</p>
            <ul className="entrada-pontos">
              {conteudoDoApp.entrada.pontos.map((ponto) => (
                <li key={ponto}>{ponto}</li>
              ))}
            </ul>
          </aside>
          <main id="conteudo" className="entrada-cartao">
            {children}
          </main>
        </div>
      </div>
    </FundoDoApp>
  );
}
