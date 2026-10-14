// Os campos de uma tela, montados a partir do contrato da página (src/paginas.py): nome, tipo,
// limites e padrão vêm de lá, e os valores ficam no endereço (?ticker=PETR4.SA&periodo=1y), como no
// app atual. A taxa livre de risco e o custo por operação aparecem em % e vão para a API como fração.
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
  estrategia: "Estratégia",
  custo_por_operacao: "Custo por operação (%)",
};
const PERIODOS: Record<string, string> = { "6mo": "6 meses", "1y": "1 ano", "2y": "2 anos", "5y": "5 anos" };
const CEM = 100;
const LISTA = "lista de textos"; // vários valores do mesmo campo (com=VALE3&com=AAPL)
const OBJETO = "objeto"; // os parâmetros da estratégia, no endereço como p.curta=20
const PREFIXO_DO_PARAMETRO = "p.";
const EM_PORCENTAGEM = new Set(["taxa", "custo_por_operacao"]); // fração na API, % no campo
const { atalhos, padrao: ATALHOS_PADRAO } = conteudoDoApp.comparacao;
const { estrategias } = conteudoDoApp.backtest;
const GRUPOS = [...new Set(estrategias.map((e) => e.grupo))];

/** "VALE3, aapl ,VALE3" → ["VALE3", "AAPL"]: sem vazios nem repetidos. */
export function itensDaLista(texto: string): string[] {
  const itens = texto.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
  return [...new Set(itens)];
}

const lerObjeto = (texto: string): Record<string, string> => (texto ? JSON.parse(texto) : {});

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
    if (e.tipo === OBJETO) {
      const doEndereco = [...busca.entries()]
        .filter(([nome]) => nome.startsWith(PREFIXO_DO_PARAMETRO))
        .map(([nome, valor]) => [nome.slice(PREFIXO_DO_PARAMETRO.length), valor]);
      valores[e.nome] = JSON.stringify(Object.fromEntries(doEndereco));
      continue;
    }
    const doEndereco = busca.get(e.nome);
    if (doEndereco !== null) valores[e.nome] = doEndereco;
    else if (e.nome === "ticker") valores[e.nome] = TICKER_DO_EXEMPLO;
    else if (e.nome === "estrategia") valores[e.nome] = estrategias[0].nome;
    else valores[e.nome] = e.padrao === null ? "" : String(e.padrao);
  }
  return valores;
}

/** Os parâmetros de um pedido GET, na ordem do contrato; campo vazio e opcional fica de fora. */
export function parametrosDoPedido(
  entradas: EntradaDoContrato[],
  valores: Record<string, string>,
): Parametros {
  const parametros: Parametros = {};
  for (const e of entradas) {
    const texto = (valores[e.nome] ?? "").trim();
    if (texto === "" || e.tipo === OBJETO) continue;
    parametros[e.nome] = e.tipo === LISTA ? itensDaLista(texto) : texto;
  }
  return parametros;
}

/** O parâmetro de estratégia com o tipo certo: escolha fica texto, o resto vira número. */
function valorDoParametro(estrategia: string, nome: string, texto: string): string | number {
  const definicao = estrategias.find((e) => e.nome === estrategia)?.parametros.find((p) => p.nome === nome);
  return definicao && definicao.opcoes.length === 0 ? Number(texto.replace(",", ".")) : texto;
}

/** O corpo de um pedido POST (o backtest): números como números, os parâmetros como objeto. */
export function corpoDoPedido(
  entradas: EntradaDoContrato[],
  valores: Record<string, string>,
): Record<string, unknown> {
  const corpo: Record<string, unknown> = {};
  for (const e of entradas) {
    const texto = (valores[e.nome] ?? "").trim();
    if (texto === "") continue;
    if (e.tipo === OBJETO) {
      const estrategia = valores.estrategia ?? "";
      corpo[e.nome] = Object.fromEntries(
        Object.entries(lerObjeto(texto)).map(([nome, v]) => [nome, valorDoParametro(estrategia, nome, v)]),
      );
    } else if (e.tipo === "numero" || e.tipo === "inteiro") corpo[e.nome] = Number(texto);
    else corpo[e.nome] = e.tipo === LISTA ? itensDaLista(texto) : texto;
  }
  return corpo;
}

