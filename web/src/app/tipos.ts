// O formato das respostas da API (src/api_v1/esquemas.py e rotas.py). Escritos à mão, com teste que
// confere cada um contra docs/api/openapi-v1.json (testes/app/api.test.ts).

export interface LimitesV1 {
  simulacoes: number | null; // null = sem limite
  favoritos: number;
  ativos_na_carteira: number;
  relatorios_por_dia: number | null;
  recursos: string[];
}

/** Quem está logado: só o necessário para a tela (sem e-mail). */
export interface EuV1 {
  nome: string | null;
  plano: string;
  administrador: boolean;
  limites: LimitesV1;
}

/** Uma série ao longo do tempo (datas "AAAA-MM-DD"; null onde não há valor). */
export interface CurvaV1 {
  datas: string[];
  valores: (number | null)[];
}

/** O ativo e o período analisados, de onde vieram os preços e a taxa usada. */
export interface AtivoV1 {
  ticker: string; // o símbolo dos dados (^BVSP): é o que volta para a API
  codigo: string; // o que a tela mostra (IBOV, PETR4)
  periodo: string;
  inicio: string;
  fim: string;
  origem: string; // "atual", "cache_antigo" ou "exemplo"
  taxa_livre_de_risco: number;
  taxa_do_cdi: boolean;
  aviso_da_origem: string | null;
}

/** Os números da visão geral (frações: 0.12 = 12%). */
export interface PainelDeNumerosV1 {
  retorno_total: number | null;
  retorno_anualizado: number | null;
  volatilidade_anual: number | null;
  maior_queda: number | null;
  sharpe: number | null;
  data_do_melhor_dia: string;
  melhor_dia: number | null;
  data_do_pior_dia: string;
  pior_dia: number | null;
  dias_de_alta: number | null;
  confianca_do_var: number;
  var: number | null;
  cvar: number | null;
}

export interface VisaoGeralV1 {
  ativo: AtivoV1;
  painel: PainelDeNumerosV1;
  curva: CurvaV1; // o fechamento em base 100
  motivo_sem_anualizar: string | null;
}

/** Um número de Juros e inflação, com o texto e a legenda prontos (src/juros_e_inflacao.py). */
export interface NumeroDeJurosV1 {
  nome: string;
  valor: number | null;
  texto: string; // como a tela mostra ("15,00% ao ano", "—")
  unidade: string;
  referencia: string | null;
  referencia_mensal: boolean;
  divulgado_em: string | null;
  fonte: string;
  legenda: string; // referência, divulgação e fonte
}

export interface ExpectativaV1 {
  indicador: string; // "IPCA" ou "Selic"
  ano: number;
  mediana: number; // %
  pesquisa: string | null;
}

export interface PontoMensalV1 {
  mes: string; // primeiro dia do mês
  selic_meta: number | null; // % ao ano
  ipca_12_meses: number | null; // %
}

export interface JurosEInflacaoV1 {
  dia: string;
  numeros: NumeroDeJurosV1[];
  expectativas: ExpectativaV1[];
  historico: PontoMensalV1[];
  avisos: string[];
}

/** Um documento na linha do tempo e o ponto da curva (base 100) onde ele fica. */
export interface MarcoV1 {
  data: string;
  dia_no_grafico: string;
  valor_no_grafico: number;
  rotulo: string;
  tema: string;
  materialidade: number;
  assunto: string;
  descricao: string; // "dd/mm/aaaa · tipo: assunto"
  link: string; // vazio: sem link seguro
  topico: string; // o assunto do fato relevante (leitor v2): código; vazio se não há
  topico_nome: string; // o mesmo, em português ("Aquisição")
}

export interface LinhaDoTempoV1 {
  curva: CurvaV1;
  marcos: MarcoV1[];
  fora_do_grafico: number;
  aviso: string;
  sem_acontecimentos: string | null;
  texto_fora_do_grafico: string | null;
}

export interface LinhaDoTempoDoAtivoV1 {
  ativo: AtivoV1;
  linha_do_tempo: LinhaDoTempoV1;
}

export interface PiorQuedaV1 {
  queda: number | null;
  data_topo: string | null;
  data_fundo: string | null;
  data_recuperacao: string | null;
}

/** A queda desde o topo dia a dia (frações, nunca positivas) e a volatilidade móvel. */
export interface RiscoV1 {
  drawdown: CurvaV1;
  pior_queda: PiorQuedaV1;
  janela: number;
  volatilidade_movel: CurvaV1;
  frase_da_pior_queda: string;
  aviso_da_janela: string | null;
}

export interface RiscoDoAtivoV1 {
  ativo: AtivoV1;
  risco: RiscoV1;
}

export interface MesV1 {
  mes: string; // "2024-03"
  retorno: number | null;
}

export interface AnoV1 {
  ano: number;
  meses: (number | null)[]; // janeiro a dezembro
  total: number | null;
}

export interface RetornoMensalV1 {
  meses: MesV1[];
  tabela: AnoV1[];
  melhor: MesV1;
  pior: MesV1;
  meses_de_alta: number | null;
  media_por_mes: (number | null)[];
}

