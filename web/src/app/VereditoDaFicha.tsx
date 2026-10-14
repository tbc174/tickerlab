// O veredito e as cinco checagens da ficha "Foi sorte?" (src/ficha.py), iguais no backtest e no link
// compartilhado. Sem verde nem vermelho (a marca guarda os dois para alta e queda): o símbolo e o texto
// dizem o resultado, como os ícones do Streamlit.

const SIMBOLO_DO_VEREDITO: Record<string, string> = { passou: "✓", "não passou": "✕", inconclusivo: "?" };
const SIMBOLO_DA_CHECAGEM: Record<string, string> = {
  passou: "✓",
  "não passou": "✕",
  "não se aplica": "–",
  "não deu para medir": "?",
};

interface Checagem {
  pergunta: string;
  situacao: string;
  explicacao: string;
}

interface Propriedades {
  resultado?: string; // "passou", "não passou" ou "inconclusivo" (sem ele, sem símbolo no título)
  titulo: string;
  texto: string;
  checagens: Checagem[];
  nivel?: 2 | 3; // o título do veredito: h2 na página do link, h3 embaixo do backtest
}

export function VereditoDaFicha({ resultado, titulo, texto, checagens, nivel = 2 }: Propriedades) {
  const Titulo = nivel === 3 ? "h3" : "h2";
  return (
    <>
      <section className="cartao-do-veredito" aria-label="Veredito">
        <Titulo>
          {resultado ? <span aria-hidden="true">{SIMBOLO_DO_VEREDITO[resultado] ?? "?"} </span> : null}
          {titulo}
        </Titulo>
        <p>{texto}</p>
      </section>
      <ul className="checagens">
        {checagens.map((c) => (
          <li key={c.pergunta}>
            <span className="simbolo-da-checagem" aria-hidden="true">
              {SIMBOLO_DA_CHECAGEM[c.situacao] ?? "?"}{" "}
            </span>
            <strong>{c.pergunta}</strong> <span className="apagado">({c.situacao})</span>
            <p>{c.explicacao}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
