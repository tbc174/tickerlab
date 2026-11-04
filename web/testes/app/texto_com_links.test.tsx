// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TextoComLinks } from "../../src/app/TextoComLinks";

afterEach(cleanup);

describe("TextoComLinks", () => {
  it("vira link numa aba nova só o endereço https://, sem a pontuação do fim", () => {
    const { container } = render(
      <TextoComLinks texto="DFP entregue à CVM — DFP: https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp; ITR: https://dados.cvm.gov.br/." />,
    );
    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp",
      "https://dados.cvm.gov.br/",
    ]);
    for (const a of links) {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toBe("noopener noreferrer");
    }
    expect(container.textContent).toContain("DFP entregue à CVM — DFP: ");
    expect(container.textContent?.endsWith(".")).toBe(true);
  });

  it("outro esquema continua texto", () => {
    render(<TextoComLinks texto="http://x.com/a javascript:alert(1) ftp://y.com" />);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});
