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

/** Um mês de um preço de referência: o Pink Sheet e, no café e no algodão, o FMI ao lado. */
export interface PontoDoPrecoV1 {
  mes: string; // primeiro dia do mês
  bm: number | null; // Banco Mundial (Pink Sheet)
  fmi: number | null; // FMI (PCPS); null também quando o item não tem o FMI
}

export interface PontoDoSpreadV1 {
  mes: string;
  valor: number; // arábica menos robusta, US$/kg
}

/** Um item de Preços de referência, com os textos prontos (src/commodities/painel_de_precos.py). */
export interface PrecoDeReferenciaV1 {
  chave: string;
  nome: string;
  unidade: string;
  ultimo_mes: string;
  ultimo_valor: number;
  texto: string; // como a tela mostra ("1.234,50")
  variacao_12_meses: number | null;
  texto_da_variacao: string | null; // "+3,2% em 12 meses"
  legenda: string; // o mês e a fonte
  com_fmi: boolean;
  nota_das_fontes: string | null;
  historico: PontoDoPrecoV1[];
}

export interface PrecosDeReferenciaV1 {
  dia: string;
  itens: PrecoDeReferenciaV1[];
  spread: PontoDoSpreadV1[];
  titulo_do_spread: string;
  nota_do_spread: string;
  aviso_diario: string;
  atribuicao: string;
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
  endereco: string | null; // reabre no app novo ("/backtest?..."); null: só reabre na versão clássica
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
  endereco: string | null; // o backtest no app novo; null: só reabre na versão clássica
}

export interface LimitesDoPulseV1 {
  sem_ficha: number;
  alem_do_maximo: number;
  nao_conferidas: number;
  alem_dos_ativos: number; // ativos guardados além do máximo que o Pulse acompanha
}

// --- Pulse, parte 2: acontecimentos novos e variação do preço (Workspace, PR 3) ---

export interface AcontecimentoV1 {
  id: string; // "<fonte>:<protocolo>"
  ticker: string; // sem o ".SA"
  empresa: string;
  tipo: string; // "Fato Relevante", "Comunicado ao Mercado", "8-K"…
  titulo: string;
  publicado_em: string; // "2026-10-08"
  fonte: string; // "CVM" ou "SEC"
  link_do_original: string | null; // só https da CVM ou da SEC; null: sem link
  relevancia: number; // de 0 a 1: a ordem da lista
  por_que_aparece: string[];
}

export interface VariacaoV1 {
  ticker: string;
  variacao: number; // fração: 0.0115 = +1,15%
  de: string; // o último fechamento que já existia na hora da visita
  ate: string; // o último fechamento de hoje
  por_que_aparece: string[]; // "favoritos", "Minha carteira", "lista Bancos"…
}

export interface PulseV1 {
  janela: JanelaV1;
  estrategias: EstrategiaAcompanhadaV1[]; // as que mudaram, as iguais, as não conferidas
  limites: LimitesDoPulseV1;
  avisos: string[];
  sem_estrategias: string;
  notas: string[];
  acontecimentos: AcontecimentoV1[] | null; // null: a leitura falhou e a visita não foi marcada
  variacoes: VariacaoV1[]; // a maior mudança primeiro (pulse.ordenar_variacoes)
  avisos_dos_ativos: string[];
  sem_variacao: string[]; // os ativos sem preço para comparar
  sem_ativos: string; // a frase de quando não há nenhum ativo guardado
  nota_da_variacao: string;
}

/** Um número do relatório da empresa, já escrito ("R$ 12,3 bi"), com a base e a nota. */
/** Contra o quê o número é comparado (o setor, uma faixa, o artigo, o balanço anterior). */
export interface ComparacaoDoNumeroV1 {
  contra: string;
  texto: string;
  valor?: number | null; // o número comparado, quando é um só
}

/** Um ponto de "O que os dados mostram": de uma regra fixa, com o número, a data e a tabela. */
export interface PontoDoRelatorioV1 {
  lado: string; // "forte" ou "atenção"
  texto: string;
  numero: string;
  medido_em: string;
  tabela: string;
  indicador: string;
}

/** Um documento que entrou na conta: a demonstração da CVM ou o fechamento do preço. */
export interface DocumentoUsadoV1 {
  nome: string;
  publicado_em: string | null; // ISO; null: o dia não é conhecido
  url: string; // "" quando não há link
}

