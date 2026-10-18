// A moldura de toda tela do app novo: topo com a marca, a conta e o tema; rodapé com o aviso.
// As telas ficam no menu por áreas (MenuPorAreas, ADR 0096): ao lado no computador; no celular (até 760 px,
// só CSS), em 5 abas fixas embaixo, ao alcance do polegar (ADR 0066).
import type { ReactNode } from "react";
import { AVISO, linkDoApp } from "../site/textos";
import { ContaNoTopo } from "./conta";
import { Logo } from "./Logo";
import { MenuDoTema } from "./MenuDoTema";
import { AbasDoCelular, MenuPorAreas } from "./MenuPorAreas";

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
