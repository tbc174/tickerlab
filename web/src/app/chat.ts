// A conta do chat na tela "Perguntar" (linha 903), sem React: juntar os eventos da resposta numa troca,
// separar o que a base não tem, montar o histórico que vai de volta ao modelo e resumir as fontes e as
// consultas da conversa. A tela só desenha o que sai daqui.
import { type Bloco, blocosDoMarkdown } from "./Markdown";
import type { ConsultaDoChat, EventoDoChat, FonteDaConsulta } from "./tipos";

export interface Troca {
  id: number;
  pergunta: string;
  texto: string;
  /** Onde começa o texto da volta atual: um "recomeço" descarta só o que veio depois daqui. */
  inicioDaVolta: number;
  /** As consultas em andamento (o evento "ferramenta"); o "fim" traz a lista completa. */
  consultando: { nome: string; titulo: string }[];
  situacao: "respondendo" | "pronta" | "erro";
  comoChegueiAqui: ConsultaDoChat[];
  avisos: string[];
  avisoFinal: string | null;
  erro: string | null;
}

export function trocaNova(id: number, pergunta: string): Troca {
  return {
    id,
    pergunta,
    texto: "",
    inicioDaVolta: 0,
    consultando: [],
    situacao: "respondendo",
    comoChegueiAqui: [],
    avisos: [],
    avisoFinal: null,
    erro: null,
  };
}

const ENTRE_VOLTAS = "\n\n";
const TIPOS = new Set(["ferramenta", "texto", "recomeco", "fim", "erro"]);

/** O evento de uma linha, se tem a forma esperada; linha estranha é ignorada (não derruba a tela). */
export function eventoDaLinha(valor: unknown): EventoDoChat | null {
  if (typeof valor !== "object" || valor === null) return null;
  const tipo = (valor as { tipo?: unknown }).tipo;
  return typeof tipo === "string" && TIPOS.has(tipo) ? (valor as EventoDoChat) : null;
}

/** A troca depois de mais um evento da resposta. */
export function comEvento(troca: Troca, evento: EventoDoChat): Troca {
  switch (evento.tipo) {
    case "ferramenta": {
      // a volta terminou pedindo consultas: o texto dela fica, e a próxima começa num parágrafo novo
      const texto =
        troca.texto.trim() === "" || troca.texto.endsWith(ENTRE_VOLTAS) ? troca.texto : troca.texto + ENTRE_VOLTAS;
      return {
        ...troca,
        texto,
        inicioDaVolta: texto.length,
        consultando: [...troca.consultando, { nome: evento.nome, titulo: evento.titulo }],
      };
    }
    case "texto":
      return { ...troca, texto: troca.texto + evento.texto };
    case "recomeco":
      // a volta recomeçou: o texto parcial dela não vale; o das voltas anteriores fica
      return { ...troca, texto: troca.texto.slice(0, troca.inicioDaVolta) };
    case "fim":
      return {
        ...troca,
        situacao: "pronta",
        consultando: [],
        comoChegueiAqui: evento.como_cheguei_aqui ?? [],
        avisos: evento.avisos ?? [],
        avisoFinal: evento.aviso_final ?? null,
      };
    case "erro":
      return { ...troca, situacao: "erro", consultando: [], erro: evento.mensagem };
  }
}

const TITULO_DAS_LACUNAS = /^o que a base n[aã]o tem/i;
const LACUNA = /^n[aã]o temos\b/i;

/** A resposta em blocos, com o que a base não tem à parte: a seção "O que a base não tem", se o modelo
 * escreveu uma, e os parágrafos que começam por "Não temos" (as instruções pedem esse começo). */
export function separarLacunas(texto: string): { corpo: Bloco[]; lacunas: string[] } {
  const corpo: Bloco[] = [];
  const lacunas: string[] = [];
  let naSecao = false;
  for (const bloco of blocosDoMarkdown(texto)) {
    if (bloco.tipo === "titulo") {
      naSecao = TITULO_DAS_LACUNAS.test(bloco.texto);
      if (!naSecao) corpo.push(bloco);
    } else if (naSecao && bloco.tipo === "paragrafo") {
      lacunas.push(bloco.texto);
    } else if (naSecao && bloco.tipo === "lista") {
      lacunas.push(...bloco.itens);
    } else if (bloco.tipo === "paragrafo" && LACUNA.test(bloco.texto)) {
      lacunas.push(bloco.texto);
    } else {
      corpo.push(bloco);
    }
  }
  return { corpo, lacunas };
}

