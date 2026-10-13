// Peças que aparecem em mais de uma página do site.
import type { Modulo } from "../conteudo";
import { modulos } from "../conteudo";
import { TICKER_DO_EXEMPLO, linkDoApp } from "./textos";

// os seis módulos da página Produto; o Aprender tem página própria
export const MODULOS_DO_PRODUTO: Modulo[] = modulos.slice(0, 6);

export function disponiveis(modulo: Modulo): number {
  return modulo.funcionalidades.filter((f) => f.disponivel).length;
}

/** "4 disponíveis · 2 em breve" (no singular quando é uma só). */
export function contagem(modulo: Modulo): string {
  const prontas = disponiveis(modulo);
  const emBreve = modulo.funcionalidades.length - prontas;
  const partes: string[] = [];
  if (prontas) partes.push(`${prontas} ${prontas === 1 ? "disponível" : "disponíveis"}`);
  if (emBreve) partes.push(`${emBreve} em breve`);
  return partes.join(" · ");
}

export function ChamadaFinal() {
  return (
    <div className="escura">
      <section className="faixa secao final" aria-labelledby="titulo-final">
        <h2 id="titulo-final">Comece pela sua primeira análise</h2>
        <p className="subtitulo">
          O tutorial do app guia você em 2 minutos, com dados de verdade.
        </p>
        <a
          className="botao primario"
          href={linkDoApp("visao-geral", { ticker: TICKER_DO_EXEMPLO })}
        >
          Experimentar com PETR4
        </a>
      </section>
    </div>
  );
}
