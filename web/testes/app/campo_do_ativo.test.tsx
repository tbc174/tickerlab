// @vitest-environment jsdom
// O campo Ativo do app novo procura no catálogo (web/conteudo/ativos.json, o mesmo do Streamlit) pelo
// código ou pelo nome, sem ligar para maiúsculas nem acentos, e um código fora da lista continua valendo.
// Regra SEARCH-03 (src/catalogo.py): nunca trocar o ativo sem avisar; o que se digita só é ligado ao
// catálogo quando bate exatamente com um código dele.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type Ativo, carregarAtivos, resolverAtivo, sugestoes } from "../../src/app/buscaDeAtivos";
import { Formulario, valoresIniciais } from "../../src/app/Formulario";
import { paginasDoApp } from "../../src/conteudo";

const ROTULO_DA_PETROBRAS = "PETR4 · Petroleo Brasileiro S.A. Petrobras PN · B3 · Ação";

function abrir(busca = "") {
  const entradas = paginasDoApp.find((p) => p.url === "visao-geral")!.contrato!.entradas;
  const aoAnalisar = vi.fn();
  render(
    <Formulario entradas={entradas} valores={valoresIniciais(entradas, new URLSearchParams(busca))} aoAnalisar={aoAnalisar} />,
  );
  return { aoAnalisar, campo: screen.getByRole("combobox", { name: "Ativo" }) as HTMLInputElement };
}

const digitar = (campo: HTMLElement, texto: string) => fireEvent.change(campo, { target: { value: texto } });
const analisar = () => fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
// as sugestões do Ativo (o Período também tem <option>)
const sugeridas = async () => within(await screen.findByRole("listbox", { name: "Ativos do catálogo" })).getAllByRole("option");
const opcoes = async () => (await sugeridas()).map((o) => o.textContent);

afterEach(cleanup);

describe("busca no catálogo (funções)", () => {
  let ativos: Ativo[];
  const nomes = (texto: string) => sugestoes(ativos, texto).map((a) => a.simbolo);

  it("acha pelo nome, sem ligar para maiúsculas nem acentos", async () => {
    ativos = await carregarAtivos();
    expect(nomes("petrobras")).toEqual(expect.arrayContaining(["PETR4.SA", "PETR3.SA"]));
    expect(nomes("PETRÓLEO BRASILEIRO")).toContain("PETR4.SA");
    expect(nomes("petroreconcavo")).toContain("RECV3.SA"); // no catálogo: "Petrorecôncavo"
    // a palavra inteira vem antes do começo de palavra ("itau": Itaú Unibanco antes da Itaúsa), e as ações
    // antes dos fundos com o mesmo nome (são dezenas de "Itaú ... FII")
    expect(nomes("itau").slice(0, 4)).toEqual(["ITUB3.SA", "ITUB4.SA", "ITSA3.SA", "ITSA4.SA"]);
  });

  it("acha pelo código, e o código exato vem primeiro", async () => {
    ativos = await carregarAtivos();
    expect(nomes("petr4")[0]).toBe("PETR4.SA");
    expect(nomes("ibov")[0]).toBe("^BVSP");
    expect(nomes("bova11")[0]).toBe("BOVA11.SA"); // ETF: o código exato vem antes de tudo, de qualquer tipo
  });

  it("mostra poucas sugestões e nenhuma com o campo vazio", async () => {
    ativos = await carregarAtivos();
    expect(nomes("a").length).toBeLessThanOrEqual(8);
    expect(nomes("   ")).toEqual([]);
  });

  it("só liga ao catálogo o código exato (SEARCH-03); o resto vai como foi digitado", async () => {
    ativos = await carregarAtivos();
    expect(resolverAtivo(ativos, " petr4 ")).toBe("PETR4.SA");
    expect(resolverAtivo(ativos, "ibov")).toBe("^BVSP");
    expect(resolverAtivo(ativos, "PETR4.SA")).toBe("PETR4.SA");
    expect(resolverAtivo(ativos, "petr")).toBe("PETR"); // prefixo: não vira PETR4 sozinho
    expect(resolverAtivo(ativos, "Petrobras")).toBe("PETROBRAS");
    expect(resolverAtivo(ativos, "xpto11")).toBe("XPTO11");
  });
});