export interface TrocaAnterior {
  pergunta: string;
  resposta: string;
}

/** As últimas trocas respondidas, que a tela reenvia para o modelo ter o contexto: no máximo `quantas`, cada
 * texto no tamanho que a rota aceita (o servidor ainda corta o total). */
export function historicoParaEnviar(
  trocas: Troca[],
  quantas: number,
  caracteresDaPergunta: number,
  caracteresDaResposta: number,
): TrocaAnterior[] {
  if (quantas <= 0) return [];
  return trocas
    .filter((t) => t.situacao === "pronta" && t.texto.trim() !== "")
    .slice(-quantas)
    .map((t) => ({
      pergunta: t.pergunta.slice(0, caracteresDaPergunta),
      resposta: t.texto.slice(0, caracteresDaResposta),
    }));
}

/** As fontes de todas as consultas da conversa, uma vez cada, com a data mais nova. */
export function fontesDaConversa(trocas: Troca[]): FonteDaConsulta[] {
  const porNome = new Map<string, FonteDaConsulta>();
  for (const troca of trocas) {
    for (const consulta of troca.comoChegueiAqui) {
      for (const fonte of consulta.fontes ?? []) {
        const antiga = porNome.get(fonte.fonte);
        const datas = [antiga?.publicado_em, fonte.publicado_em].filter((d): d is string => Boolean(d)).sort();
        porNome.set(fonte.fonte, {
          fonte: fonte.fonte,
          atribuicao: antiga?.atribuicao ?? fonte.atribuicao,
          licenca: antiga?.licenca ?? fonte.licenca,
          publicado_em: datas.at(-1) ?? null,
        });
      }
    }
  }
  return [...porNome.values()].sort((a, b) => a.fonte.localeCompare(b.fonte));
}

/** As fontes de uma troca só (a linha "Fonte:" embaixo da resposta). */
export function fontesDaTroca(troca: Troca): FonteDaConsulta[] {
  return fontesDaConversa([troca]);
}

/** Quantas vezes cada ferramenta foi chamada na conversa, pelo título, na ordem da primeira chamada. */
export function ferramentasDaConversa(trocas: Troca[]): { titulo: string; vezes: number }[] {
  const vezes = new Map<string, number>();
  for (const troca of trocas) {
    for (const consulta of troca.comoChegueiAqui) vezes.set(consulta.titulo, (vezes.get(consulta.titulo) ?? 0) + 1);
  }
  return [...vezes].map(([titulo, n]) => ({ titulo, vezes: n }));
}

const CNPJ = /^\d{8}(\d{6})?$/;

/** Os CNPJs (ou raízes) que as consultas pediram, sem repetir: o filtro que a ferramenta recebeu. */
export function cnpjsDaConversa(trocas: Troca[]): string[] {
  const vistos = new Set<string>();
  for (const troca of trocas) {
    for (const consulta of troca.comoChegueiAqui) {
      for (const [campo, valor] of Object.entries(consulta.filtros ?? {})) {
        const digitos = String(valor).replace(/\D/g, "");
        if (campo.toLowerCase().includes("cnpj") && CNPJ.test(digitos)) vistos.add(digitos);
      }
    }
  }
  return [...vistos];
}

/** "1234" → "1,2 s"; abaixo de um segundo, em milissegundos. */
export function formatarDuracao(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} s`;
}

/** Os filtros de uma consulta numa linha: "uf: SC · idade_minima: 15". */
export function filtrosEmLinha(filtros: Record<string, string | number | boolean>): string {
  const partes = Object.entries(filtros ?? {}).map(([campo, valor]) => `${campo}: ${String(valor)}`);
  return partes.length > 0 ? partes.join(" · ") : "sem filtros";
}
