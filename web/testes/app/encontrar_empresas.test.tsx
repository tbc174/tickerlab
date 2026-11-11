// @vitest-environment jsdom
// Encontrar empresas (tela do analista, linha 798): o formulário abre com as opções da API (um pedido sem
// filtro, que não lê a base), a busca manda os filtros no corpo do POST, "Carregar mais" pede a página
// seguinte pelo cursor e o link de cada empresa abre a ficha com o CNPJ no estado da navegação, nunca no
// endereço. "Sem prontidão" é um estado da tela ("dado ainda não liberado"), nunca um erro. Capital social e
// estabelecimentos ativos filtram e ordenam, e a tela diz que são só uma aproximação do tamanho.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { BuscaDeEmpresasV1, CampoComFonteV1, EmpresaDaBuscaV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const ROTA = "/api/v1/analista/empresas";
const FICHA = "/api/v1/analista/ficha";
const LIMITES = ["Uma linha por empresa.", "Nada aqui é recomendação de investimento."];

function campo(valor: CampoComFonteV1["valor"]): CampoComFonteV1 {
  return { valor, fonte: "rfb-cnpj", publico_em: "2026-10-31", visto_em: null };
}

function empresa(cnpj: string, razao: string): EmpresaDaBuscaV1 {
  return {
    cnpj,
    razao_social: campo(razao),
    natureza_juridica: campo("2054"),
    porte: campo("other"),
    situacao_cadastral: campo("02"),
    data_inicio_atividade: campo("2010-05-04"),
    cnae_principal: campo("6201501"),
    uf: campo("MG"),
    municipio: campo("4123"),
    matriz: campo(true),
    capital_social: campo(6000000),
    n_estabelecimentos: campo(2),
    cnae_descricao: "Desenvolvimento de programas de computador sob encomenda",
    municipio_nome: "BELO HORIZONTE",
    porte_descricao: "Demais",
  };
}

const OPCOES: BuscaDeEmpresasV1 = {
  estado: "sem_filtro",
  como_era_em: null,
  empresas: [],
  cortada: false,
  proximo_cursor: null,
  fontes: [],
  limites: LIMITES,
  setores: [
    { codigo: "A", nome: "Agricultura" },
    { codigo: "C", nome: "Indústrias de transformação" },
    { codigo: "G", nome: "Comércio" },
    { codigo: "J", nome: "Informação e comunicação" },
  ],
  ufs: ["MG", "SP"],
  ordens: [
    { codigo: "maior_capital", nome: "Maior capital social" },
    { codigo: "mais_estabelecimentos", nome: "Mais estabelecimentos ativos" },
  ],
};
const FONTES = [{ fonte: "rfb-cnpj", licenca: "CC BY 4.0", atribuicao: "Receita Federal do Brasil" }];
const PRIMEIRA: BuscaDeEmpresasV1 = {
  ...OPCOES,
  estado: "pronta",
  como_era_em: "2026-11-10",
  empresas: [empresa("11111111000191", "EMPRESA ALFA S.A.")],
  cortada: true,
  proximo_cursor: "cursor-2",
  fontes: FONTES,
};
const SEGUNDA: BuscaDeEmpresasV1 = {
  ...PRIMEIRA,
  empresas: [empresa("22222222000191", "EMPRESA BETA LTDA")],
  cortada: false,
  proximo_cursor: null,
};
const VAZIA: BuscaDeEmpresasV1 = { ...PRIMEIRA, empresas: [], cortada: false, proximo_cursor: null };
const NAO_LIBERADA: BuscaDeEmpresasV1 = { ...OPCOES, estado: "nao_liberada" };

/** A API de mentira: o pedido sem filtro devolve as opções; com cursor, a segunda página; o resto, `busca`. */
function abrir(busca: BuscaDeEmpresasV1) {
  return abrirApp("/encontrar-empresas", {
    rotas: (endereco, pedido) => {
      if (endereco === FICHA) return respostaJson(200, { estado: "nao_liberada", ficha: null, fontes: [], limites: LIMITES, o_que_vem: [] });
      if (endereco !== ROTA) return undefined;
      const corpo = JSON.parse(String(pedido?.body ?? "{}")) as Record<string, unknown>;
      if (Object.keys(corpo).length === 0) return respostaJson(200, OPCOES);
      return respostaJson(200, corpo.cursor ? SEGUNDA : busca);
    },
  });
}

const corpos = (buscar: ReturnType<typeof abrir>["buscar"], rota = ROTA) =>
  buscar.mock.calls.filter(([e]) => String(e) === rota).map(([, p]) => JSON.parse(String(p?.body)));

async function buscarPor(setores: string[], idade?: string) {
  for (const nome of setores) fireEvent.click(await screen.findByRole("checkbox", { name: nome }));
  if (idade !== undefined) fireEvent.change(screen.getByLabelText("Idade mínima (anos)"), { target: { value: idade } });
  fireEvent.click(screen.getByRole("button", { name: "Encontrar empresas" }));
}

afterEach(() => {
  cleanup();
});

