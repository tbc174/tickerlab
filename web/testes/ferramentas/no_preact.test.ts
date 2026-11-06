// @vitest-environment jsdom
// O ferramentas.js de verdade (site/ferramentas.js), que no navegador roda sobre o preact/compat em
// vez do React (vite.ferramentas.config.ts): os outros testes montam as ferramentas com o React, este
// confere que o arquivo publicado liga cada ferramenta das páginas prontas e responde aos campos.
import { fireEvent, screen } from "@testing-library/dom";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type DadosDoBc, ENDERECO_DOS_DADOS } from "../../src/ferramentas/dados";
import { formatarReais } from "../../src/ferramentas/numeros";

const SITE = join(process.cwd(), "..", "site");
const ler = (arquivo: string) => readFileSync(join(SITE, arquivo), "utf8");
const SCRIPT = ler("ferramentas.js");
const PAGINAS = readdirSync(SITE)
  .filter((arquivo) => arquivo.endsWith(".html"))
  .filter((arquivo) => ler(arquivo).includes("data-ferramenta="));

// o /dados/ferramentas.json, pequeno, para as ferramentas com dados do Banco Central desenharem tudo
const ontem = new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10);
const DADOS: DadosDoBc = {
  gerado_em: `${ontem}T13:40:00-03:00`,
  fonte: "Banco Central do Brasil",
  moedas: [{ codigo: "USD", nome: "Dólar dos Estados Unidos", compra: 5.0, venda: 5.0096, data: ontem }],
  cdi: { ao_ano: 0.1365, data: ontem },
  selic_meta: { ao_ano: 0.1375, data: ontem },
  poupanca: { ao_mes: 0.006704, data: ontem },
  ipca: {
    // de 1995 a 2025, para caber o período de exemplo de toda ferramenta
    meses: Array.from({ length: 31 * 12 }, (_, i) => [
      `${1995 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`,
      0.004,
    ]),
    ultimo: "2025-12",
  },
};

/** Põe o corpo da página pronta no jsdom (sem os scripts) e roda o ferramentas.js. */
async function abrir(arquivo: string) {
  document.body.innerHTML = ler(arquivo)
    .match(/<body[^>]*>([\s\S]*)<\/body>/)![1]
    .replace(/<script[\s\S]*?<\/script>/g, "");
  new Function(SCRIPT)();
  // os efeitos do Preact rodam depois do desenho, e os dados chegam depois deles
  await vi.waitFor(() => expect(document.body.textContent).not.toContain("Carregando"));
}

const erros = vi.spyOn(console, "error");
afterEach(() => {
  document.body.innerHTML = "";
  erros.mockClear();
  vi.unstubAllGlobals();
});

describe("ferramentas.js no Preact", () => {
  it("há páginas de ferramentas para conferir", () => {
    expect(PAGINAS.length).toBeGreaterThanOrEqual(10);
  });

  it.each(PAGINAS)("%s: liga toda ferramenta da página sem erro", async (arquivo) => {
    // sem internet: só o arquivo do Banco Central responde; as outras buscas falham, e a ferramenta
    // tem de dizer isso sem quebrar
    vi.stubGlobal("fetch", (endereco: string) =>
      endereco === ENDERECO_DOS_DADOS
        ? Promise.resolve(new Response(JSON.stringify(DADOS), { status: 200 }))
        : Promise.reject(new Error("sem internet no teste")),
    );
    await abrir(arquivo);
    const lugares = [...document.querySelectorAll<HTMLElement>("[data-ferramenta]")];
    expect(lugares.length).toBeGreaterThan(0);
    for (const lugar of lugares) {
      expect(lugar.dataset.ligada).toBe("sim");
      expect(lugar.querySelector("[data-resultado], output, figure, table")).not.toBeNull();
    }
    // cada ferramenta é uma raiz própria: um id repetido ligaria o rótulo ao campo de outra
    const ids = [...document.querySelectorAll("[id]")].map((el) => el.id);
    expect(ids.length - new Set(ids).size).toBe(0);
    expect(erros).not.toHaveBeenCalled();
  });

  it("na calculadora de juros, digitar a taxa muda o resultado", async () => {
    await abrir("calculadora-de-juros-compostos.html");
    const resultado = () => document.querySelector("[data-resultado]")!.textContent;
    // o exemplo: R$ 10.000 a 10% ao ano por 10 anos
    expect(resultado()).toBe(formatarReais(10000 * 1.1 ** 10));
    // o Preact escuta o "input" (o que o navegador manda a cada tecla) no lugar do onChange
    fireEvent.input(screen.getByLabelText("Taxa de juros"), { target: { value: "12" } });
    await new Promise((pronto) => setTimeout(pronto, 0));
    expect(resultado()).toBe(formatarReais(10000 * 1.12 ** 10));
  });
});