export interface RetornoMensalDoAtivoV1 {
  ativo: AtivoV1;
  retorno_mensal: RetornoMensalV1;
}

export interface LinhaDaComparacaoV1 {
  ticker: string;
  codigo: string;
  retorno_total: number | null;
  retorno_anualizado: number | null;
  volatilidade_anual: number | null;
  maior_queda: number | null;
  sharpe: number | null;
}

export interface ComparacaoV1 {
  dias_em_comum: number;
  dias_descartados: number;
  curvas: Record<string, CurvaV1> | null;
  tabela: LinhaDaComparacaoV1[] | null;
  nota: string | null;
  aviso: string | null;
}

export interface ComparacaoDoAtivoV1 {
  ativo: AtivoV1;
  comparacao: ComparacaoV1;
  sem_dados: string[];
}

/** As métricas (na ordem da tela), a curva de capital em base 100 e quantas operações houve. */
export interface BacktestV1 {
  metricas: Record<string, number | null>;
  curva_de_capital: CurvaV1;
  operacoes: number;
}

export interface LinkV1 {
  id: string;
  titulo: string;
  situacao: string; // "ativo", "vencido" ou "revogado"
  descricao: string;
}

export interface MeusLinksV1 {
  explicacao: string;
  sem_links: string;
  links: LinkV1[];
}

export interface MeuPlanoV1 {
  plano: string;
  nome_do_plano: string;
  simulacoes: string; // "1 de 5", "0 de ilimitadas" ou "—"
  favoritos: string;
  frase_da_assinatura: string | null;
  aviso: string;
  tabela: Record<string, string>[]; // uma linha por recurso: {Recurso, Gratuito, Plus, Pro}
  acao: string | null; // "assinar", "gerenciar" ou null (nenhum botão)
  texto_da_acao: string | null;
  nota_do_cartao: string;
}

export interface ChecagemV1 {
  pergunta: string;
  situacao: string; // "passou", "não passou", "não se aplica" ou "não deu para medir"
  explicacao: string;
}

export interface VereditoV1 {
  resultado: string; // "passou", "não passou" ou "inconclusivo"
  titulo: string;
  texto: string;
}

export interface FichaV1 {
  veredito: VereditoV1;
  checagens: ChecagemV1[];
  tentativas: number;
  tentativas_da_pessoa: number;
  texto_das_tentativas: string;
  tolerancia_de_queda: number;
  livres: string[];
  capital_inicial: number;
  nota: string;
}

export interface BacktestDoAtivoV1 {
  ativo: AtivoV1;
  estrategia: string;
  parametros: Record<string, number | string>;
  custo_por_operacao: number;
  backtest: BacktestV1;
  ficha: FichaV1 | null; // null: não deu para montar (motivo_sem_ficha diz por quê)
  motivo_sem_ficha: string | null;
}

/** Uma simulação guardada na conta (Minhas simulações; Workspace, PR 1). */
export interface SimulacaoV1 {
  id: string;
  tipo: string; // "backtest", "carteira"...
  nome: string;
  criada_em: string; // data e hora, ISO
  dados_ate: string | null; // "dd/mm/aaaa": até quando iam os dados quando foi salva
  numeros: Record<string, string>; // os números como a tela mostrou ("Retorno total": "+12,0%")
  veredito: string | null; // o da ficha "Foi sorte?" ao salvar; null: salva sem ficha
  endereco: string | null; // reabre no app novo ("/backtest?..."); null: só reabre no app atual
}

export interface MinhasSimulacoesV1 {
  simulacoes: SimulacaoV1[]; // a mais nova primeiro
  usadas: number;
  limite: number | null; // null = sem limite
  uso: string; // "1 de 5", "0 de ilimitadas"
  sem_simulacoes: string; // a frase da lista vazia
}

// --- Pulse: estratégias acompanhadas (Workspace, PR 2) ---

export interface JanelaV1 {
  inicio: string; // data e hora, ISO com fuso: o início que o F5 reenvia em `desde`
  fim: string;
  primeira_vez: boolean;
  texto: string; // "Desde a sua última visita, em 16/10/2026 às 09h30."
}

export interface EstrategiaAcompanhadaV1 {
  id: string;
  nome: string;
  ticker: string | null;
  antes: string | null; // o veredito visto na última visita (ou o da hora de salvar)
  agora: string | null; // null: não deu para conferir agora
  mudou: boolean;
  conferido_em: string | null; // a visita em que o veredito de agora foi visto (ISO)
  tese_ligada: string | null; // texto da pessoa: mostrar como texto puro
  endereco: string | null; // o backtest no app novo; null: só reabre no app atual
}

export interface LimitesDoPulseV1 {
  sem_ficha: number;
  alem_do_maximo: number;
  nao_conferidas: number;
}

export interface PulseV1 {
  janela: JanelaV1;
  estrategias: EstrategiaAcompanhadaV1[]; // as que mudaram, as iguais, as não conferidas
  limites: LimitesDoPulseV1;
  avisos: string[];
  sem_estrategias: string;
  notas: string[];
}
