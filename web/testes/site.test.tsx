// O site em React sai igual ao gerado por scripts/gerar_site.py (o site/ de hoje): mesmas tags,
// atributos e textos em cada página, mesmo CSS e mesmo site.js. Só o comentário de origem e o
// pedaço de hash do `?v=` mudam.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Parser } from "htmlparser2";
import { describe, expect, it } from "vitest";
import { arquivos, arquivosFixos, renderizar } from "../src/entry-server";
import { ROTAS } from "../src/rotas";

const SITE_ATUAL = join(process.cwd(), "..", "site");
const atual = (nome: string) =>
  readFileSync(join(SITE_ATUAL, nome), "utf8").replace(/\r\n/g, "\n"); // CRLF do Git no Windows
const semAPrimeiraLinha = (texto: string) => texto.slice(texto.indexOf("\n") + 1);

function normalizarAtributo(nome: string, valor: string): string {
  if (nome === "style") return valor.replace(/\s+/g, "");
  return valor.replace(/\?v=[0-9a-f]{12}$/, "?v=…"); // o hash muda com o comentário de origem
}

/** O HTML como lista de eventos (tag com atributos em ordem, texto sem sobras de espaço). */
export function canonico(html: string): string[] {
  const eventos: string[] = [];
  let texto = "";
  const soltarTexto = () => {
    const limpo = texto.replace(/\s+/g, " ").trim();
    if (limpo) eventos.push(`#${limpo}`);
    texto = "";
  };
  const parser = new Parser(
    {
      onopentag(nome, atributos) {
        soltarTexto();
        const lista = Object.entries(atributos)
          .map(([k, v]) => `${k}="${normalizarAtributo(k, v)}"`)
          .sort();
        eventos.push(`<${nome} ${lista.join(" ")}>`);
      },
      ontext(pedaco) {
        texto += pedaco;
      },
      onclosetag(nome) {
        soltarTexto();
        eventos.push(`</${nome}>`);
      },
    },
    { decodeEntities: true, recognizeSelfClosing: true },
  );
  parser.write(html);
  parser.end();
  soltarTexto();
  return eventos;
}

describe("rotas do site", () => {
  it("cada página vira um arquivo .html diferente", () => {
    const nomes = ROTAS.map((r) => r.arquivo);
    expect(new Set(nomes).size).toBe(nomes.length);
    for (const nome of nomes) expect(nome).toMatch(/^[a-z0-9-]+\.html$/);
  });
});

describe("igual ao site de antes da troca", () => {
  for (const arquivo of arquivos) {
    it(`${arquivo}: mesmas tags, atributos e textos`, () => {
      expect(canonico(renderizar(arquivo))).toEqual(canonico(atual(arquivo)));
    });
  }

  it("estilo.css igual (fora o comentário de origem)", () => {
    expect(semAPrimeiraLinha(arquivosFixos()["estilo.css"])).toBe(
      semAPrimeiraLinha(atual("estilo.css")),
    );
  });

  it("site.js igual (fora o comentário de origem)", () => {
    expect(semAPrimeiraLinha(arquivosFixos()["site.js"])).toBe(
      semAPrimeiraLinha(atual("site.js")),
    );
  });
});

describe("HTML pronto", () => {
  it("começa com o doctype e em português", () => {
    const html = renderizar("index.html");
    expect(html.startsWith("<!doctype html>\n<html lang=\"pt-BR\">")).toBe(true);
  });

  it("nenhuma marca de HTML cru sobra depois de expandir", () => {
    for (const arquivo of arquivos) expect(renderizar(arquivo)).not.toContain("tl-bruto");
  });

  it("o comparador pega diferença de verdade", () => {
    const html = atual("index.html");
    expect(canonico(html.replace("Seis frentes", "Sete frentes"))).not.toEqual(canonico(html));
    expect(canonico(html.replace('id="relatorios"', 'id="outro"'))).not.toEqual(canonico(html));
  });
});