describe("encontrar empresas", () => {
  it("abre o formulário com as opções da API e só busca com um filtro escolhido", async () => {
    const { buscar } = abrir(PRIMEIRA);
    expect(await screen.findByRole("heading", { name: "Encontrar empresas" })).toBeTruthy();
    expect(await screen.findByRole("checkbox", { name: "Informação e comunicação" })).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: "SP" })).toBeTruthy();
    expect(corpos(buscar)).toEqual([{}]);
    expect((screen.getByRole("button", { name: "Encontrar empresas" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/pessoa física, MEI e empresário individual não aparecem/i)).toBeTruthy();
  });

  it("até três setores: o quarto fica desligado", async () => {
    abrir(PRIMEIRA);
    for (const nome of ["Agricultura", "Indústrias de transformação", "Comércio"]) {
      fireEvent.click(await screen.findByRole("checkbox", { name: nome }));
    }
    expect((screen.getByRole("checkbox", { name: "Informação e comunicação" }) as HTMLInputElement).disabled).toBe(true);
  });

  it("pronta: os filtros vão no corpo; a tabela traz os nomes da Receita, a fonte e os limites", async () => {
    const { buscar } = abrir(PRIMEIRA);
    await buscarPor(["Informação e comunicação", "MG"], "10");
    const linha = await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(corpos(buscar)[1]).toEqual({ setores: ["J"], ufs: ["MG"], idade_minima: 10 });
    expect(linha.textContent).toContain("11.111.111/0001-91");
    expect(linha.textContent).toContain("Desenvolvimento de programas de computador sob encomenda (6201501)");
    expect(linha.textContent).toContain("BELO HORIZONTE / MG");
    expect(linha.textContent).toContain("04/05/2010");
    expect(linha.textContent).toContain("Demais");
    expect(screen.getByText(/Fonte: rfb-cnpj · publicado em 31\/10\/2026/)).toBeTruthy();
    expect(screen.getByText(/como a base conhecia em 10\/11\/2026/)).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Fontes" })).getByText(/Receita Federal do Brasil/)).toBeTruthy();
    const limites = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(within(limites).getByText(/recomendação de investimento/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Baixar em Excel" })).toBeTruthy();
  });

  it("capital, estabelecimentos e ordem vão no corpo; a tabela mostra os dois, como aproximação", async () => {
    const { buscar } = abrir(PRIMEIRA);
    const capital = await screen.findByLabelText("Capital social mínimo (R$)");
    expect(screen.getByText(/só uma aproximação do tamanho/)).toBeTruthy();
    fireEvent.change(capital, { target: { value: "1000000" } });
    fireEvent.change(screen.getByLabelText("Estabelecimentos ativos, no mínimo"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Ordenar por"), { target: { value: "maior_capital" } });
    fireEvent.click(screen.getByRole("button", { name: "Encontrar empresas" }));
    const linha = await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(corpos(buscar)[1]).toEqual({
      setores: [],
      ufs: [],
      capital_minimo: 1000000,
      estabelecimentos_minimo: 2,
      ordem: "maior_capital",
    });
    expect(linha.textContent).toMatch(/R\$\s6\.000\.000/);
    expect(screen.getByRole("columnheader", { name: "Estabelecimentos ativos" })).toBeTruthy();
    // a ordem vai junto no "Carregar mais", com o cursor
    fireEvent.click(screen.getByRole("button", { name: "Carregar mais" }));
    await screen.findByRole("row", { name: /EMPRESA BETA LTDA/ });
    expect(corpos(buscar).at(-1)).toMatchObject({ ordem: "maior_capital", cursor: "cursor-2" });
  });

  it("a ordem sozinha não é filtro: o botão segue desligado", async () => {
    abrir(PRIMEIRA);
    fireEvent.change(await screen.findByLabelText("Ordenar por"), { target: { value: "maior_capital" } });
    expect((screen.getByRole("button", { name: "Encontrar empresas" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Capital social máximo (R$)"), { target: { value: "500000" } });
    expect((screen.getByRole("button", { name: "Encontrar empresas" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("carregar mais: manda o cursor com os mesmos filtros e junta a página seguinte embaixo", async () => {
    const { buscar } = abrir(PRIMEIRA);
    await buscarPor(["SP"]);
    fireEvent.click(await screen.findByRole("button", { name: "Carregar mais" }));
    expect(await screen.findByRole("row", { name: /EMPRESA BETA LTDA/ })).toBeTruthy();
    expect(screen.getByRole("row", { name: /EMPRESA ALFA S\.A\./ })).toBeTruthy();
    expect(corpos(buscar).at(-1)).toEqual({ setores: [], ufs: ["SP"], cursor: "cursor-2" });
    expect(screen.queryByRole("button", { name: "Carregar mais" })).toBeNull();
  });

  it("o link abre a ficha com o CNPJ no corpo do pedido, nunca no endereço", async () => {
    const { buscar } = abrir(PRIMEIRA);
    await buscarPor(["SP"]);
    fireEvent.click(await screen.findByRole("link", { name: "EMPRESA ALFA S.A." }));
    expect(await screen.findByRole("heading", { name: "Ficha da empresa" })).toBeTruthy();
    await waitFor(() => expect(corpos(buscar, FICHA)).toEqual([{ cnpj: "11111111000191" }]));
    const enderecos = buscar.mock.calls.map(([e]) => String(e));
    expect(enderecos.some((e) => e.includes("11111111000191"))).toBe(false);
    expect((screen.getByLabelText("CNPJ") as HTMLInputElement).value).toBe("11111111000191");
  });

  it("nenhuma empresa: a frase no lugar da tabela, sem Excel", async () => {
    abrir(VAZIA);
    await buscarPor(["SP"]);
    expect(await screen.findByText("Nenhuma empresa com esses filtros.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Baixar em Excel" })).toBeNull();
  });

  it("dado ainda não liberado: estado da tela, sem alerta de erro e com os limites à vista", async () => {
    abrir(NAO_LIBERADA);
    await buscarPor(["SP"]);
    expect(await screen.findByText(/Dado ainda não liberado/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("region", { name: "Limites e cuidados" })).toBeTruthy();
  });
});
