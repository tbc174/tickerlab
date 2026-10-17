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
  pagina_do_site: string | null; // as ferramentas grátis ficam no site, não no app
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

// o que só o site usa e vem do app: estilos do Report Studio, ativos de exemplo e a fita da inicial
export const site = siteJson;
import exemploJson from "../conteudo/exemplo.json";

/** Um número do painel: o valor (para a cor) e o texto como o PDF mostra ("▲ +545,8%"). */
export interface NumeroDoPainel {
  valor: number;
  texto: string;
}

/** O painel da página inicial: os números do PDF de exemplo (painel_de_exemplo no Python). */
export const exemplo: {
  ticker: string;
  codigo: string;
  inicio: string; // AAAA-MM-DD
  fim: string;
  retorno_total: NumeroDoPainel;
  retorno_ao_ano: NumeroDoPainel;
  maior_queda: NumeroDoPainel;
  volatilidade: NumeroDoPainel;
  sharpe: NumeroDoPainel;
  serie: number[]; // preço em base 100
} = exemploJson;
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
  entrada: { aviso: string };
  assinatura: { retorno_ok: string; retorno_cancelado: string };
  aceite: {
    versao: string;
    titulo: string;
    introducao: string;
    caixa: string;
    sem_o_aceite: { titulo: string; explicacao: string };
    novidades: { texto: string; versao: string };
  };
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

import regrasDeImpostoJson from "../conteudo/regras_de_imposto.json";

/** Uma regra de imposto com a fonte oficial (src/regras_de_imposto.py). */
export interface RegraDeImposto {
  chave: string;
  descricao: string;
  valor: number | string;
  fonte: string;
  onde: string;
  conferida_em: string;
}

// as regras de imposto das ferramentas (DARF, renda fixa), com fonte e data
export const regrasDeImposto: {
  regras: RegraDeImposto[];
  renda_fixa: { ate_dias: number | null; aliquota: number }[];
  iof: number[]; // a fração do rendimento do 1º ao 29º dia (Decreto 6.306/2007, anexo)
  custodia_do_tesouro: { taxa: number; isento_no_selic_ate: number };
  fundos: { come_cotas_longo: number; come_cotas_curto: number; curto_prazo: { ate_dias: number; aliquotas: number[] } };
} = regrasDeImpostoJson;
import amostraJson from "../conteudo/amostra_relatorio.json";

/** Uma tabela da amostra, já escrita: colunas, linhas e, quando há, o link de cada linha. */
export interface TabelaDaAmostra {
  chave: string;
  titulo: string;
  colunas: string[];
  linhas: string[][];
  links: string[];
}

/** A amostra aberta do relatório da base (src/amostra_do_relatorio.py, para_o_site). */
export const amostraRelatorio: {
  empresa: string;
  razao_social: string;
  cnpj: string;
  ticker: string;
  setor: string;
  dados_de: string; // DD/MM/AAAA
  pdf: string;
  aviso: string;
  destaques: {
    chave: string;
    titulo: string;
    texto: string;
    fonte: string;
    data: string;
    secao: string;
    link: string;
  }[];
  secoes: {
    chave: string;
    titulo: string;
    itens: { nome: string; texto: string; base: string }[];
    paragrafos: string[];
    tabelas: TabelaDaAmostra[];
  }[];
  limites: string[];
  fontes: string[];
} = amostraJson;
