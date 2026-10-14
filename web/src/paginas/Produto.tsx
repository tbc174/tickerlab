// Produto: os seis módulos, o que já está no app e o que vem por aí. Era `produto()`.
import { Fragment } from "react";
import { ChamadaFinal, MODULOS_DO_PRODUTO, SecaoDoModulo } from "../site/comum";
import { TopoDaPagina } from "../site/Fundo";

export const DADOS = {
  caminho: "/produto.html",
  titulo: "Produto",
  descricao:
    "Research, Carteira, Estratégias, Relatórios, Mercado e Ferramentas: o que o TickerLab " +
    "já faz e o que está em construção.",
  atual: "/produto.html",
};

export function Produto() {
  return (
    <>
      <TopoDaPagina
        olho="Produto"
        titulo="Tudo o que o TickerLab faz, e o que vem por aí"
        subtitulo={
          "O selo mostra o que já está no app e o que ainda está em construção. " +
          "O que está em breve não tem data marcada."
        }
      >
        <p className="atalhos">
          {MODULOS_DO_PRODUTO.map((m, i) => (
            <Fragment key={m.chave}>
              {i > 0 ? " " : null}
              <a className="botao secundario pequeno" href={`#${m.chave}`}>
                {m.nome}
              </a>
            </Fragment>
          ))}
        </p>
      </TopoDaPagina>
      {MODULOS_DO_PRODUTO.map((m) => (
        <SecaoDoModulo key={m.chave} modulo={m} />
      ))}
      <ChamadaFinal />
    </>
  );
}
