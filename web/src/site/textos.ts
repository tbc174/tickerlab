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
// O caminho de um número até o relatório (página "Como funciona"): fonte, original com hash, versões,
// porta e relatório. O terceiro item de cada passo é a explicação técnica, que vai recolhida em
// "Como foi calculado" (ADR 0099, item 7).
export const PASSOS: [string, string, string][] = [
  [
    "A fonte",
    "Coletamos de órgãos públicos, como a CVM, a B3, o Banco Central e a SEC. Cada tabela da base diz de qual fonte vem e com que licença.",
    "A coleta lê o que o órgão publica e anota a hora em que leu. A licença é a que a própria fonte publica; onde ela ainda não respondeu por escrito sobre uso comercial, a página Dados avisa.",
  ],
  [
    "O original, com hash",
    "Guardamos o arquivo exatamente como veio e registramos o SHA-256 dele: quem quiser confere que nada foi mexido.",
    "O hash SHA-256 é calculado sobre os bytes do arquivo no momento da coleta. O mesmo arquivo dá sempre o mesmo hash, e qualquer alteração, mesmo de uma vírgula, muda o resultado.",
  ],
  [
    "As versões",
    "Quando a fonte corrige um dado, a correção entra como versão nova, com a data em que a vimos. A anterior não é apagada.",
    "Cada versão guarda a data em que o dado ficou público e a data em que o TickerLab o viu. Por isso é possível perguntar “como era em tal dia”, com o que se sabia então.",
  ],
  [
    "A porta",
    "Os dados da base são consultados por data: a consulta só enxerga o que já era público naquele dia. A API aberta, para consultar de fora, está em construção.",
    "Um dado só é usado a partir do dia em que ficou público. Cortar o futuro não muda o passado: há teste automático que confere isso em cada versão do código.",
  ],
  [
    "O relatório",
    "O PDF junta os números, cada um com a fonte e a data, e diz o que não foi achado. A seção “Limites e cuidados” é obrigatória.",
    "As contas ficam recolhidas em “Como foi calculado”: quem quer conferir abre, quem só quer o resultado não é atrapalhado. Os mesmos cálculos valem para a tela e para o PDF.",
  ],
];

export const PUBLICOS: [string, string][] = [
  [
    "Quem analisa empresas",
    "Analistas e equipes de análise que conferem o que uma empresa e o grupo dela dizem contra as bases públicas, com a data de cada fonte e o que não foi achado.",
  ],
  [
    "Estudantes e pesquisadores",
    "Querem um número que possam citar: fonte, data e versão em cada um, e o teste de estratégia mostra também quando a estratégia não funciona.",
  ],
  [
    "Equipes",
    "O plano Casa, por assento, para quem analisa junto. Ainda está em construção: conte para a gente o que a sua equipe precisa.",
  ],
];

export const CONFIANCA: [string, string][] = [
  [
    "Dados",
    "Documentos oficiais da CVM, da B3, do Banco Central e da SEC, cada um com fonte, data e licença. Os preços diários vêm do Yahoo Finance, ajustados por dividendos e desdobramentos; não são tempo real e podem ter atraso, falhas e ajustes posteriores.",
  ],
  [
    "Original e versões",
    "O arquivo da fonte é guardado como veio, com o hash. Quando a fonte corrige um dado, a correção vira versão nova: nada é sobrescrito.",
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
    "O TickerLab diz o que comprar?",
    "Não. O TickerLab mostra o que aconteceu e explica cada " +
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

// --- as quatro regras que valem para toda tabela da base (página inicial e Dados) -----------
export const REGRAS_DA_BASE: [string, string][] = [
  [
    "Como era na data",
    "Guardamos o que estava público em cada dia, não só o valor de hoje. Uma consulta a uma data " +
      "nunca enxerga o que só ficou público depois dela.",
  ],
  [
    "Linhagem",
    "Cada tabela diz de qual fonte vem, qual versão do contrato a descreve e desde quando há histórico.",
  ],
  [
    "Licença por tabela",
    "Cada tabela leva a licença da sua fonte e diz o que pode ser repassado. Onde ainda não há " +
      "resposta escrita da fonte, a página avisa.",
  ],
  [
    "Explicação",
    "O que cada dado é e como foi calculado vem escrito em português e recolhido: quem quer " +
      "conferir abre, quem só quer o resultado não é atrapalhado.",
  ],
];
