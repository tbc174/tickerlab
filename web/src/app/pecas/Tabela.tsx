// Peça única: a tabela do app. Legenda (o leitor de tela anuncia), cabeçalho de coluna com escopo, número
// alinhado à direita em fonte de largura fixa, rolagem lateral no celular sem a página rolar junto e, sem
// linha nenhuma, a frase do vazio no lugar de uma tabela só com cabeçalho.
import type { ReactNode } from "react";
import { Vazio } from "./Vazio";

export interface Coluna<Linha> {
  chave: string;
  titulo: string;
  celula(linha: Linha): ReactNode;
  /** Coluna de número: alinha à direita, com algarismos de mesma largura. */
  numero?: boolean;
}

interface Propriedades<Linha> {
  /** O que a tabela mostra; vira a legenda (`caption`). */
  legenda: string;
  colunas: Coluna<Linha>[];
  linhas: Linha[];
  chaveDaLinha(linha: Linha): string;
  /** A frase quando não há linha (ex.: "Nenhuma empresa com esses filtros."). */
  vazio?: string;
  /** A legenda fica só para o leitor de tela (quando um título logo acima já diz o mesmo). */
  legendaEscondida?: boolean;
  /** A fonte e a data do dado, embaixo da tabela (peça `Fonte`). */
  rodape?: ReactNode;
}

export function Tabela<Linha>(propriedades: Propriedades<Linha>) {
  const { legenda, colunas, linhas, chaveDaLinha, vazio, legendaEscondida, rodape } = propriedades;
  if (linhas.length === 0 && vazio) return <Vazio frase={vazio} />;
  return (
    <div className="tabela-da-peca">
      {/* com foco pelo teclado: quem não usa mouse também rola a tabela larga */}
      <div className="tabela-rolavel" role="region" aria-label={legenda} tabIndex={0}>
        <table className="tabela-do-app">
          <caption className={legendaEscondida ? "so-para-leitor" : undefined}>{legenda}</caption>
          <thead>
            <tr>
              {colunas.map((coluna) => (
                <th key={coluna.chave} scope="col" className={coluna.numero ? "numero" : undefined}>
                  {coluna.titulo}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {linhas.map((linha) => (
              <tr key={chaveDaLinha(linha)}>
                {colunas.map((coluna) => (
                  <td key={coluna.chave} className={coluna.numero ? "numero" : undefined}>
                    {coluna.celula(linha)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rodape}
    </div>
  );
}
