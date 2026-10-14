// O conteúdo que vem do Python (scripts/exportar_conteudo.py): o Python é a fonte da verdade.
import appJson from "../conteudo/app.json";
import marcaJson from "../conteudo/marca.json";
import modulosJson from "../conteudo/modulos.json";
import paginasJson from "../conteudo/paginas.json";
import planosJson from "../conteudo/planos.json";

export interface Funcionalidade {
  nome: string;
  descricao: string;
  pagina_do_app: string | null;
  ticker: string | null;
  disponivel: boolean;
}

export interface Modulo {
  chave: string;
  nome: string;
  objetivo: string;
  frase: string;
  funcionalidades: Funcionalidade[];
}

/** Um campo da tela, com os limites que a rota da API aceita (`Entrada` de src/paginas.py). */
export interface EntradaDoContrato {
  nome: string;
  tipo: string; // "texto", "inteiro", "numero", "opcao", "lista de textos", "objeto" ou "parametros da estrategia"
  descricao: string;
  obrigatoria: boolean;
  padrao: number | string | null;
  minimo: number | null;
  maximo: number | null;
  opcoes: string[];
}

/** O que a tela recebe e qual rota devolve o que ela mostra (`Contrato` de src/paginas.py). */
export interface Contrato {
  metodo: string; // "GET" ou "POST"
  rota: string; // sem o prefixo /api: "/v1/visao-geral"
  entradas: EntradaDoContrato[];
  resposta: string; // o esquema da resposta em src/api_v1/esquemas.py
}

export interface PaginaDoApp {
  chave: string;
  titulo: string;
  url: string;
  grupo: string;
  descricao: string;
  e_pro: boolean;
  no_menu: boolean;
  somente_admin: boolean;
  contrato: Contrato | null; // as páginas que já têm rota na API de leitura
}

export const marca = marcaJson;
export const modulos: Modulo[] = modulosJson;
export const paginasDoApp: PaginaDoApp[] = paginasJson;
export const planos = planosJson;
import siteJson from "../conteudo/site.json";

// o que só o site usa e vem do app: estilos do Report Studio e ativos de exemplo
export const site = siteJson;
import legalJson from "../conteudo/legal.json";
import qualidadeJson from "../conteudo/qualidade.json";
import metodologiaJson from "../conteudo/metodologia.json";
import novidadesJson from "../conteudo/novidades.json";

// os Termos e a Política, já em HTML (convertidos do Markdown de conteudo/ pelo Python)
export const legal = legalJson;
// o selo "dado em conferência" e as regras fixas, com os mesmos textos do app
export const qualidade = qualidadeJson;
// padrões por setor, notas e fórmulas do relatório de empresa (src/metodologia_das_notas.py)
export const metodologia = metodologiaJson;

/** Uma atualização do TickerLab (`Atualizacao` de src/novidades.py), da mais nova à mais velha. */
export interface Atualizacao {
  data: string; // AAAA-MM-DD
  titulo: string;
  resumo: string;
  novidades: string[];
  correcoes: string[];
}
export const novidades: Atualizacao[] = novidadesJson;

// --- o que só o app em React usa (scripts/exportar_conteudo.py, função _app) ---

/** Um número do painel da visão geral (`ItemDoPainel` de src/analises.py). */
export interface ItemDoPainel {
  campo: string;
  rotulo: string; // pode ter {data} e {confianca}
  termo: string; // do glossário
  formato: string; // "pct", "pct_com_sinal" ou "decimal"
  grupo: string;
  campo_da_data: string | null;
}

/** Um parágrafo do "?" de um termo: "O que é", "Exemplo", "Cuidado"... (sem Markdown). */
export interface ParteDaAjuda {
  rotulo: string | null;
  texto: string;
}

export const conteudoDoApp: {
  painel: { itens: ItemDoPainel[]; legenda: string; frase_do_cvar: string };
  glossario: Record<string, ParteDaAjuda[]>;
  juros: { termos: Record<string, string>; fonte_focus: string; nota_do_focus: string };
  linha_do_tempo: { relevancias: { nome: string; valor: number }[]; padrao: number };
  retorno_mensal: { meses: string[]; legenda: string };
  backtest: {
    estrategias: {
      nome: string;
      grupo: string;
      parametros: {
        nome: string;
        rotulo: string;
        padrao: number | string;
        minimo: number | null;
        maximo: number | null;
        passo: number;
        ajuda: string;
        opcoes: string[];
      }[];
    }[];
    metricas_por_formato: Record<string, string[]>;
    ficha: { termo: string; termo_da_tolerancia: string; explicacao: string };
  };
  comparacao: {
    atalhos: { nome: string; ticker: string }[];
    padrao: string[];
    max_ativos: number;
    colunas: { rotulo: string; formato: string }[];
    aviso_do_limite: string;
    aviso_sem_dados: string;
  };
} = appJson;