/** Uma linha do "como foi calculado", já escrita como na página e no PDF (src/rastro.py). */
export interface LinhaDoRastroV1 {
  rotulo: string; // "Fórmula", "Versão do cálculo", "Fonte", "Publicado em", "Documento"
  texto: string;
  url: string; // o documento original ("" quando não há link)
}

/** Como o número foi calculado e de onde veio: a conta, a versão, a fonte e a publicação. */
export interface RastroDoNumeroV1 {
  formula: string;
  versao_do_calculo: string;
  fonte_id: string;
  publicado_em: string | null;
  documentos: DocumentoUsadoV1[];
  outras_fontes: string[];
  linhas: LinhaDoRastroV1[];
}

/** Um número com de quando é (base), de onde veio (fonte) e a comparação (ou por que não há). */
export interface ItemDoRelatorioV1 {
  chave: string;
  nome: string;
  texto: string;
  valor: number | null;
  unidade: string;
  base: string;
  motivo: string;
  nota: string | null;
  nota_texto: string;
  fonte: string;
  comparacao: ComparacaoDoNumeroV1 | null;
  sem_comparacao: string;
  rastro?: RastroDoNumeroV1 | null; // null: frase (nome, auditor) ou ficha antiga da base
}

/** Uma tabela com as células já escritas (como na página do Streamlit e no PDF). */
export interface TabelaDoRelatorioV1 {
  chave: string;
  titulo: string;
  colunas: string[];
  linhas: string[][];
}

export interface SecaoDoRelatorioV1 {
  chave: string;
  titulo: string;
  itens: ItemDoRelatorioV1[];
  paragrafos: string[];
  tabelas: TabelaDoRelatorioV1[];
  pontos?: PontoDoRelatorioV1[];
  trancada: boolean; // o plano não inclui a seção: só o título e o convite, sem números
  recolhida?: boolean; // explicação: a tela mostra fechada até a pessoa abrir
}

/** A nota numerada de uma frase da análise: abre o número de onde a frase saiu. */
export interface NotaDaAnaliseV1 {
  numero: number;
  id: string;
  nome: string;
  texto: string; // o valor já escrito, ou a linha da tabela
  medido_em: string;
  fonte: string;
  comparacao: string; // "Contra X: texto"; vazio quando não compara
}

export interface FraseDaAnaliseV1 {
  texto: string;
  notas: number[]; // os números das notas (AnaliseDaEmpresaV1.notas)
}

export interface ParagrafoDaAnaliseV1 {
  tipo: "fato" | "leitura";
  rotulo: string; // "Leitura" no parágrafo de leitura; vazio no de fato
  frases: FraseDaAnaliseV1[];
}

export interface ParteDaAnaliseV1 {
  chave: string;
  titulo: string;
  origem: "modelo" | "molde"; // molde: texto de reserva por regras
  paragrafos: ParagrafoDaAnaliseV1[];
}

/** A análise escrita pelo modelo, frase por frase, com fonte em cada uma (ADR 0100). */
export interface AnaliseDaEmpresaV1 {
  partes: ParteDaAnaliseV1[];
  notas: NotaDaAnaliseV1[];
  aviso: string;
  motivo?: string | null; // por que saiu o molde no lugar do texto do modelo, se saiu
}

export interface RelatorioDaEmpresaV1 {
  empresa: string;
  cnpj: string;
  ticker: string;
  setor: string;
  grupo: string;
  secoes: SecaoDoRelatorioV1[];
  fontes: string[];
  aviso_das_notas: string;
  em_conferencia: boolean;
  analise?: AnaliseDaEmpresaV1 | null; // null: sem análise aprovada para a empresa
}

/** O relatório do CNPJ (molde B): as seções no formato do relatório da empresa. */
export interface BuscaPorCnpjV1 {
  situacao: "encontrada" | "fora_da_base_aberta";
  cnpj: string;
  empresa: string;
  tickers: string[];
  como_era_em: string | null; // o dia da ficha da noite (AAAA-MM-DD)
  secoes: SecaoDoRelatorioV1[];
  fontes: string[];
  limites: string[]; // "Limites e cuidados": sempre presentes
  desligado: string[]; // o que ainda não aparece e por quê: sempre presente
  avisos: string[];
}

/** Uma camada do Mapa do café: o que pinta os municípios, com o "o que é isto" e a fonte. */
export interface CamadaDoMapaV1 {
  chave: string; // "producao", "area", "chuva" ou "geada"
  titulo: string;
  unidade: string;
  o_que_e: string;
  fonte: string;
  escala: string; // "sequencial" (mais é mais) ou "divergente" (em torno de `referencia`)
  referencia: number | null;
}

