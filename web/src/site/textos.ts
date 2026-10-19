// Textos e endereços do site público (eram constantes de scripts/gerar_site.py).

export const URL_DO_SITE = "https://tickerlab.com.br";
export const URL_DO_APP = "https://app.tickerlab.com.br";
export const URL_DO_CODIGO = "https://github.com/tbc174/tickerlab";
export const EMAIL_DE_CONTATO = "contato@tickerlab.com.br";

// Beta fechado: só contas convidadas entram (o aviso aparece no topo da página inicial)
export const BETA_FECHADO = false;
export const TICKER_DO_EXEMPLO = "PETR4.SA";

export const AVISO =
  "Nada aqui é recomendação de investimento. Os dados vêm do Yahoo " +
  "Finance e podem ter atraso ou erros. Rentabilidade passada não garante resultado futuro.";

// a assinatura institucional do manual de identidade
export const ASSINATURA = "Dados auditáveis para quem analisa empresas no Brasil.";

/** Endereço de uma página do app, com os parâmetros na ordem dada (sem codificar, como antes). */
export function linkDoApp(pagina = "", parametros: Record<string, string> = {}): string {
  const consulta = Object.entries(parametros)
    .map(([chave, valor]) => `${chave}=${valor}`)
    .join("&");
  return `${URL_DO_APP}/${pagina}` + (consulta ? `?${consulta}` : "");
}

// --- textos que aparecem em mais de uma página ---------------------------------------------
export const PASSOS: [string, string][] = [
  ["Escolha o que investigar", "Busque por código ou empresa: B3, EUA, índices e cripto."],
  ["Explore os dados", "Gráficos, risco e testes de estratégia no passado, com custos."],
  ["Guarde e compartilhe", "Monte um PDF com as seções que importam e baixe."],
];

export const PUBLICOS: [string, string][] = [
  [
    "Quem está começando",
    "Quer entender uma ação antes de investir, sem jargão. O tutorial guia a primeira " +
      "análise em 2 minutos.",
  ],
  [
    "Quem estuda estratégias",
    "Testa regras de compra e venda com custos, validação fora da amostra e teste " +
      "contra o acaso, e vê quando a estratégia não funciona.",
  ],
  [
    "Quem quer organizar a carteira",
    "Vê concentração, número efetivo de ativos e o comportamento da carteira de hoje no " +
      "passado, comparada ao Ibovespa.",
  ],
];

export const CONFIANCA: [string, string][] = [
  [
    "Dados",
    "Preços diários do Yahoo Finance, ajustados por dividendos e desdobramentos. Não é " +
      "tempo real: os dados podem ter atraso, falhas e ajustes posteriores.",
  ],
  [
    "Carteira B3",
    "A API da Área do Investidor só atende empresas credenciadas. Por isso o caminho é " +
      "a planilha que você mesmo baixa; ela é lida só na memória.",
  ],
  [
    "Privacidade",
    "Login com o Google, com sessão de 30 dias; você exporta ou apaga a sua conta quando quiser. O site não usa " +
      "Google Fonts nem ferramentas de rastreamento.",
  ],
  [
    "Método",
    "A decisão de um dia só vale no dia seguinte (sem olhar o futuro), custos entram em " +
      "todo teste e o app mostra quando algo não funciona.",
  ],
];

export const PERGUNTAS: [string, string][] = [
  [
    "O TickerLab recomenda o que comprar?",
    "Não. O TickerLab mostra o que aconteceu no passado e explica cada " +
      "número. Nada aqui é recomendação de investimento.",
  ],
  [
    "Os preços são em tempo real?",
    "Não. O app usa o histórico diário do Yahoo Finance, que pode ter atraso. Cada " +
      "relatório diz a data e a hora dos dados usados.",
  ],
  [
    "Vocês se conectam à minha conta na B3?",
    "Não. A API da B3 é só para empresas credenciadas. Você envia a planilha de posição " +
      "que baixa na Área do Investidor; ela não fica guardada.",
  ],
  [
    "O que fica guardado sobre mim?",
    "Seu perfil do Google (nome, e-mail), preferências, favoritos, simulações salvas e o " +
      "registro dos relatórios gerados, com o PDF original por 1 ano (menos o de \"Minha carteira\", " +
      "que nunca fica guardado). Detalhes na Política de privacidade.",
  ],
  [
    "Preciso pagar?",
    "Não para começar: o plano Gratuito não pede cartão. Hoje a cobrança dos planos " +
      "pagos está em modo de teste, sem dinheiro real.",
  ],
  [
    "Como apago a minha conta?",
    "Em Minha conta → Meus dados e privacidade: dá para exportar tudo em JSON e apagar a " +
      "conta, o que também encerra a assinatura.",
  ],
];

// --- página inicial v2 (ADR 0065) ----------------------------------------------------------
// de onde vem cada dado, como nas Fontes e metodologia (o nome e o que vem de lá)
export const FONTES_DOS_DADOS: [string, string][] = [
  ["CVM", "documentos e demonstrações"],
  ["SEC", "empresas dos EUA"],
  ["Banco Central", "juros, inflação e câmbio"],
  ["Tesouro dos EUA", "curva de juros"],
  ["Yahoo Finance", "preços, com atraso possível"],
];

// a frase da diferença, em duas partes (a segunda em destaque); o texto final é do Tiago
// (tarefa marketing-frase-diferenca na Central)
export const FRASE_DA_DIFERENCA: [string, string] = [
  "Outros sites mostram os números.",
  "O TickerLab testa se a ideia funciona.",
];

export const PRINCIPIOS: [string, string][] = [
  [
    "Sem olhar o futuro",
    "Cada teste usa só o que se sabia naquele dia, com custos de operação na conta.",
  ],
  [
    "Desconta a sorte",
    "A ficha “Foi sorte?” mostra se um bom resultado resiste quando tiramos o acaso da conta.",
  ],
  [
    "Cada número explicado",
    "Em português, com a fonte, a data e os limites de cada análise. Nada é recomendação.",
  ],
];
