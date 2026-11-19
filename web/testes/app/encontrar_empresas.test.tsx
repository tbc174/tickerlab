// @vitest-environment jsdom
// Encontrar empresas (tela do analista, linha 798): o formulário abre com as opções da API (um pedido sem
// filtro, que não lê a base), a busca manda os filtros no corpo do POST, "Carregar mais" pede a página
// seguinte pelo cursor e o link de cada empresa abre a ficha com o CNPJ no estado da navegação, nunca no
// endereço. "Sem prontidão" é um estado da tela ("dado ainda não liberado"), nunca um erro. Capital social e
// estabelecimentos ativos filtram e ordenam, e a tela diz que são só uma aproximação do tamanho.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { BuscaDeEmpresasV1, CampoComFonteV1, EmpresaDaBuscaV1 } from "../../src/app/tipos";
import { aberturaDoSetor, filtroInicial } from "../../src/app/telas/EncontrarEmpresas";
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
const DUAS: BuscaDeEmpresasV1 = {
  ...PRIMEIRA,
  empresas: [empresa("11111111000191", "EMPRESA ALFA S.A."), empresa("33333333000191", "EMPRESA GAMA LTDA")],
  cortada: false,
  proximo_cursor: null,
};
const SEIS: [string, string][] = [1, 2, 3, 4, 5, 6].map((n) => [`${n}${n}${n}${n}${n}${n}${n}${n}000191`, `EMPRESA N${n} LTDA`]);
const VAZIA: BuscaDeEmpresasV1 = { ...PRIMEIRA, empresas: [], cortada: false, proximo_cursor: null };
const NAO_LIBERADA: BuscaDeEmpresasV1 = { ...OPCOES, estado: "nao_liberada" };
const AVISO_DE_PILOTO = "Dado de piloto: passou na qualidade automática, mas ainda não na conferência cruzada com outra fonte.";
const DE_PILOTO: BuscaDeEmpresasV1 = { ...PRIMEIRA, aviso_de_piloto: AVISO_DE_PILOTO };

