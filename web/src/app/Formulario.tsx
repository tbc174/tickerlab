// Os campos de uma tela, montados a partir do contrato da página (src/paginas.py): nome, tipo,
// limites e padrão vêm de lá, e os valores ficam no endereço (?ticker=PETR4.SA&periodo=1y), como no
// app atual. A taxa livre de risco aparece em "% ao ano" e vai para a API como fração.
import { type FormEvent, useState } from "react";
import { type EntradaDoContrato, conteudoDoApp } from "../conteudo";
import { TICKER_DO_EXEMPLO } from "../site/textos";
import type { Parametros } from "./api";

const NOMES: Record<string, string> = {
  ticker: "Ativo",
  periodo: "Período",
  taxa: "Taxa livre de risco (% ao ano)",
  confianca_do_var: "Confiança do VaR (%)",
  janela: "Janela (dias)",
  materialidade_minima: "Quais acontecimentos mostrar",
};
const PERIODOS: Record<string, string> = { "6mo": "6 meses", "1y": "1 ano", "2y": "2 anos", "5y": "5 anos" };
const CEM = 100;
const LISTA = "lista de textos"; // vários valores do mesmo campo (com=VALE3&com=AAPL)
const { atalhos, padrao: ATALHOS_PADRAO } = conteudoDoApp.comparacao;

/** "VALE3, aapl ,VALE3" → ["VALE3", "AAPL"]: sem vazios nem repetidos. */
export function itensDaLista(texto: string): string[] {
  const itens = texto.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
  return [...new Set(itens)];
}

/** As escolhas de um campo de opção: os períodos, ou as relevâncias da linha do tempo pelo nome. */
function escolhas(e: EntradaDoContrato): { valor: string; nome: string }[] {
  if (e.nome === "materialidade_minima") {
    return conteudoDoApp.linha_do_tempo.relevancias.map((r) => ({ valor: String(r.valor), nome: r.nome }));
  }
  return e.opcoes.map((o) => ({ valor: o, nome: PERIODOS[o] ?? o }));
}

/** O valor de cada campo como texto (o do endereço ou o padrão do contrato). */
export function valoresIniciais(
  entradas: EntradaDoContrato[],
  busca: URLSearchParams,
): Record<string, string> {
  const valores: Record<string, string> = {};
  for (const e of entradas) {
    if (e.tipo === LISTA) {
      const doEndereco = busca.getAll(e.nome);
      const padrao = atalhos.filter((a) => ATALHOS_PADRAO.includes(a.nome)).map((a) => a.ticker);
      valores[e.nome] = (doEndereco.length > 0 ? doEndereco : padrao).join(",");
      continue;
    }
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
    parametros[e.nome] = e.tipo === LISTA ? itensDaLista(texto) : texto;
  }
  return parametros;
}

/** Os valores no endereço da página (a lista vira um parâmetro repetido; vazio fica de fora). */
export function buscaDosValores(
  entradas: EntradaDoContrato[],
  valores: Record<string, string>,
): URLSearchParams {
  const busca = new URLSearchParams();
  for (const [nome, valor] of Object.entries(parametrosDoPedido(entradas, valores))) {
    for (const item of Array.isArray(valor) ? valor : [valor]) {
      if (item !== undefined) busca.append(nome, String(item));
    }
  }
  return busca;
}

/** A lista de ativos da comparação: os atalhos (Ibovespa, S&P 500...) e outros tickers digitados. */
function CampoDeAtivos({ valor, aoMudar }: { valor: string; aoMudar(valor: string): void }) {
  const itens = itensDaLista(valor);
  const tickersDosAtalhos = atalhos.map((a) => a.ticker);
  const outros = itens.filter((t) => !tickersDosAtalhos.includes(t));
  const [textoDosOutros, setTextoDosOutros] = useState(outros.join(", "));
  const juntar = (marcados: string[], texto: string) =>
    aoMudar([...marcados, ...itensDaLista(texto)].join(","));
  const marcados = tickersDosAtalhos.filter((t) => itens.includes(t));
  return (
    <fieldset className="campo-de-ativos">
      <legend>Comparar com</legend>
      {atalhos.map((a) => (
        <label key={a.ticker} className="marcar">
          <input
            type="checkbox"
            checked={marcados.includes(a.ticker)}
            onChange={(ev) =>
              juntar(
                ev.target.checked ? [...marcados, a.ticker] : marcados.filter((t) => t !== a.ticker),
                textoDosOutros,
              )
            }
          />
          {a.nome}
        </label>
      ))}
      <label>
        <span>Outros tickers (separados por vírgula)</span>
        <input
          value={textoDosOutros}
          placeholder="Ex.: VALE3, AAPL"
          maxLength={120}
          onChange={(ev) => {
            setTextoDosOutros(ev.target.value);
            juntar(marcados, ev.target.value);
          }}
        />
      </label>
    </fieldset>
  );
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
      {entradas.map((e) =>
        e.tipo === LISTA ? (
          <CampoDeAtivos key={e.nome} valor={rascunho[e.nome] ?? ""} aoMudar={(v) => mudar(e.nome, v)} />
        ) : (
        <label key={e.nome} title={e.descricao}>
          <span>{NOMES[e.nome] ?? e.nome}</span>
          {e.tipo === "opcao" || e.nome === "materialidade_minima" ? (
            <select value={rascunho[e.nome]} onChange={(ev) => mudar(e.nome, ev.target.value)}>
              {escolhas(e).map((o) => (
                <option key={o.valor} value={o.valor}>
                  {o.nome}
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
        ),
      )}
      <button className="botao primario" type="submit">
        Analisar
      </button>
    </form>
  );
}