export interface MunicipioDoMapaV1 {
  codigo: string; // o código do IBGE, o mesmo da propriedade `codarea` da malha
  nome: string;
  uf: string;
  regiao: string | null; // null: fora das regiões produtoras do cadastro
  valores: Record<string, number | null>; // por camada
  sem_dado: Record<string, string>; // por camada sem valor: por que o município fica cinza
  area_mapbiomas_ha: number | null;
}

export interface IndiceDoMapaV1 {
  valor: number | null;
  normal: number | null;
  n_estacoes: number;
  inicio: string;
  fim: string;
  texto: string; // a frase pronta, com o período e de onde veio
}

export interface ItemDoMesV1 {
  titulo: string;
  texto: string;
}

export interface RegiaoDoMapaV1 {
  id: string;
  nome: string;
  tipo_predominante: string;
  chuva: IndiceDoMapaV1;
  geada: IndiceDoMapaV1;
  fase: string;
  o_que_o_mercado_olha: ItemDoMesV1[];
}

/** O GeoJSON simplificado da malha do IBGE (só o que a tela usa). */
export interface MalhaDoMapa {
  type: string;
  features: { properties: { codarea?: string }; geometry: { type: string; coordinates: unknown } }[];
}

export interface MapaDoCafeV1 {
  tipo: string;
  ano: number;
  gerado_em: string;
  mes: number;
  camadas: CamadaDoMapaV1[];
  municipios: MunicipioDoMapaV1[];
  regioes: RegiaoDoMapaV1[];
  malha: MalhaDoMapa;
  fontes: string[];
  aviso: string;
}

// --- Painel do café (src/api_v1/esquemas.py, PainelDoCafeV1): cada caixa com o que é, fonte e data ---

export interface PontoDoPrecoDoCafeV1 {
  mes: string;
  bm: number | null; // Pink Sheet do Banco Mundial
  fmi: number | null;
}

export interface PrecoDeReferenciaDoCafeV1 {
  chave: string;
  nome: string;
  unidade: string;
  ultimo_mes: string;
  ultimo_valor: number;
  variacao_12_meses: number | null; // em %
  historico: PontoDoPrecoDoCafeV1[];
  com_fmi: boolean;
  nota_das_fontes: string | null;
}

export interface PontoDoSpreadDoCafeV1 {
  mes: string;
  arabica: number; // centavos de dólar por libra-peso
  robusta: number;
  spread: number;
  razao: number;
}

export interface MarcoDoCafeV1 {
  data: string;
  texto: string;
  fonte: string;
}

export interface PrecoDoCafeV1 {
  item: PrecoDeReferenciaDoCafeV1;
  spread: PontoDoSpreadDoCafeV1[];
  marcos: MarcoDoCafeV1[];
}

export interface PontoDoCambioV1 {
  mes: string;
  valor: number; // média do mês, R$ por US$
}

export interface CambioDoCafeV1 {
  ultimo_dia: string;
  ultimo_valor: number;
  variacao_12_meses: number | null; // em %
  historico: PontoDoCambioV1[];
}

export interface PontoDosFundosV1 {
  relatorio: string;
  liquido_lotes: number;
  fracao_do_interesse_aberto: number;
}

export interface FundosDoCafeV1 {
  relatorio: string;
  comprados_lotes: number;
  vendidos_lotes: number;
  liquido_lotes: number;
  liquido_sacas: number;
  interesse_aberto_lotes: number;
  fracao_do_interesse_aberto: number;
  historico: PontoDosFundosV1[];
  legenda: string;
}

export interface DestinoDoCafeV1 {
  pais: string;
  sacas: number;
  fob_usd: number;
  fracao: number;
}

export interface ExportacoesDoCafeV1 {
  primeiro_mes: string;
  ultimo_mes: string;
  sacas: number;
  fob_usd: number;
  destinos: DestinoDoCafeV1[];
  fracao_do_espirito_santo: number | null;
  nota: string;
}

export interface PontoAnualDoCafeV1 {
  ano_safra: number;
  valor: number;
  rotulo: string;
}

export interface BalancoDoPaisV1 {
  codigo_do_pais: string;
  ano_safra: number;
  tipo: string;
  producao: number;
  participacao_na_producao: number;
  relacao_estoque_consumo: number | null;
}

export interface BalancoDoCafeV1 {
  ultima_safra: number;
  estoque_consumo_mundo: PontoAnualDoCafeV1[];
  estoque_consumo_brasil: PontoAnualDoCafeV1[];
  participacao_do_brasil: PontoAnualDoCafeV1[];
  paises: BalancoDoPaisV1[];
}

