// O recorte de um cartão de empresa fechada por estado e por setor (linha 925, 2º PR): as barras vêm prontas
// de base/vitrine.py; a tela só desenha, recolhido num <details>, com o número de cada barra no texto.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { FatoDaBase } from "../../src/conteudo";
import { Fato } from "../../src/site/Cruzamentos";

const semTags = (texto: string) => texto.replace(/<[^>]+>/g, "");

const FATO: FatoDaBase = {
  chave: "saiu_do_simples",
  numero: "20,0%",
  texto: "empresas fechadas saíram do Simples Nacional.",
  fonte: "Receita Federal",
  tabelas: ["simples"],
  data: "2026-11-14",
  como_foi_calculado: "A conta do cartão.",
};

const RECORTE = {
  por_uf: {
    barras: [
      { rotulo: "SP", parte: "1.000", todo: "5.000", porcento: "20,0%", largura: 100 },
      { rotulo: "MG", parte: "500", todo: "3.000", porcento: "16,7%", largura: 50 },
    ],
    escondidas: ["AC", "Sem informação no cadastro"],
  },
  por_setor: {
    barras: [{ rotulo: "Indústrias de transformação", parte: "1.300", todo: "6.000", porcento: "21,7%", largura: 100 }],
    escondidas: [],
  },
  como_foi_calculado: "Cada empresa do cartão entra no estado e no setor da matriz.",
};

describe("o recorte do cartão por estado e por setor", () => {
  it("sem recorte, o cartão fica como era", () => {
    const html = renderToStaticMarkup(<Fato fato={FATO} />);
    expect(html).not.toContain("v2-recorte");
  });

  it("com recorte, cada barra traz o rótulo e a conta no texto, e as escondidas só pelo nome", () => {
    const html = renderToStaticMarkup(<Fato fato={{ ...FATO, recorte: RECORTE }} />);
    expect(html).toContain("<summary>Por estado e por setor</summary>");
    const texto = semTags(html);
    expect(texto).toContain("SP1.000 de 5.000 (20,0%)");
    expect(texto).toContain("MG500 de 3.000 (16,7%)");
    expect(texto).toContain("Indústrias de transformação1.300 de 6.000 (21,7%)");
    expect(texto).toContain("Não aparecem, por terem poucas empresas: AC, Sem informação no cadastro.");
    expect(texto).toContain(RECORTE.como_foi_calculado);
    // a barra é só desenho: a largura vai como fração, e o leitor de tela lê o número do texto
    expect(html).toContain('style="--p:1.000"');
    expect(html).toContain('style="--p:0.500"');
    expect(html.match(/class="v2-recorte-barra" aria-hidden="true"/g)).toHaveLength(3);
    // sem setor escondido, não sai a frase das escondidas daquele lado
    expect(texto.match(/Não aparecem/g)).toHaveLength(1);
    // o recorte vem antes da conta do cartão
    expect(html.indexOf("v2-recorte")).toBeLessThan(html.indexOf("Como foi calculado"));
  });
});
