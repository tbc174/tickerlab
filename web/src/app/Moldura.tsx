// A moldura de toda tela do app novo: topo com a marca, as telas e o tema; rodapé com o aviso.
// No computador, as telas ficam no menu por áreas, ao lado (MenuPorAreas); no celular (até 760 px, só
// CSS), numa barra de abas fixa embaixo, ao alcance do polegar (ADR 0066).
import { type ReactNode, useRef } from "react";
import { NavLink } from "react-router";
import { AVISO, linkDoApp } from "../site/textos";
import { ContaNoTopo } from "./conta";
import { Logo } from "./Logo";
import { MenuDoTema } from "./MenuDoTema";
import { MenuPorAreas } from "./MenuPorAreas";
import { TELAS_DO_APP } from "./rotas";

// as telas com aba própria no celular, com o nome curto; as outras ficam em "Mais"
const ABAS: Record<string, string> = {
  visao_geral: "Visão geral",
  backtest: "Backtest",
  comparar: "Comparar",
};
// na ordem de ABAS (não na do menu); tela que sair do app some da aba sem quebrar
const NAS_ABAS = Object.keys(ABAS).flatMap((chave) => TELAS_DO_APP.filter((p) => p.chave === chave));
const EM_MAIS = TELAS_DO_APP.filter((p) => !(p.chave in ABAS));

function AbasDoCelular() {
  const mais = useRef<HTMLDetailsElement>(null);
  // escolher uma tela fecha a lista (a moldura continua na página; sem isso ela ficaria aberta)
  const fecharMais = () => {
    if (mais.current) mais.current.open = false;
  };
  return (
    <nav className="app-abas" aria-label="Telas, atalhos">
      <NavLink to="/" end>
        Início
      </NavLink>
      {NAS_ABAS.map((pagina) => (
        <NavLink key={pagina.chave} to={`/${pagina.url}`}>
          {ABAS[pagina.chave]}
        </NavLink>
      ))}
      <details ref={mais} className="app-abas-mais">
        <summary>Mais</summary>
        <div className="app-abas-lista">
          {EM_MAIS.map((pagina) => (
            <NavLink key={pagina.chave} to={`/${pagina.url}`} onClick={fecharMais}>
              {pagina.titulo}
            </NavLink>
          ))}
        </div>
      </details>
    </nav>
  );
}

export function Moldura({ comMenu, children }: { comMenu: boolean; children: ReactNode }) {
  return (
    <>
      <a className="pular" href="#conteudo">
        Pular para o conteúdo
      </a>
      <header className="topo">
        <div className="faixa">
          <Logo />
          <span className="selo-novo">Versão nova</span>
          <MenuDoTema />
          <ContaNoTopo />
          <a className="botao pequeno" href={linkDoApp()}>
            App atual
          </a>
        </div>
      </header>
      <div className={comMenu ? "app-corpo faixa" : "app-corpo sem-menu faixa"}>
        {comMenu ? <MenuPorAreas /> : null}
        <main id="conteudo">{children}</main>
      </div>
      {comMenu ? <AbasDoCelular /> : null}
      <footer className="rodape-do-app faixa">
        <p className="apagado">{AVISO}</p>
      </footer>
    </>
  );
}
