// Os campos de uma tela, montados a partir do contrato da página (src/paginas.py): nome, tipo,
// limites e padrão vêm de lá, e os valores ficam no endereço (?ticker=PETR4.SA&periodo=1y), como no
// app atual. A taxa livre de risco aparece em "% ao ano" e vai para a API como fração.
import { type FormEvent, useState } from "react";
import type { EntradaDoContrato } from "../conteudo";
import { TICKER_DO_EXEMPLO } from "../site/textos";
import type { Parametros } from "./api";

const NOMES: Record<string, string> = {
  ticker: "Ativo",
  periodo: "Período",
  taxa: "Taxa livre de risco (% ao ano)",
  confianca_do_var: "Confiança do VaR (%)",
  janela: "Janela (dias)",
  materialidade_minima: "Relevância mínima (0 a 100)",
};
const PERIODOS: Record<string, string> = { "6mo": "6 meses", "1y": "1 ano", "2y": "2 anos", "5y": "5 anos" };
const CEM = 100;

/** O valor de cada campo como texto (o do endereço ou o padrão do contrato). */
export function valoresIniciais(
  entradas: EntradaDoContrato[],
  busca: URLSearchParams,
): Record<string, string> {
  const valores: Record<string, string> = {};
  for (const e of entradas) {
    const doEndereco = busca.get(e.nome);
    if (doEndereco !== null) valores[e.nome] = doEndereco;
    else if (e.nome === "ticker") valores[e.nome] = TICKER_DO_EXEMPLO;
    else valores[e.nome] = e.padrao === null ? "" : String(e.padrao);
  }
  return valores;
}

/** Os parâmetros do pedido à API, na ordem do contrato; campo vazio e opcional fica de fora. */
export function parametrosDoPedido(
  entradas: EntradaDoContrato[],
  valores: Record<string, string>,
): Parametros {
  const parametros: Parametros = {};
  for (const e of entradas) {
    const texto = (valores[e.nome] ?? "").trim();
    if (texto === "") continue;
    parametros[e.nome] = texto;
  }
  return parametros;
}

/** A taxa do endereço (fração) vira "% ao ano" no campo, e volta a ser fração no pedido. */
export const taxaParaOCampo = (fracao: string) =>
  fracao === "" ? "" : String(Number((Number(fracao) * CEM).toPrecision(12)));
export const taxaDoCampo = (percentual: string) =>
  percentual.trim() === "" ? "" : String(Number((Number(percentual.replace(",", ".")) / CEM).toPrecision(12)));

interface Propriedades {
  entradas: EntradaDoContrato[];
  valores: Record<string, string>;
  aoAnalisar(valores: Record<string, string>): void;
}

export function Formulario({ entradas, valores, aoAnalisar }: Propriedades) {
  const [rascunho, setRascunho] = useState<Record<string, string>>(() => ({
    ...valores,
    ...(valores.taxa !== undefined ? { taxa: taxaParaOCampo(valores.taxa) } : {}),
  }));
  const mudar = (nome: string, valor: string) => setRascunho((r) => ({ ...r, [nome]: valor }));
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    aoAnalisar({
      ...rascunho,
      ...(rascunho.taxa !== undefined ? { taxa: taxaDoCampo(rascunho.taxa) } : {}),
    });
  };
  return (
    <form className="formulario-do-app" onSubmit={enviar}>
      {entradas.map((e) => (
        <label key={e.nome} title={e.descricao}>
          <span>{NOMES[e.nome] ?? e.nome}</span>
          {e.tipo === "opcao" ? (
            <select value={rascunho[e.nome]} onChange={(ev) => mudar(e.nome, ev.target.value)}>
              {e.opcoes.map((o) => (
                <option key={o} value={o}>
                  {PERIODOS[o] ?? o}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={rascunho[e.nome] ?? ""}
              onChange={(ev) => mudar(e.nome, ev.target.value)}
              required={e.obrigatoria}
              inputMode={e.tipo === "texto" ? "text" : "decimal"}
              placeholder={e.nome === "taxa" ? "vazio = CDI do período" : undefined}
              {...(e.tipo === "inteiro" && e.minimo !== null ? { min: e.minimo } : {})}
              {...(e.tipo === "inteiro" && e.maximo !== null ? { max: e.maximo } : {})}
              type={e.tipo === "inteiro" ? "number" : "text"}
              maxLength={e.tipo === "texto" ? 20 : undefined}
            />
          )}
        </label>
      ))}
      <button className="botao primario" type="submit">
        Analisar
      </button>
    </form>
  );
}
