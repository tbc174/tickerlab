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
  ticker: string;
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
