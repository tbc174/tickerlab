// Página inicial. Por enquanto só a prova de que o caminho Python → JSON → React funciona;
// a página de verdade (igual à atual) vem no PR 7 da série 2.
import { modulos } from "../conteudo";

export function Inicio() {
  return (
    <main>
      <h1>TickerLab</h1>
      <ul>
        {modulos.map((m) => (
          <li key={m.chave}>{m.nome}</li>
        ))}
      </ul>
    </main>
  );
}
