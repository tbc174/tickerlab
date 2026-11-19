// Peça única: a casca de toda tela do app (linha 903). No topo, a marca, a busca (Ctrl K), "O que mudou", o
// tema e a conta; ao lado, o menu de sete itens (MenuDoApp); embaixo, o aviso. No celular (até 760 px, só
// CSS) o menu vira abas fixas embaixo, ao alcance do polegar (ADR 0066). Antes de entrar (login, link
// compartilhado, API fora do ar) a casca vem sem menu, sem busca e com o caminho para a versão clássica.
import type { ReactNode } from "react";
import { Link } from "react-router";
import { paginasDoApp } from "../../conteudo";
import { AVISO } from "../../site/textos";
import { BuscaGlobal } from "../BuscaGlobal";
import { linkDoClassico } from "../classico";
import { ContaNoTopo } from "../conta";
import { useDialogo } from "../dialogo";
import { Logo } from "../Logo";
import { AbasDoCelular, MenuDoApp, TodasAsTelas } from "../MenuDoApp";
import { MenuDoTema } from "../MenuDoTema";
import { temTelaPronta } from "../rotas";

const O_QUE_MUDOU = paginasDoApp.find((p) => p.chave === "o_que_mudou" && temTelaPronta(p.chave));

function ComMenu({ children }: { children: ReactNode }) {
  const todasAsTelas = useDialogo();
  return (
    <>
      <div className="app-corpo faixa">
        <MenuDoApp todasAsTelas={todasAsTelas} />
        <main id="conteudo">{children}</main>
      </div>
      <AbasDoCelular todasAsTelas={todasAsTelas} />
      <TodasAsTelas dialogo={todasAsTelas} />
    </>
  );
}

export function Casca({ comMenu, children }: { comMenu: boolean; children: ReactNode }) {
  return (
    <>
      <a className="pular" href="#conteudo">
        Pular para o conteúdo
      </a>
      <header className="topo">
        <div className="faixa">
          <Logo />
          {comMenu ? <BuscaGlobal /> : null}
          {comMenu && O_QUE_MUDOU ? (
            <Link className="novidades-no-topo" to={`/${O_QUE_MUDOU.url}`}>
              {O_QUE_MUDOU.titulo}
            </Link>
          ) : null}
          <MenuDoTema />
          <ContaNoTopo />
          {comMenu ? null : (
            <a className="botao pequeno app-atual-no-topo" href={linkDoClassico()}>
              Versão clássica
            </a>
          )}
        </div>
      </header>
      {comMenu ? (
        <ComMenu>{children}</ComMenu>
      ) : (
        <div className="app-corpo sem-menu faixa">
          <main id="conteudo">{children}</main>
        </div>
      )}
      <footer className="rodape-do-app faixa">
        <p className="apagado">{AVISO}</p>
      </footer>
    </>
  );
}
