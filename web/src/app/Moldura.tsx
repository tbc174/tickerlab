// A moldura de toda tela do app novo: topo com a marca, as telas e o tema; rodapé com o aviso.
import type { ReactNode } from "react";
import { NavLink } from "react-router";
import { AVISO, linkDoApp } from "../site/textos";
import { ContaNoTopo } from "./conta";
import { Logo } from "./Logo";
import { MenuDoTema } from "./MenuDoTema";
import { TELAS_DO_APP } from "./rotas";

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
        {comMenu ? (
          <nav className="app-menu" aria-label="Telas">
            {TELAS_DO_APP.map((pagina) => (
              <NavLink key={pagina.chave} to={`/${pagina.url}`}>
                {pagina.titulo}
              </NavLink>
            ))}
          </nav>
        ) : null}
        <main id="conteudo">{children}</main>
      </div>
      <footer className="rodape-do-app faixa">
        <p className="apagado">{AVISO}</p>
      </footer>
    </>
  );
}
