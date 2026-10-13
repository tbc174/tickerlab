// Termos de uso e Política de privacidade: o texto de conteudo/*.md, convertido pelo Python.
// Era `legal()` de scripts/gerar_site.py.
import { legal } from "../conteudo";
import { Bruto } from "../site/Bruto";

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
  return (
    <section className="faixa secao estreita texto-longo">
      <h1>{titulo}</h1>
      <Bruto html={legal[texto]} />
    </section>
  );
}
