// @vitest-environment jsdom
// O pregão mais novo no navegador: o HTML pronto traz o último pregão guardado; o ferramentas.js
// pede à API o mais novo e só troca a data e o corpo se ele for mais novo e do molde aprovado.
import { act } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pregaoDoDia } from "../../src/conteudo";
import { PregaoDoDia } from "../../src/paginas/PregaoDoDia";
import { dataDoPregao } from "../../src/site/CorpoDoPregao";
import { ENDERECO_DO_PREGAO, lerPregao, ligarPregao } from "../../src/site/PregaoAoVivo";

const erros = vi.spyOn(console, "error");
afterEach(() => {
  document.body.innerHTML = "";
  erros.mockClear();
});

const MOLDE = pregaoDoDia.molde_aprovado;
const GUARDADO = pregaoDoDia.pregao.pregao;
const MAIS_NOVO = "2099-01-02";
const FRASE_NOVA = "O Ibovespa subiu 1,0% em 02/01/2099, para 200.000 pontos.";

function respostaDaApi(dia = MAIS_NOVO, molde = MOLDE) {
  const [primeira, ...resto] = pregaoDoDia.pregao.frases;
  return {
    molde_aprovado: molde,
    pregao: {
      ...pregaoDoDia.pregao,
      pregao: dia,
      impressao_digital: molde,
      frases: [{ ...primeira, texto: FRASE_NOVA }, ...resto],
    },
  };
}

function apiQueResponde(corpo: unknown, ok = true) {
  return vi.fn(async () => ({ ok, json: async () => corpo }) as Response);
}

const datas = () => [...document.querySelectorAll("[data-pregao-do-dia]")].map((d) => d.textContent);
const corpo = () => document.querySelector("[data-corpo-do-pregao]")?.textContent ?? "";

function abrirPagina() {
  document.body.innerHTML = renderToStaticMarkup(<PregaoDoDia />);
}

describe("lerPregao: a resposta da API", () => {
  it("aceita a resposta do molde aprovado", () => {
    expect(lerPregao(respostaDaApi(), MOLDE)?.pregao).toBe(MAIS_NOVO);
  });

  it("recusa outro molde, mesmo que a API diga que é o aprovado", () => {
    expect(lerPregao(respostaDaApi(MAIS_NOVO, "outro"), MOLDE)).toBeNull();
    const meiaTroca = respostaDaApi();
    meiaTroca.pregao.impressao_digital = "outro";
    expect(lerPregao(meiaTroca, MOLDE)).toBeNull();
  });

  it("recusa o que não tem a forma da página", () => {
    for (const estragado of [
      null,
      "texto",
      { molde_aprovado: MOLDE },
      { ...respostaDaApi(), pregao: { ...respostaDaApi().pregao, frases: [] } },
      { ...respostaDaApi(), pregao: { ...respostaDaApi().pregao, tabelas: [{ titulo: 1 }] } },
      { ...respostaDaApi(), pregao: { ...respostaDaApi().pregao, limites: [] } },
      { ...respostaDaApi(), pregao: { ...respostaDaApi().pregao, pregao: "02/01/2099" } },
    ]) {
      expect(lerPregao(estragado, MOLDE)).toBeNull();
    }
  });
});

describe("ligarPregao: a página do pregão no navegador", () => {
  it("o HTML pronto traz o pregão guardado, com a data e o molde marcados", () => {
    abrirPagina();
    expect(datas()).toEqual([dataDoPregao(GUARDADO)]);
    const marca = document.querySelector<HTMLElement>("[data-pregao-do-dia]");
    expect(marca?.dataset.moldeAprovado).toBe(MOLDE);
    expect(corpo()).toContain(pregaoDoDia.pregao.frases[0].texto);
  });

  it("pregão mais novo na API: troca a data do título e o corpo, sem aviso do React", async () => {
    abrirPagina();
    const buscar = apiQueResponde(respostaDaApi());
    let trocou = false;
    await act(async () => {
      trocou = await ligarPregao(document, buscar);
    });
    expect(trocou).toBe(true);
    expect(buscar).toHaveBeenCalledWith(ENDERECO_DO_PREGAO, expect.objectContaining({ credentials: "omit" }));
    expect(datas()).toEqual([dataDoPregao(MAIS_NOVO)]);
    expect(document.querySelector("h1")?.textContent).toBe(`O pregão de ${dataDoPregao(MAIS_NOVO)}`);
    expect(corpo()).toContain(FRASE_NOVA);
    expect(corpo()).toContain("Limites e cuidados");
    expect(erros).not.toHaveBeenCalled();
  });

  it("o mesmo dia ou um mais velho: nada muda", async () => {
    for (const dia of [GUARDADO, "2000-01-03"]) {
      abrirPagina();
      const antes = document.body.innerHTML;
      await act(async () => {
        expect(await ligarPregao(document, apiQueResponde(respostaDaApi(dia)))).toBe(false);
      });
      expect(document.body.innerHTML).toBe(antes);
    }
  });

  it("API fora do ar, com erro ou com outro molde: a página fica como veio", async () => {
    const falhas = [
      vi.fn(async () => {
        throw new TypeError("rede");
      }),
      apiQueResponde({ detail: "indisponível" }, false),
      apiQueResponde(respostaDaApi(MAIS_NOVO, "outro")),
    ];
    for (const buscar of falhas) {
      abrirPagina();
      const antes = document.body.innerHTML;
      await act(async () => {
        expect(await ligarPregao(document, buscar as unknown as typeof fetch)).toBe(false);
      });
      expect(document.body.innerHTML).toBe(antes);
    }
  });

  it("página sem o pregão marcado: nem pede à API", async () => {
    document.body.innerHTML = "<p>outra página</p>";
    const buscar = apiQueResponde(respostaDaApi());
    expect(await ligarPregao(document, buscar)).toBe(false);
    expect(buscar).not.toHaveBeenCalled();
  });
});
