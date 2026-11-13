// @vitest-environment jsdom
// As peças únicas do app (plano de 13/11/2026): cada tela monta a página com as mesmas peças, e cada peça
// mora num arquivo só. Os dados dos testes são inventados e não têm pessoa nem empresa de verdade.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErroDaApi } from "../../src/app/api";
import { Abas } from "../../src/app/pecas/Abas";
import { Baixar } from "../../src/app/pecas/Baixar";
import { Cabecalho } from "../../src/app/pecas/Cabecalho";
import { CartaoDeNumero } from "../../src/app/pecas/CartaoDeNumero";
import { Erro } from "../../src/app/pecas/Erro";
import { Fonte, Fontes } from "../../src/app/pecas/Fonte";
import { Limites } from "../../src/app/pecas/Limites";
import { Selo } from "../../src/app/pecas/Selo";
import { type Coluna, Tabela } from "../../src/app/pecas/Tabela";
import { respostaJson } from "./ajudantes";

// a conta aberta sem o provedor inteiro (que pede o login do Google): só o que as peças leem
vi.mock("../../src/app/conta", async (original) => ({
  ...(await original<typeof import("../../src/app/conta")>()),
  useConta: () => ({ token: "sessao", pedirAceite: () => {} }),
}));

const APP = join(process.cwd(), "src", "app");
const CSS = readFileSync(join(APP, "app.css"), "utf8");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("uma peça, um arquivo", () => {
  it.each(["Carregando", "Vazio", "CabecalhoDaTela", "telas/ErroDaTela"])(
    "%s não tem mais cópia fora de pecas/",
    (antigo) => expect(existsSync(join(APP, `${antigo}.tsx`))).toBe(false),
  );

  it("a pasta tem as peças do plano", () => {
    const pecas = readdirSync(join(APP, "pecas")).map((nome) => nome.replace(".tsx", ""));
    for (const peca of ["Abas", "Baixar", "Cabecalho", "Carregando", "CartaoDeNumero", "Erro", "Fonte", "Limites"])
      expect(pecas).toContain(peca);
    for (const peca of ["Selo", "Tabela", "Vazio"]) expect(pecas).toContain(peca);
  });
});

describe("Cabecalho", () => {
  it("mostra o olho, o título como h1, os selos ao lado e as ações", () => {
    render(
      <Cabecalho
        olho="Empresas"
        titulo="Empresa de Exemplo S.A."
        descricao="Cadastro inventado para o teste."
        selos={<Selo tom="bom">Ativa</Selo>}
        acoes={<button type="button">Comparar</button>}
      />,
    );
    const titulo = screen.getByRole("heading", { level: 1, name: "Empresa de Exemplo S.A." });
    const cabecalho = titulo.closest("header") as HTMLElement;
    expect(within(cabecalho).getByText("Empresas").classList.contains("olho")).toBe(true);
    expect(titulo.parentElement?.textContent).toContain("Ativa");
    expect(screen.getByRole("button", { name: "Comparar" }).closest(".cabecalho-acoes")).not.toBeNull();
  });

  it("sem olho, descrição e ações, sobra só o título", () => {
    const { container } = render(<Cabecalho titulo="Setores" />);
    expect(container.querySelector(".olho, .apagado, .cabecalho-acoes")).toBeNull();
  });
});

const ABAS = [
  { chave: "resumo", rotulo: "Resumo", conteudo: <p>Texto do resumo</p> },
  { chave: "cadastro", rotulo: "Cadastro", conteudo: <p>Texto do cadastro</p> },
  { chave: "eventos", rotulo: "Eventos", conteudo: <p>Texto dos eventos</p>, contagem: 3 },
];

function Endereco() {
  return <output data-testid="endereco">{useLocation().search}</output>;
}

function abrirAbas(endereco = "/ficha", parametro?: string) {
  return render(
    <MemoryRouter initialEntries={[endereco]}>
      <Abas rotulo="Partes da ficha" abas={ABAS} parametro={parametro} />
      <Endereco />
    </MemoryRouter>,
  );
}

