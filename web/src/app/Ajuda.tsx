// O "?" de um número: o texto do glossário (O que é, Exemplo, Cuidado), aberto com um clique ou com o
// teclado. Texto puro vindo do Python, sem Markdown e sem HTML pronto.
import { conteudoDoApp } from "../conteudo";

export function Ajuda({ termo, rotulo }: { termo: string; rotulo: string }) {
  const partes = conteudoDoApp.glossario[termo];
  if (!partes) return null;
  return (
    <details className="ajuda">
      <summary aria-label={`O que significa ${rotulo}`}>?</summary>
      <div className="ajuda-texto">
        {partes.map((parte) => (
          <p key={parte.texto}>
            {parte.rotulo ? <strong>{parte.rotulo}</strong> : null}
            {parte.rotulo ? ": " : null}
            {parte.texto}
          </p>
        ))}
      </div>
    </details>
  );
}
