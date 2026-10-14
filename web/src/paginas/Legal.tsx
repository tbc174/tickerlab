// Termos de uso e Política de privacidade: o texto de conteudo/*.md, convertido pelo Python.
// Era `legal()` de scripts/gerar_site.py.
import { legal } from "../conteudo";
import { Bruto } from "../site/Bruto";
import { PaginaDeLeitura, ancorarTitulos } from "../site/Leitura";

export const DADOS_DOS_TERMOS = {
  caminho: "/termos.html",
  titulo: "Termos de uso",
  descricao:
    "Os termos de uso do TickerLab, plataforma de inteligência financeira para análise de ações.",
  atual: "/termos.html",
};

export const DADOS_DA_PRIVACIDADE = {
  caminho: "/privacidade.html",
  titulo: "Política de privacidade",
  descricao:
    "Que dados o TickerLab trata, para quê, por quanto tempo e como exportar ou apagar.",
  atual: "/privacidade.html",
};

export function Legal({ titulo, texto }: { titulo: string; texto: keyof typeof legal }) {
  // as seções dos dois textos são h3 (o h2 do Markdown ficou para o título da página)
  const { html, itens } = ancorarTitulos(legal[texto], "h3");
  return (
    <PaginaDeLeitura titulo={titulo} sumario={itens}>
      <Bruto html={html} />
    </PaginaDeLeitura>
  );
}