export interface LinhaDaSafraV1 {
  uf: string;
  area_producao_ha: number | null;
  produtividade_sc_ha: number | null;
  producao_mil_sacas: number | null;
}

export interface SafraDoCafeV1 {
  safra: number;
  levantamento: number;
  divulgado_em: string;
  linhas: LinhaDaSafraV1[];
}

export interface ErroDaSafraV1 {
  safra: number;
  erro_pct: number;
  erro_mil_sacas: number;
}

export interface TermometroDaConabV1 {
  erros: ErroDaSafraV1[];
  vies_medio_pct: number | null;
  menor_erro_pct: number;
  maior_erro_pct: number;
  nota: string;
}

export interface PontoDaSafraV1 {
  safra: number;
  tipo: string;
  uf: string;
  serie: string;
  valor: number;
  unidade: string;
  rotulo: string | null;
  levantamento: number | null;
}

export interface BienalidadeDoCafeV1 {
  marcas: PontoDaSafraV1[];
}

export interface IndiceDeChuvaV1 {
  valor: number | null; // mm somados nos três meses
  normal: number | null;
  anomalia: number | null;
  razao_da_normal: number | null;
  n_estacoes: number;
  inicio: string;
  fim: string;
}

export interface TemperaturaDoMesV1 {
  competencia: string;
  tmin_media_c: number | null;
  tmin_normal_c: number | null;
  tmin_anomalia_c: number | null;
  dias_tmin_abaixo_de_2c: number | null;
}

export interface ClimaDaRegiaoV1 {
  regiao: string;
  nome_da_regiao: string;
  fonte_dos_dados: string;
  chuva: IndiceDeChuvaV1;
  temperatura: TemperaturaDoMesV1;
}

export interface FaseDoCafeV1 {
  mes: number;
  regiao_id: string;
  safra_em_curso: string;
  safra_seguinte: string;
  em_colheita: boolean;
  na_janela_de_geada: boolean;
}

export interface ItemDoCalendarioV1 {
  tema: string;
  texto: string;
  indices: string[];
}

export interface CalendarioDoCafeV1 {
  fase: FaseDoCafeV1;
  itens: ItemDoCalendarioV1[];
}

export interface FatoDaContraparteV1 {
  fato: string;
  descricao: string;
  valor: number | null;
  unidade: string | null;
  data: string;
  divulgado_em: string;
  fonte: string; // o link
  veiculo: string;
  tipo_de_fonte: string;
}

export interface FichaDaContraparteV1 {
  id: string;
  cnpj: string | null;
  nome: string;
  tipo: string;
  uf: string | null;
  fatos: FatoDaContraparteV1[];
  o_que_nao_sabemos: string[];
}

export interface ContrapartesDoCafeV1 {
  fichas: FichaDaContraparteV1[];
}

/** Uma caixa do painel: sem dado, `conteudo` vem vazio e `motivo_sem_dado` diz por quê. */
export interface BlocoDoCafeV1<T> {
  chave: string;
  titulo: string;
  o_que_e: string;
  fonte: string;
  data: string | null; // o número mais novo da caixa
  motivo_sem_dado: string | null;
  conteudo: T | null;
}

export interface OpcaoDeRegiaoV1 {
  id: string;
  nome: string;
  tipo_predominante: string;
}

export interface PainelDoCafeV1 {
  dia: string;
  tipo: string; // "arabica" ou "conilon"
  nome_do_tipo: string;
  regiao: string;
  regioes: OpcaoDeRegiaoV1[];
  aviso_diario: string;
  preco_de_referencia: BlocoDoCafeV1<PrecoDoCafeV1>;
  cambio: BlocoDoCafeV1<CambioDoCafeV1>;
  fundos: BlocoDoCafeV1<FundosDoCafeV1>;
  exportacoes: BlocoDoCafeV1<ExportacoesDoCafeV1>;
  balanco: BlocoDoCafeV1<BalancoDoCafeV1>;
  safra: BlocoDoCafeV1<SafraDoCafeV1>;
  termometro: BlocoDoCafeV1<TermometroDaConabV1>;
  bienalidade: BlocoDoCafeV1<BienalidadeDoCafeV1>;
  clima: BlocoDoCafeV1<ClimaDaRegiaoV1>;
  calendario: BlocoDoCafeV1<CalendarioDoCafeV1>;
  contrapartes: BlocoDoCafeV1<ContrapartesDoCafeV1>;
}