/** Os valores no endereço da página (lista e parâmetros viram vários; vazio fica de fora). */
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
  for (const e of entradas.filter((e) => e.tipo === OBJETO)) {
    for (const [nome, valor] of Object.entries(lerObjeto(valores[e.nome] ?? ""))) {
      busca.append(`${PREFIXO_DO_PARAMETRO}${nome}`, valor);
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

/** Os parâmetros da estratégia escolhida, com os limites e a ajuda de src/estrategias.py. */
function CamposDaEstrategia(props: { estrategia: string; valor: string; aoMudar(valor: string): void }) {
  const definicao = estrategias.find((e) => e.nome === props.estrategia);
  if (!definicao || definicao.parametros.length === 0) return null;
  const valores = lerObjeto(props.valor);
  const mudar = (nome: string, valor: string) => props.aoMudar(JSON.stringify({ ...valores, [nome]: valor }));
  return (
    <fieldset className="campo-de-ativos">
      <legend>Ajustes da estratégia</legend>
      {definicao.parametros.map((p) => (
        <label key={p.nome} title={p.ajuda}>
          <span>{p.rotulo}</span>
          {p.opcoes.length > 0 ? (
            <select value={valores[p.nome] ?? String(p.padrao)} onChange={(ev) => mudar(p.nome, ev.target.value)}>
              {p.opcoes.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          ) : (
            <input
              type="number"
              value={valores[p.nome] ?? String(p.padrao)}
              onChange={(ev) => mudar(p.nome, ev.target.value)}
              {...(p.minimo !== null ? { min: p.minimo } : {})}
              {...(p.maximo !== null ? { max: p.maximo } : {})}
              step={p.passo}
            />
          )}
        </label>
      ))}
    </fieldset>
  );
}

/** Os padrões de uma estratégia, para os campos começarem preenchidos ao trocar de estratégia. */
const padroesDa = (nome: string) =>
  JSON.stringify(
    Object.fromEntries((estrategias.find((e) => e.nome === nome)?.parametros ?? []).map((p) => [p.nome, String(p.padrao)])),
  );

/** Fração do endereço → "% " no campo, e de volta (10 → 0.1; "0,05" → 0.0005). */
export const paraOCampo = (fracao: string) =>
  fracao === "" ? "" : String(Number((Number(fracao) * CEM).toPrecision(12))).replace(".", ",");
export const doCampo = (percentual: string) =>
  percentual.trim() === "" ? "" : String(Number((Number(percentual.replace(",", ".")) / CEM).toPrecision(12)));

function converter(valores: Record<string, string>, conversao: (v: string) => string) {
  return Object.fromEntries(
    Object.entries(valores).map(([nome, v]) => [nome, EM_PORCENTAGEM.has(nome) ? conversao(v) : v]),
  );
}

interface Propriedades {
  entradas: EntradaDoContrato[];
  valores: Record<string, string>;
  aoAnalisar(valores: Record<string, string>): void;
}

export function Formulario({ entradas, valores, aoAnalisar }: Propriedades) {
  const [rascunho, setRascunho] = useState<Record<string, string>>(() => converter(valores, paraOCampo));
  const mudar = (nome: string, valor: string) => setRascunho((r) => ({ ...r, [nome]: valor }));
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    aoAnalisar(converter(rascunho, doCampo));
  };
  return (
    <form className="formulario-do-app" onSubmit={enviar}>
      {entradas.map((e) => {
        if (e.tipo === LISTA) {
          return <CampoDeAtivos key={e.nome} valor={rascunho[e.nome] ?? ""} aoMudar={(v) => mudar(e.nome, v)} />;
        }
        if (e.tipo === OBJETO) {
          return (
            <CamposDaEstrategia
              key={e.nome}
              estrategia={rascunho.estrategia ?? ""}
              valor={rascunho[e.nome] ?? ""}
              aoMudar={(v) => mudar(e.nome, v)}
            />
          );
        }
        return (
          <label key={e.nome} title={e.descricao}>
            <span>{NOMES[e.nome] ?? e.nome}</span>
            {e.nome === "estrategia" ? (
              <select
                value={rascunho.estrategia}
                onChange={(ev) => setRascunho((r) => ({ ...r, estrategia: ev.target.value, parametros: padroesDa(ev.target.value) }))}
              >
                {GRUPOS.map((grupo) => (
                  <optgroup key={grupo} label={grupo}>
                    {estrategias
                      .filter((s) => s.grupo === grupo)
                      .map((s) => (
                        <option key={s.nome}>{s.nome}</option>
                      ))}
                  </optgroup>
                ))}
              </select>
            ) : e.tipo === "opcao" || e.nome === "materialidade_minima" ? (
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
        );
      })}
      <button className="botao primario" type="submit">
        Analisar
      </button>
    </form>
  );
}