/** A API de mentira: o pedido sem filtro devolve as opções; com cursor, a segunda página; o resto, `busca`. */
function abrir(busca: BuscaDeEmpresasV1, consulta = "") {
  return abrirApp(`/encontrar-empresas${consulta}`, {
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

const SETORES = new Set(OPCOES.setores.map((s) => s.nome));

/** Escolhe um setor pela caixa de busca: digita o nome e clica na sugestão. */
async function escolherSetor(nome: string) {
  const campo = await screen.findByRole("combobox", { name: /^Setor/ });
  fireEvent.change(campo, { target: { value: nome } });
  fireEvent.click(await screen.findByRole("option", { name: new RegExp(`^${nome}`) }));
}

/** Escolhe setores (pela caixa) e estados (pela lista), mais a idade, e busca. */
async function buscarPor(filtros: string[], idade?: string) {
  for (const nome of filtros) {
    if (SETORES.has(nome)) await escolherSetor(nome);
    else fireEvent.click(await screen.findByRole("checkbox", { name: nome }));
  }
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
    expect(await screen.findByRole("combobox", { name: /^Setor/ })).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: "SP" })).toBeTruthy();
    expect(screen.getByText("Brasil inteiro")).toBeTruthy();
    expect(corpos(buscar)).toEqual([{}]);
    expect((screen.getByRole("button", { name: "Encontrar empresas" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/pessoa física, MEI e empresário individual não aparecem/i)).toBeTruthy();
  });

  it("até três setores: escolhidos viram etiquetas e a caixa se desliga no terceiro", async () => {
    abrir(PRIMEIRA);
    for (const nome of ["Agricultura", "Indústrias de transformação", "Comércio"]) await escolherSetor(nome);
    const escolhidos = screen.getByRole("list", { name: "Setores escolhidos" });
    expect(within(escolhidos).getAllByRole("listitem").map((i) => i.textContent)).toEqual([
      "Agricultura ×",
      "Indústrias de transformação ×",
      "Comércio ×",
    ]);
    expect((screen.getByRole("combobox", { name: /^Setor/ }) as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Tirar o setor Comércio" }));
    expect((screen.getByRole("combobox", { name: /^Setor/ }) as HTMLInputElement).disabled).toBe(false);
  });

  it("a caixa do setor lista todas as seções ao abrir e acha a seção pelo nome de uma atividade", async () => {
    abrir(PRIMEIRA);
    const campo = await screen.findByRole("combobox", { name: /^Setor/ });
    fireEvent.focus(campo);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Agricultura",
      "Indústrias de transformação",
      "Comércio",
      "Informação e comunicação",
    ]);
    fireEvent.change(campo, { target: { value: "programas de computador" } });
    const opcao = await screen.findByRole("option", { name: /^Informação e comunicação/ });
    expect(opcao.textContent).toMatch(/pela atividade: .*programas de computador/i);
    fireEvent.click(opcao);
    expect(screen.getByRole("button", { name: "Tirar o setor Informação e comunicação" })).toBeTruthy();
    expect((campo as HTMLInputElement).value).toBe("");
  });

  it("o estado fica numa lista compacta que resume a escolha", async () => {
    abrir(PRIMEIRA);
    expect(await screen.findByText("Brasil inteiro")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "SP" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "MG" }));
    expect(screen.getByText("SP, MG")).toBeTruthy();
    const lista = screen.getByText("SP, MG").closest("details") as HTMLDetailsElement;
    lista.open = true;
    fireEvent.mouseDown(screen.getByRole("checkbox", { name: "SP" }));
    expect(lista.open).toBe(true); // clicar dentro não fecha
    fireEvent.mouseDown(document.body);
    expect(lista.open).toBe(false);
    lista.open = true;
    fireEvent.keyDown(document, { key: "Escape" });
    expect(lista.open).toBe(false);
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
    expect(screen.queryByText(/Dado de piloto/)).toBeNull();
  });

  it("dado de piloto: o aviso do servidor fica à vista com a lista, inclusive depois de carregar mais", async () => {
    abrir(DE_PILOTO);
    await buscarPor(["SP"]);
    await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(screen.getByText(AVISO_DE_PILOTO)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Carregar mais" }));
    await screen.findByRole("row", { name: /EMPRESA BETA LTDA/ });
    expect(screen.getByText(AVISO_DE_PILOTO)).toBeTruthy();
  });

  it("capital e estabelecimentos ficam em Mais filtros e vão no corpo; a ordem, ao lado da lista, refaz a busca", async () => {
    const { buscar } = abrir(PRIMEIRA);
    const capital = await screen.findByLabelText("Capital social mínimo (R$)");
    expect(capital.closest("details")?.open).toBe(false);
    expect(screen.getByText(/só uma aproximação do tamanho/)).toBeTruthy();
    fireEvent.change(capital, { target: { value: "1000000" } });
    fireEvent.change(screen.getByLabelText("Estabelecimentos ativos, no mínimo"), { target: { value: "2" } });
    expect(screen.getByText("Mais filtros (2 em uso)")).toBeTruthy();
    expect(screen.queryByLabelText("Ordenar por")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Encontrar empresas" }));
    await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(corpos(buscar)[1]).toEqual({ setores: [], ufs: [], capital_minimo: 1000000, estabelecimentos_minimo: 2 });
    // o formulário se refaz com os filtros buscados: "Mais filtros" abre, porque há filtro lá dentro
    expect(screen.getByLabelText("Capital social mínimo (R$)").closest("details")?.open).toBe(true);
    fireEvent.change(screen.getByLabelText("Ordenar por"), { target: { value: "maior_capital" } });
    await waitFor(() =>
      expect(corpos(buscar)[2]).toEqual({
        setores: [],
        ufs: [],
        capital_minimo: 1000000,
        estabelecimentos_minimo: 2,
        ordem: "maior_capital",
      }),
    );
    const linha = await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(linha.textContent).toMatch(/R\$\s6\.000\.000/);
    expect(screen.getByRole("columnheader", { name: "Estabelecimentos ativos" })).toBeTruthy();
    // a ordem vai junto no "Carregar mais", com o cursor
    fireEvent.click(screen.getByRole("button", { name: "Carregar mais" }));
    await screen.findByRole("row", { name: /EMPRESA BETA LTDA/ });
    expect(corpos(buscar).at(-1)).toMatchObject({ ordem: "maior_capital", cursor: "cursor-2" });
  });

  it("as faixas de capital preenchem o mínimo e o máximo, e o valor ainda se digita", async () => {
    const { buscar } = abrir(PRIMEIRA);
    const botao = (await screen.findByRole("button", { name: "Encontrar empresas" })) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    const faixa = screen.getByRole("button", { name: "R$ 1 mi a 10 mi" });
    fireEvent.click(faixa);
    expect(faixa.getAttribute("aria-pressed")).toBe("true");
    expect((screen.getByLabelText("Capital social mínimo (R$)") as HTMLInputElement).value).toBe("1000000");
    expect((screen.getByLabelText("Capital social máximo (R$)") as HTMLInputElement).value).toBe("10000000");
    expect(botao.disabled).toBe(false);
    fireEvent.change(screen.getByLabelText("Capital social máximo (R$)"), { target: { value: "500000000" } });
    expect(faixa.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Acima de R$ 100 mi" }));
    fireEvent.click(botao);
    await waitFor(() => expect(corpos(buscar)[1]).toEqual({ setores: [], ufs: [], capital_minimo: 100000000 }));
  });

  it("antes da busca, exemplos que se clicam: a lista aparece e o formulário mostra os filtros", async () => {
    const { buscar } = abrir(PRIMEIRA);
    const exemplos = await screen.findByRole("region", { name: "Exemplos de busca" });
    expect(within(exemplos).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Comércio em SP",
      "Indústrias de transformação em MG, com 20 anos ou mais",
      "Informação e comunicação, com capital social a partir de R$ 10 mi",
    ]);
    fireEvent.click(within(exemplos).getByRole("button", { name: "Indústrias de transformação em MG, com 20 anos ou mais" }));
    await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(corpos(buscar)[1]).toEqual({ setores: ["C"], ufs: ["MG"], idade_minima: 20 });
    expect(screen.getByRole("button", { name: "Tirar o setor Indústrias de transformação" })).toBeTruthy();
    expect((screen.getByRole("checkbox", { name: "MG" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Idade mínima (anos)") as HTMLInputElement).value).toBe("20");
    expect(screen.queryByRole("region", { name: "Exemplos de busca" })).toBeNull();
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

  it("a bandeja Comparar acompanha a escolha e leva os CNPJs à comparação pelo estado da navegação", async () => {
    const { buscar } = abrir(DUAS);
    await buscarPor(["SP"]);
    expect(screen.queryByRole("region", { name: "Comparar" })).toBeNull();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Escolher EMPRESA ALFA S.A. para comparar" }));
    const bandeja = screen.getByRole("region", { name: "Comparar" });
    expect(within(bandeja).getByText(/EMPRESA ALFA S\.A\./)).toBeTruthy();
    expect(within(bandeja).getByText(/escolha ao menos mais 1/)).toBeTruthy();
    expect((within(bandeja).getByRole("button", { name: "Comparar" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "Escolher EMPRESA GAMA LTDA para comparar" }));
    fireEvent.click(within(screen.getByRole("region", { name: "Comparar" })).getByRole("button", { name: "Comparar" }));
    expect(await screen.findByRole("heading", { name: "Comparar 2 empresas" })).toBeTruthy();
    expect((screen.getAllByLabelText(/^CNPJ/)[0] as HTMLInputElement).value).toBe("11111111000191");
    expect((screen.getAllByLabelText(/^CNPJ/)[1] as HTMLInputElement).value).toBe("33333333000191");
    expect(buscar.mock.calls.map(([e]) => String(e)).some((e) => e.includes("11111111000191"))).toBe(false);
  });

  it("a escolha para em cinco empresas e \"Limpar a escolha\" esvazia a bandeja", async () => {
    abrir({ ...PRIMEIRA, empresas: SEIS.map(([c, n]) => empresa(c, n)), proximo_cursor: null });
    await buscarPor(["SP"]);
    for (const [, nome] of SEIS.slice(0, 5)) {
      fireEvent.click(await screen.findByRole("checkbox", { name: `Escolher ${nome} para comparar` }));
    }
    expect((screen.getByRole("checkbox", { name: `Escolher ${SEIS[5][1]} para comparar` }) as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Limpar a escolha" }));
    expect(screen.queryByRole("region", { name: "Comparar" })).toBeNull();
  });

  it("os filtros viram etiquetas que se tiram com um clique; sem filtro nenhum, volta ao começo", async () => {
    const { buscar } = abrir(PRIMEIRA);
    await buscarPor(["Comércio", "SP"], "10");
    const etiquetas = await screen.findByRole("list", { name: "Filtros em uso" });
    expect(within(etiquetas).getAllByRole("listitem").map((i) => i.textContent)).toEqual([
      "Setor: Comércio ×",
      "Estado: SP ×",
      "Idade mínima: 10 anos ×",
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Tirar o filtro Estado: SP" }));
    await waitFor(() => expect(corpos(buscar)[2]).toEqual({ setores: ["G"], ufs: [], idade_minima: 10 }));
    // o formulário acompanha: o campo do estado ficou desmarcado
    expect((screen.getByRole("checkbox", { name: "SP" }) as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Tirar o filtro Setor: Comércio" }));
    fireEvent.click(screen.getByRole("button", { name: "Tirar o filtro Idade mínima: 10 anos" }));
    expect(await screen.findByText(/Escolha ao menos um filtro/)).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Filtros em uso" })).toBeNull();
  });

  it("o capital das etiquetas sai em reais por extenso curto, não em número solto", async () => {
    abrir(PRIMEIRA);
    fireEvent.change(await screen.findByLabelText("Capital social mínimo (R$)"), { target: { value: "5000000" } });
    fireEvent.change(screen.getByLabelText("Capital social máximo (R$)"), { target: { value: "1500000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Encontrar empresas" }));
    const etiquetas = await screen.findByRole("list", { name: "Filtros em uso" });
    expect(within(etiquetas).getAllByRole("listitem").map((i) => i.textContent)).toEqual([
      "Capital social mínimo: R$ 5 mi ×",
      "Capital social máximo: R$ 1,5 bi ×",
    ]);
  });

  it("a ordem fica ao lado da contagem e continua quando a busca muda pelo formulário", async () => {
    const { buscar } = abrir(PRIMEIRA);
    await buscarPor(["SP"]);
    expect(((await screen.findByLabelText("Ordenar por")) as HTMLSelectElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("Ordenar por"), { target: { value: "maior_capital" } });
    await waitFor(() => expect(corpos(buscar)[2]).toEqual({ setores: [], ufs: ["SP"], ordem: "maior_capital" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "MG" }));
    fireEvent.click(screen.getByRole("button", { name: "Encontrar empresas" }));
    await waitFor(() => expect(corpos(buscar)[3]).toEqual({ setores: [], ufs: ["SP", "MG"], ordem: "maior_capital" }));
    expect(((await screen.findByLabelText("Ordenar por")) as HTMLSelectElement).value).toBe("maior_capital");
  });

  it("Limpar filtros volta ao formulário vazio e tira a lista, sem nova busca", async () => {
    const { buscar } = abrir(PRIMEIRA);
    expect(((await screen.findByRole("button", { name: "Limpar filtros" })) as HTMLButtonElement).disabled).toBe(true);
    await buscarPor(["Comércio", "SP"], "10");
    await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    const antes = corpos(buscar).length;
    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(await screen.findByText(/Escolha ao menos um filtro/)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("list", { name: "Filtros em uso" })).toBeNull();
    expect(screen.queryByRole("list", { name: "Setores escolhidos" })).toBeNull();
    expect((screen.getByRole("checkbox", { name: "SP" }) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Idade mínima (anos)") as HTMLInputElement).value).toBe("");
    expect(screen.queryByLabelText("Ordenar por")).toBeNull();
    expect((screen.getByRole("button", { name: "Limpar filtros" }) as HTMLButtonElement).disabled).toBe(true);
    expect(corpos(buscar).length).toBe(antes);
  });

  it("Limpar filtros também esvazia o que ainda não foi buscado", async () => {
    abrir(PRIMEIRA);
    await escolherSetor("Agricultura");
    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(screen.queryByRole("button", { name: "Tirar o setor Agricultura" })).toBeNull();
    expect((screen.getByRole("button", { name: "Encontrar empresas" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("nenhuma empresa: a frase no lugar da tabela, sem Excel", async () => {
    abrir(VAZIA);
    await buscarPor(["SP"]);
    expect(await screen.findByText("Nenhuma empresa com esses filtros.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Baixar em Excel" })).toBeNull();
  });

  it("o setor e o estado do endereço (link dos cruzamentos do site) já abrem a busca com o filtro", async () => {
    const { buscar } = abrir(PRIMEIRA, "?setor=C&uf=SP");
    await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(corpos(buscar)).toEqual([{}, { setores: ["C"], ufs: ["SP"] }]);
    expect(screen.getByRole("button", { name: "Tirar o setor Indústrias de transformação" })).toBeTruthy();
    expect((screen.getByRole("checkbox", { name: "SP" }) as HTMLInputElement).checked).toBe(true);
    const etiquetas = screen.getByRole("list", { name: "Filtros em uso" });
    expect(within(etiquetas).getAllByRole("listitem").map((i) => i.textContent)).toEqual([
      "Setor: Indústrias de transformação ×",
      "Estado: SP ×",
    ]);
  });

  it("só o estado no endereço: busca só pelo estado", async () => {
    const { buscar } = abrir(PRIMEIRA, "?uf=MG");
    await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(corpos(buscar)[1]).toEqual({ setores: [], ufs: ["MG"] });
  });

  it("no endereço, só setor e estado contam: outros parâmetros não viram filtro", async () => {
    const { buscar } = abrir(PRIMEIRA, "?setor=J&idade_minima=10&capital_minimo=1&ordem=maior_capital&cnpj=1");
    await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(corpos(buscar)[1]).toEqual({ setores: ["J"], ufs: [] });
    expect((screen.getByLabelText("Idade mínima (anos)") as HTMLInputElement).value).toBe("");
  });

  it.each([
    ["setor e estado que o formulário não oferece", "?setor=Z&uf=XX"],
    ["seção fora da busca e estado em minúscula", "?setor=O&uf=sp"],
    ["valores vazios", "?setor=&uf="],
    ["só outros parâmetros", "?idade_minima=10"],
  ])("valor inválido no endereço (%s): filtro vazio, sem erro e sem busca", async (_caso, consulta) => {
    const { buscar } = abrir(PRIMEIRA, consulta);
    const botao = (await screen.findByRole("button", { name: "Encontrar empresas" })) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(screen.getByText(/Escolha ao menos um filtro/)).toBeTruthy();
    expect(corpos(buscar)).toEqual([{}]);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("list", { name: "Filtros em uso" })).toBeNull();
  });

  it("um valor bom e outro ruim: fica só o bom", async () => {
    const { buscar } = abrir(PRIMEIRA, "?setor=Z&uf=SP");
    await screen.findByRole("row", { name: /EMPRESA ALFA S\.A\./ });
    expect(corpos(buscar)[1]).toEqual({ setores: [], ufs: ["SP"] });
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

describe("filtro com que a busca começa", () => {
  const DO_ENDERECO = { setores: ["C"], ufs: ["SP"] };

  it("o que o Setor mandou vale antes do endereço", () => {
    const abertura = aberturaDoSetor({ doSetor: { cnae: "6201501", uf: "MG" } }, OPCOES);
    expect(filtroInicial(abertura, DO_ENDERECO)).toEqual({ setores: ["J"], ufs: ["MG"] });
  });

  it("o Setor sem filtro também vale: a nota dele diz que nada entrou, e o endereço não entra calado", () => {
    const abertura = aberturaDoSetor({ doSetor: { cnae: "8411600", uf: null } }, OPCOES);
    expect(filtroInicial(abertura, DO_ENDERECO)).toBeNull();
  });

  it("sem o Setor, vale o endereço; sem os dois, filtro vazio", () => {
    expect(filtroInicial(null, DO_ENDERECO)).toEqual(DO_ENDERECO);
    expect(filtroInicial(null, null)).toBeNull();
  });
});

describe("abertura vinda do Setor", () => {
  it("o CNAE vira a seção dele e a UF vira o estado, só se o formulário os oferece", () => {
    expect(aberturaDoSetor({ doSetor: { cnae: "6201501", uf: "SP" } }, OPCOES)).toMatchObject({
      filtros: { setores: ["J"], ufs: ["SP"] },
    });
    expect(aberturaDoSetor({ doSetor: { cnae: "62015", uf: null } }, OPCOES)?.filtros).toEqual({ setores: ["J"], ufs: [] });
    expect(aberturaDoSetor({ doSetor: { cnae: "6201501", uf: "XX" } }, OPCOES)?.filtros).toEqual({ setores: ["J"], ufs: [] });
    expect(aberturaDoSetor({ doSetor: { cnae: "6201501", uf: "sp" } }, OPCOES)?.filtros).toEqual({ setores: ["J"], ufs: [] });
  });

  it("seção fora da busca: só o estado entra, e sem estado não há filtro", () => {
    const com = aberturaDoSetor({ doSetor: { cnae: "8411600", uf: "MG" } }, OPCOES);
    expect(com?.filtros).toEqual({ setores: [], ufs: ["MG"] });
    expect(com?.nota).toMatch(/não está nesta busca/);
    expect(aberturaDoSetor({ doSetor: { cnae: "8411600", uf: null } }, OPCOES)?.filtros).toBeNull();
  });

  it("a nota diz que a busca usa a seção, mais ampla que o CNAE", () => {
    const nota = aberturaDoSetor({ doSetor: { cnae: "6201501", uf: "SP" } }, OPCOES)?.nota ?? "";
    expect(nota).toContain("CNAE 6201501");
    expect(nota).toContain("Informação e comunicação");
    expect(nota).toMatch(/mais ampla/);
  });

  it.each([
    ["sem estado", null],
    ["sem estado (indefinido)", undefined],
    ["texto", "doSetor"],
    ["outro estado da navegação", { cnpjs: ["11111111000191"] }],
    ["setor sem forma", { doSetor: "6201501" }],
    ["CNAE curto", { doSetor: { cnae: "62", uf: null } }],
    ["CNAE com letra", { doSetor: { cnae: "62015AB", uf: null } }],
    ["CNAE que não é número", { doSetor: { cnae: 6201501, uf: null } }],
    ["divisão que não existe", { doSetor: { cnae: "0400000", uf: null } }],
  ])("estado que não é do Setor (%s): não abre filtro nenhum", (_caso, estado) => {
    expect(aberturaDoSetor(estado, OPCOES)).toBeNull();
  });
});