describe("campo Ativo do formulário", () => {
  it("é uma caixa de busca acessível: combobox ligado à lista, fechado no começo", () => {
    const { campo } = abrir();
    expect(campo.getAttribute("aria-autocomplete")).toBe("list");
    expect(campo.getAttribute("aria-expanded")).toBe("false");
    expect(campo.getAttribute("autocomplete")).toBe("off");
    expect(campo.value).toBe("PETR4.SA");
  });

  it("buscar pelo nome mostra a lista com o rótulo do catálogo, e o clique escolhe", async () => {
    const { aoAnalisar, campo } = abrir();
    digitar(campo, "petrobras");
    expect(await opcoes()).toContain(ROTULO_DA_PETROBRAS);
    expect(campo.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById(campo.getAttribute("aria-controls")!)?.getAttribute("role")).toBe("listbox");
    fireEvent.click((await sugeridas()).find((o) => o.textContent === ROTULO_DA_PETROBRAS)!);
    expect(campo.value).toBe("PETR4");
    expect(screen.queryByRole("listbox")).toBeNull();
    analisar();
    expect(aoAnalisar).toHaveBeenCalledWith(expect.objectContaining({ ticker: "PETR4.SA" }));
  });

  it("buscar pelo código acha o ativo; o código exato vale mesmo sem escolher na lista", async () => {
    const { aoAnalisar, campo } = abrir();
    // digitado logo ao abrir, antes de o catálogo chegar (a carga é assíncrona): liga quando ele chega
    digitar(campo, "vale3");
    expect((await opcoes())[0]).toMatch(/^VALE3 · /);
    analisar();
    expect(aoAnalisar).toHaveBeenCalledWith(expect.objectContaining({ ticker: "VALE3.SA" }));
  });

  it("um código fora da lista continua valendo e o campo avisa que está fora do catálogo", async () => {
    const { aoAnalisar, campo } = abrir();
    digitar(campo, "xpto11");
    expect(await screen.findByText(/fora do catálogo/)).toBeTruthy();
    expect(campo.getAttribute("aria-describedby")).toBeTruthy();
    analisar();
    expect(aoAnalisar).toHaveBeenCalledWith(expect.objectContaining({ ticker: "XPTO11" }));
  });

  it("escolhe pelo teclado: setas andam, Enter escolhe sem enviar, Esc fecha", async () => {
    const { aoAnalisar, campo } = abrir();
    digitar(campo, "itau");
    await opcoes();
    fireEvent.keyDown(campo, { key: "ArrowDown" });
    const primeira = (await sugeridas())[0];
    expect(campo.getAttribute("aria-activedescendant")).toBe(primeira.id);
    expect(primeira.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(campo, { key: "ArrowDown" });
    fireEvent.keyDown(campo, { key: "ArrowUp" });
    expect(campo.getAttribute("aria-activedescendant")).toBe(primeira.id);
    const escolhida = primeira.textContent!.split(" · ")[0];
    fireEvent.keyDown(campo, { key: "Enter" });
    expect(campo.value).toBe(escolhida);
    expect(aoAnalisar).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();

    digitar(campo, "vale");
    await opcoes();
    fireEvent.keyDown(campo, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(campo.value).toBe("vale"); // fechar não troca o que foi digitado
  });

  it("Enter sem opção marcada envia o que foi digitado, sem pegar a primeira da lista", async () => {
    const { aoAnalisar, campo } = abrir();
    digitar(campo, "petr");
    await opcoes();
    fireEvent.submit(campo.closest("form")!);
    expect(aoAnalisar).toHaveBeenCalledWith(expect.objectContaining({ ticker: "PETR" }));
  });
});
