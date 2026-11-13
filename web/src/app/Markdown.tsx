// O texto do chat em Markdown, desenhado só com elementos do React (nunca HTML cru): parágrafos, títulos,
// listas, tabelas, negrito, itálico e código. O texto vem do modelo, que leu dados de terceiros: nada dele
// vira HTML, link ou script; o que este leitor não conhece aparece como texto.
import type { ReactNode } from "react";

export type Bloco =
  | { tipo: "titulo"; nivel: 2 | 3 | 4; texto: string }
  | { tipo: "paragrafo"; texto: string }
  | { tipo: "lista"; ordenada: boolean; itens: string[] }
  | { tipo: "tabela"; cabecalho: string[]; linhas: string[][] };

const TITULO = /^(#{1,6})\s+(.*)$/;
const ITEM = /^\s*(?:[-*+]|(\d+)[.)])\s+(.*)$/;
const SEPARADOR_DA_TABELA = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const LINHA_DA_TABELA = /^\s*\|.*\|\s*$/;
const REGUA = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;
// negrito, itálico e código, nesta ordem de procura
const MARCA_EM_LINHA = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/;

function celulas(linha: string): string[] {
  return linha
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

function nivelDoTitulo(cerquilhas: number): 2 | 3 | 4 {
  // o h1 é da tela; a resposta começa no h2
  return cerquilhas <= 2 ? 2 : cerquilhas === 3 ? 3 : 4;
}

/** O texto em blocos, linha a linha. */
export function blocosDoMarkdown(texto: string): Bloco[] {
  const linhas = texto.replace(/\r\n?/g, "\n").split("\n");
  const blocos: Bloco[] = [];
  let paragrafo: string[] = [];
  const fecharParagrafo = () => {
    if (paragrafo.length > 0) blocos.push({ tipo: "paragrafo", texto: paragrafo.join(" ") });
    paragrafo = [];
  };
  let i = 0;
  while (i < linhas.length) {
    const linha = linhas[i];
    const titulo = TITULO.exec(linha);
    if (!linha.trim() || REGUA.test(linha)) {
      fecharParagrafo();
      i += 1;
    } else if (titulo) {
      fecharParagrafo();
      blocos.push({ tipo: "titulo", nivel: nivelDoTitulo(titulo[1].length), texto: titulo[2].trim() });
      i += 1;
    } else if (LINHA_DA_TABELA.test(linha) && SEPARADOR_DA_TABELA.test(linhas[i + 1] ?? "")) {
      fecharParagrafo();
      const cabecalho = celulas(linha);
      const corpo: string[][] = [];
      i += 2;
      while (i < linhas.length && LINHA_DA_TABELA.test(linhas[i])) {
        corpo.push(celulas(linhas[i]));
        i += 1;
      }
      blocos.push({ tipo: "tabela", cabecalho, linhas: corpo });
    } else if (ITEM.test(linha)) {
      fecharParagrafo();
      const ordenada = ITEM.exec(linha)?.[1] !== undefined;
      const itens: string[] = [];
      while (i < linhas.length && ITEM.test(linhas[i])) {
        itens.push(ITEM.exec(linhas[i])?.[2] ?? "");
        i += 1;
      }
      blocos.push({ tipo: "lista", ordenada, itens });
    } else {
      paragrafo.push(linha.trim());
      i += 1;
    }
  }
  fecharParagrafo();
  return blocos;
}

/** Negrito, itálico e código dentro de uma linha; o resto é texto. */
export function EmLinha({ texto }: { texto: string }) {
  const partes = texto.split(MARCA_EM_LINHA).filter((p) => p !== "");
  return (
    <>
      {partes.map((parte, n) => {
        const chave = `${n}-${parte}`;
        if (parte.startsWith("**") && parte.endsWith("**") && parte.length > 4)
          return <strong key={chave}>{parte.slice(2, -2)}</strong>;
        if (parte.startsWith("`") && parte.endsWith("`") && parte.length > 2)
          return <code key={chave}>{parte.slice(1, -1)}</code>;
        if (/^([*_]).+\1$/.test(parte) && parte.length > 2) return <em key={chave}>{parte.slice(1, -1)}</em>;
        return <span key={chave}>{parte}</span>;
      })}
    </>
  );
}

function Tabela({ cabecalho, linhas }: { cabecalho: string[]; linhas: string[][] }) {
  return (
    // a tabela larga rola de lado pelo teclado
    <div className="tabela-rolavel" tabIndex={0}>
      <table className="tabela-do-app">
        <thead>
          <tr>
            {cabecalho.map((c, n) => (
              <th key={`${n}-${c}`} scope="col">
                <EmLinha texto={c} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha, n) => (
            // a linha da tabela não tem chave própria
            <tr key={n}>
              {cabecalho.map((_, coluna) => (
                // a célula é a posição na linha
                <td key={coluna}>
                  <EmLinha texto={linha[coluna] ?? ""} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Bloco({ bloco }: { bloco: Bloco }): ReactNode {
  switch (bloco.tipo) {
    case "titulo": {
      const Titulo = `h${bloco.nivel}` as const;
      return (
        <Titulo>
          <EmLinha texto={bloco.texto} />
        </Titulo>
      );
    }
    case "lista": {
      const Lista = bloco.ordenada ? "ol" : "ul";
      return (
        <Lista>
          {bloco.itens.map((item, n) => (
            // itens iguais podem se repetir
            <li key={n}>
              <EmLinha texto={item} />
            </li>
          ))}
        </Lista>
      );
    }
    case "tabela":
      return <Tabela cabecalho={bloco.cabecalho} linhas={bloco.linhas} />;
    default:
      return (
        <p>
          <EmLinha texto={bloco.texto} />
        </p>
      );
  }
}

export function Markdown({ blocos }: { blocos: Bloco[] }) {
  return (
    <>
      {blocos.map((bloco, n) => (
        // os blocos só crescem no fim enquanto a resposta chega
        <Bloco key={n} bloco={bloco} />
      ))}
    </>
  );
}
