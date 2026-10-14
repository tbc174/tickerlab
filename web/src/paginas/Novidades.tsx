// Novidades: o que entrou e o que foi corrigido em cada atualização. O texto vem de src/novidades.py
// (o mesmo da nota da versão no GitHub); a mais nova fica no topo.
import { novidades } from "../conteudo";
import { PaginaDeLeitura } from "../site/Leitura";

export const DADOS = {
  caminho: "/novidades.html",
  titulo: "Novidades",
  descricao:
    "O que entrou e o que foi corrigido no TickerLab em cada atualização: telas novas, " +
    "relatórios, dados e correções.",
  atual: "/novidades.html",
};

const MESES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

/** "2026-10-13" → "13 de outubro de 2026" (sem fuso: a data é do calendário, não um instante). */
export function dataPorExtenso(iso: string): string {
  const [ano, mes, dia] = iso.split("-").map(Number);
  return `${dia} de ${MESES[mes - 1]} de ${ano}`;
}

export function Novidades() {
  return (
    <PaginaDeLeitura
      olho="Atualizações"
      titulo="Novidades"
      subtitulo="O que entrou e o que foi corrigido em cada atualização do TickerLab."
      sumario={novidades.map((a) => ({ id: a.data, texto: dataPorExtenso(a.data) }))}
    >
      {novidades.map((a) => (
        <article key={a.data} id={a.data}>
          <h2>
            <time dateTime={a.data}>{dataPorExtenso(a.data)}</time>: {a.titulo}
          </h2>
          <p>{a.resumo}</p>
          <h3>Novidades</h3>
          <ul>
            {a.novidades.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          {a.correcoes.length > 0 && (
            <>
              <h3>Correções</h3>
              <ul>
                {a.correcoes.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </>
          )}
        </article>
      ))}
      <p className="apagado">
        Nada aqui é recomendação de investimento. Os números do TickerLab descrevem o passado.
      </p>
    </PaginaDeLeitura>
  );
}
