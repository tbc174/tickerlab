// O pregão mais novo, no navegador. O HTML do site sai com o último pregão guardado no repositório
// (funciona sem JavaScript); o ferramentas.js pede à API o último que o servidor de casa mandou
// (/v1/estudos/pregao/ultimo, src/api_v1/estudos.py) e, se ele for mais novo e do molde aprovado
// que está no HTML, troca a data e o corpo. Qualquer falha deixa a página como veio: nunca some o
// texto, e a data no título é sempre a do pregão mostrado.
import { createRoot } from "react-dom/client";
import { CorpoDoPregao, dataDoPregao, type TextoDoPregao } from "./CorpoDoPregao";
import { URL_DO_APP } from "./textos";

export const ENDERECO_DO_PREGAO = `${URL_DO_APP}/api/v1/estudos/pregao/ultimo`;
const TEMPO_LIMITE = 12_000;
const DATA_ISO = /^\d{4}-\d{2}-\d{2}$/;

const ehTexto = (x: unknown): x is string => typeof x === "string";
const listaDeTextos = (x: unknown): x is string[] => Array.isArray(x) && x.every(ehTexto);
const objeto = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null;

function tabelaValida(x: unknown): boolean {
  return (
    objeto(x) &&
    ehTexto(x.chave) &&
    ehTexto(x.titulo) &&
    listaDeTextos(x.colunas) &&
    Array.isArray(x.linhas) &&
    x.linhas.every(listaDeTextos)
  );
}

/** O texto que a API devolveu, se tem a forma da página e é do molde aprovado; senão, nada. */
export function lerPregao(corpo: unknown, moldeAprovado: string): TextoDoPregao | null {
  if (!objeto(corpo) || corpo.molde_aprovado !== moldeAprovado || !objeto(corpo.pregao)) return null;
  const p = corpo.pregao;
  const grafico = p.grafico;
  const valido =
    p.impressao_digital === moldeAprovado &&
    ehTexto(p.pregao) &&
    DATA_ISO.test(p.pregao) &&
    Array.isArray(p.frases) &&
    p.frases.length > 0 &&
    p.frases.every((f) => objeto(f) && ehTexto(f.texto)) &&
    objeto(grafico) &&
    ehTexto(grafico.titulo) &&
    Array.isArray(grafico.barras) &&
    grafico.barras.every((b) => objeto(b) && ehTexto(b.nome) && typeof b.valor === "number" && ehTexto(b.texto)) &&
    Array.isArray(p.tabelas) &&
    p.tabelas.length > 0 &&
    p.tabelas.every(tabelaValida) &&
    listaDeTextos(p.limites) &&
    p.limites.length > 0 &&
    listaDeTextos(p.fontes);
  return valido ? (p as unknown as TextoDoPregao) : null;
}

async function pedirUltimo(buscar: typeof fetch): Promise<unknown> {
  const controle = new AbortController();
  const prazo = setTimeout(() => controle.abort(), TEMPO_LIMITE);
  try {
    const resposta = await buscar(ENDERECO_DO_PREGAO, { credentials: "omit", signal: controle.signal });
    return resposta.ok ? await resposta.json() : null;
  } catch {
    return null;
  } finally {
    clearTimeout(prazo);
  }
}

/** Troca a data (e, na página do pregão, o corpo) pelo pregão mais novo da API; diz se trocou. */
export async function ligarPregao(raiz: ParentNode = document, buscar: typeof fetch = fetch): Promise<boolean> {
  const datas = [...raiz.querySelectorAll<HTMLElement>("[data-pregao-do-dia]")];
  const atual = datas[0]?.dataset.pregaoDoDia;
  const molde = datas[0]?.dataset.moldeAprovado;
  if (!atual || !molde) return false;
  const novo = lerPregao(await pedirUltimo(buscar), molde);
  // datas ISO comparam como texto; o mesmo dia ou um mais velho não muda nada
  if (!novo || novo.pregao <= atual) return false;
  const corpo = raiz.querySelector<HTMLElement>("[data-corpo-do-pregao]");
  if (corpo) createRoot(corpo).render(<CorpoDoPregao pregao={novo} />);
  for (const data of datas) {
    data.textContent = dataDoPregao(novo.pregao);
    data.dataset.pregaoDoDia = novo.pregao;
  }
  return true;
}
