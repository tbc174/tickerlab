// Uma tabela que chega pronta do Python (título, colunas e as células já escritas do jeito
// brasileiro): a página só mostra. Coluna em que toda célula é número vai à direita.
import type { ReactNode } from "react";

export interface TabelaDeTexto {
  chave: string;
  titulo: string;
  colunas: string[];
  linhas: string[][];
}

// uma célula que é número já escrito ("15.443,9", "−17,6%", "+2,8"): vai à direita
const NUMERO_ESCRITO = /^[-−+]?[\d.,]+%?$/;

/** O título vai num h3 (tabela dentro de uma seção) ou num h2 com âncora (a tabela é a seção);
 * `antes` entra entre o título e a tabela (um gráfico dos mesmos números, por exemplo). */
export function TabelaPronta({
  tabela,
  id,
  nivel = "h3",
  antes,
}: {
  tabela: TabelaDeTexto;
  id?: string;
  nivel?: "h2" | "h3";
  antes?: ReactNode;
}) {
  const Titulo = nivel;
  const numericas = tabela.colunas.map((_, i) =>
    tabela.linhas.every((linha) => NUMERO_ESCRITO.test(linha[i])),
  );
  return (
    <section>
      <Titulo id={id}>{tabela.titulo}</Titulo>
      {antes}
      <div className="tabela">
        <table>
          <thead>
            <tr>
              {tabela.colunas.map((coluna, i) => (
                <th key={coluna} scope="col" className={numericas[i] ? "v2-num" : undefined}>
                  {coluna}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tabela.linhas.map((linha) => (
              <tr key={`${tabela.chave}-${linha[0]}`}>
                {linha.map((celula, i) => (
                  <td key={tabela.colunas[i]} className={numericas[i] ? "v2-num" : undefined}>
                    {celula}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