describe("Abas", () => {
  it("abre na primeira aba e monta só o conteúdo dela", () => {
    abrirAbas();
    const lista = screen.getByRole("tablist", { name: "Partes da ficha" });
    expect(within(lista).getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("tab", { name: "Resumo" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel").textContent).toBe("Texto do resumo");
    expect(screen.queryByText("Texto do cadastro")).toBeNull();
  });

  it("o clique troca a aba e o painel aponta para a aba aberta", () => {
    abrirAbas();
    const cadastro = screen.getByRole("tab", { name: "Cadastro" });
    fireEvent.click(cadastro);
    expect(cadastro.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: "Resumo" }).getAttribute("tabindex")).toBe("-1");
    const painel = screen.getByRole("tabpanel");
    expect(painel.getAttribute("aria-labelledby")).toBe(cadastro.id);
    expect(cadastro.getAttribute("aria-controls")).toBe(painel.id);
    expect(painel.textContent).toBe("Texto do cadastro");
  });

  it("as setas, Home e End trocam de aba e levam o foco, dando a volta nas pontas", () => {
    abrirAbas();
    const aberta = () => screen.getByRole("tab", { selected: true });
    fireEvent.keyDown(aberta(), { key: "ArrowLeft" });
    expect(aberta().textContent).toContain("Eventos");
    expect(document.activeElement).toBe(aberta());
    fireEvent.keyDown(aberta(), { key: "ArrowRight" });
    expect(aberta().textContent).toBe("Resumo");
    fireEvent.keyDown(aberta(), { key: "End" });
    expect(aberta().textContent).toContain("Eventos");
    fireEvent.keyDown(aberta(), { key: "Home" });
    expect(aberta().textContent).toBe("Resumo");
  });

  it("a contagem aparece ao lado do rótulo", () => {
    abrirAbas();
    expect(screen.getByRole("tab", { name: /Eventos/ }).querySelector(".aba-contagem")?.textContent).toBe("3");
  });

  it("com parâmetro, a aba aberta vem do endereço e vai para ele, sem perder os outros parâmetros", () => {
    abrirAbas("/ficha?origem=busca&aba=cadastro", "aba");
    expect(screen.getByRole("tab", { name: "Cadastro" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: /Eventos/ }));
    expect(screen.getByTestId("endereco").textContent).toBe("?origem=busca&aba=eventos");
    expect(screen.getByRole("tabpanel").textContent).toBe("Texto dos eventos");
  });

  it("aba desconhecida no endereço abre a primeira", () => {
    abrirAbas("/ficha?aba=nao-existe", "aba");
    expect(screen.getByRole("tab", { name: "Resumo" }).getAttribute("aria-selected")).toBe("true");
  });

  it("sem aba nenhuma, não desenha nada", () => {
    const { container } = render(
      <MemoryRouter>
        <Abas rotulo="Vazias" abas={[]} />
      </MemoryRouter>,
    );
    expect(container.innerHTML).toBe("");
  });
});

interface Linha {
  setor: string;
  empresas: number;
}
const COLUNAS: Coluna<Linha>[] = [
  { chave: "setor", titulo: "Setor", celula: (linha) => linha.setor },
  { chave: "empresas", titulo: "Empresas", numero: true, celula: (linha) => String(linha.empresas) },
];
const LINHAS: Linha[] = [
  { setor: "Setor inventado A", empresas: 12 },
  { setor: "Setor inventado B", empresas: 7 },
];

function tabela(linhas: Linha[], extras: { vazio?: string; legendaEscondida?: boolean } = {}) {
  return render(
    <MemoryRouter>
      <Tabela
        legenda="Empresas por setor"
        colunas={COLUNAS}
        linhas={linhas}
        chaveDaLinha={(linha) => linha.setor}
        {...extras}
      />
    </MemoryRouter>,
  );
}

describe("Tabela", () => {
  it("tem legenda, cabeçalho de coluna com escopo e uma linha por item", () => {
    tabela(LINHAS);
    const grade = screen.getByRole("table", { name: "Empresas por setor" });
    const cabecalhos = within(grade).getAllByRole("columnheader");
    expect(cabecalhos.map((th) => th.textContent)).toEqual(["Setor", "Empresas"]);
    expect(cabecalhos.every((th) => th.getAttribute("scope") === "col")).toBe(true);
    expect(within(grade).getAllByRole("row")).toHaveLength(3);
  });

  it("a coluna de número marca o cabeçalho e as células, e o CSS alinha à direita", () => {
    tabela(LINHAS);
    expect(screen.getByRole("columnheader", { name: "Empresas" }).className).toBe("numero");
    expect(screen.getByRole("cell", { name: "12" }).className).toBe("numero");
    expect(screen.getByRole("cell", { name: "Setor inventado A" }).className).toBe("");
    expect(CSS).toMatch(/\.tabela-da-peca th\.numero, \.tabela-da-peca td\.numero \{ text-align: right; \}/);
  });

  it("rola de lado dentro de uma região que recebe o foco do teclado", () => {
    tabela(LINHAS);
    const regiao = screen.getByRole("region", { name: "Empresas por setor" });
    expect(regiao.classList.contains("tabela-rolavel")).toBe(true);
    expect(regiao.getAttribute("tabindex")).toBe("0");
  });

  it("sem linha e com a frase do vazio, mostra a frase no lugar da tabela", () => {
    tabela([], { vazio: "Nenhum setor com esses filtros." });
    expect(screen.getByText("Nenhum setor com esses filtros.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("a legenda escondida continua valendo para o leitor de tela", () => {
    tabela(LINHAS, { legendaEscondida: true });
    expect(screen.getByRole("table", { name: "Empresas por setor" }).querySelector("caption")?.className).toBe(
      "so-para-leitor",
    );
    expect(CSS).toContain(".so-para-leitor {");
  });
});

describe("Fonte e Fontes", () => {
  it("a linha curta diz a fonte e a data do dado", () => {
    render(<Fonte nome="Receita Federal" data="10/2026" />);
    expect(screen.getByText("Fonte: Receita Federal · dado de 10/2026")).toBeTruthy();
  });

  it("sem data, a linha não inventa uma", () => {
    const { container } = render(<Fonte nome="CVM" data={null} />);
    expect(container.textContent).toBe("Fonte: CVM");
  });

  it("a seção lista a atribuição e a licença de cada fonte", () => {
    render(
      <Fontes
        fontes={[
          { fonte: "rfb_cnpj", atribuicao: "Receita Federal, cadastro de CNPJ", licenca: "dados abertos" },
          { fonte: "cvm_cadastro", atribuicao: "CVM, cadastro de companhias" },
        ]}
      />,
    );
    const secao = screen.getByRole("region", { name: "Fontes" });
    const itens = within(secao).getAllByRole("listitem");
    expect(itens[0]?.textContent).toBe("Receita Federal, cadastro de CNPJ (rfb_cnpj; licença: dados abertos)");
    expect(itens[1]?.textContent).toBe("CVM, cadastro de companhias (cvm_cadastro)");
  });

  it("sem fonte nenhuma, a seção não aparece", () => {
    const { container } = render(<Fontes fontes={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("Limites", () => {
  it("lista cada limite sob o título 'Limites e cuidados'", () => {
    render(<Limites itens={["Só empresas com CNPJ ativo.", "O faturamento não é público."]} />);
    const secao = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(within(secao).getAllByRole("listitem")).toHaveLength(2);
  });

  it("sem item, a seção fica e avisa que os limites não vieram", () => {
    render(<Limites itens={[]} />);
    const secao = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(secao.textContent).toContain("não vieram na resposta");
  });
});

function baixarCom(resposta: () => Promise<Response>, extras: { corpo?: unknown } = {}) {
  const pedidos = vi.fn(resposta);
  vi.stubGlobal("fetch", pedidos);
  const salvos: string[] = [];
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:teste", revokeObjectURL: () => {} }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    salvos.push(this.download);
  });
  render(
    <Baixar rotulo="Baixar em Excel" rota="/v1/empresas/ficha/planilha" nome="ficha-tickerlab.xlsx" {...extras} />,
  );
  return { pedidos, salvos };
}

describe("Baixar", () => {
  it("pede a rota com o corpo e salva o arquivo com o nome dado", async () => {
    const corpo = { cnpj: "00000000000191" };
    const { pedidos, salvos } = baixarCom(async () => new Response(new Blob(["x"]), { status: 200 }), { corpo });
    fireEvent.click(screen.getByRole("button", { name: "Baixar em Excel" }));
    await waitFor(() => expect(salvos).toEqual(["ficha-tickerlab.xlsx"]));
    const [endereco, pedido] = pedidos.mock.calls[0] as unknown as [string, RequestInit];
    expect(endereco).toContain("/empresas/ficha/planilha");
    expect(endereco).not.toContain("00000000000191"); // o CNPJ vai no corpo, nunca no endereço
    expect(pedido.method).toBe("POST");
    expect(pedido.body).toBe(JSON.stringify(corpo));
  });

  it("enquanto baixa, o botão fica desligado: dois cliques não viram dois pedidos", async () => {
    const { pedidos } = baixarCom(() => new Promise(() => {}));
    const botao = screen.getByRole("button", { name: "Baixar em Excel" }) as HTMLButtonElement;
    fireEvent.click(botao);
    await waitFor(() => expect(botao.disabled).toBe(true));
    fireEvent.click(botao);
    expect(pedidos).toHaveBeenCalledTimes(1);
  });

  it("se a API recusar, mostra a mensagem dela e o botão volta", async () => {
    const recusa = { erro: { tipo: "indisponivel", mensagem: "A planilha não está disponível agora." } };
    const { salvos } = baixarCom(async () => respostaJson(503, recusa));
    fireEvent.click(screen.getByRole("button", { name: "Baixar em Excel" }));
    expect((await screen.findByRole("alert")).textContent).toBeTruthy();
    expect((screen.getByRole("button", { name: "Baixar em Excel" }) as HTMLButtonElement).disabled).toBe(false);
    expect(salvos).toEqual([]);
  });
});

describe("Erro", () => {
  it("aceita uma frase solta e oferece tentar de novo", () => {
    const tentar = vi.fn();
    render(
      <MemoryRouter>
        <Erro erro="Não deu para ler a resposta." tentarDeNovo={tentar} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert").textContent).toContain("Não deu para ler a resposta.");
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(tentar).toHaveBeenCalledTimes(1);
  });

  it("fora do plano não oferece tentar de novo: o caminho são os planos", () => {
    render(
      <MemoryRouter>
        <Erro erro={new ErroDaApi("plano", "Faz parte de outro plano.")} tentarDeNovo={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Conhecer os planos" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Tentar de novo" })).toBeNull();
  });
});

describe("Selo", () => {
  it("o tom vira classe e o padrão é neutro", () => {
    render(
      <>
        <Selo>Companhia aberta</Selo>
        <Selo tom="alerta">Baixada</Selo>
      </>,
    );
    expect(screen.getByText("Companhia aberta").className).toBe("selo-do-app neutro");
    expect(screen.getByText("Baixada").className).toBe("selo-do-app alerta");
  });

  it.each(["destaque", "bom", "atencao", "alerta"])("o tom %s tem estilo no CSS", (tom) =>
    expect(CSS).toContain(`.selo-do-app.${tom} {`),
  );
});

describe("CartaoDeNumero", () => {
  it("mostra o rótulo, o valor, o detalhe e a fonte", () => {
    const { container } = render(
      <CartaoDeNumero
        rotulo="Empresas ativas"
        valor="1.284"
        detalhe="no setor inventado"
        fonte={<Fonte nome="Receita Federal" data="10/2026" />}
        principal
      />,
    );
    const cartao = container.firstElementChild as HTMLElement;
    expect(cartao.className).toBe("numero-do-painel principal");
    expect(cartao.querySelector(".numero-valor")?.textContent).toBe("1.284");
    expect(cartao.textContent).toContain("Empresas ativas");
    expect(cartao.textContent).toContain("no setor inventado");
    expect(cartao.textContent).toContain("Fonte: Receita Federal · dado de 10/2026");
  });

  it("sem dado, mostra o travessão, nunca um zero", () => {
    const { container } = render(<CartaoDeNumero rotulo="Funcionários" valor={null} />);
    expect(container.querySelector(".numero-valor")?.textContent).toBe("—");
  });
});
