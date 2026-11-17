// O formato das respostas da Administração (src/api_v1/administracao.py). Fora de tipos.ts de propósito:
// aquele arquivo é conferido contra o contrato público (docs/api/openapi-v1.json), e estas rotas só abrem
// para administradores, então não estão nele. Nenhum campo aqui traz o valor de uma chave nem dado de conta.

export interface OrganizacaoDaListaV1 {
  id: string;
  nome: string;
  plano_da_api: string;
  nome_do_plano: string;
  suspensa: boolean;
}

export interface OrganizacoesV1 {
  organizacoes: OrganizacaoDaListaV1[];
}

export interface LimitesDoPlanoV1 {
  pedidos_por_minuto: number;
  pedidos_por_mes: number;
  linhas_por_resposta: number;
  chaves_ativas: number;
}

export interface ConsumoDoMesV1 {
  pedidos: number;
  linhas: number;
  negados: number;
}

/** Uma chave pelo que a identifica: o prefixo, nunca o valor. */
export interface ChaveDaOrganizacaoV1 {
  id: string;
  prefixo: string;
  /** "ativa", "de_saida" (a antiga de uma rotação), "expirada" ou "revogada". */
  estado: string;
  criada_em: string;
  expira_em: string | null;
  revogada_em: string | null;
  ultimo_uso: string | null;
}

export interface DireitoEmVigorV1 {
  conjunto: string;
  finalidade: string;
  vigente_desde: string;
  vigente_ate: string | null;
}

export interface ConjuntoDesligadoV1 {
  conjunto: string;
  finalidade: string;
  /** "sem_contrato" ou "suspenso_para_todos". */
  motivo: string;
}

export interface PainelDaOrganizacaoV1 {
  id: string;
  nome: string;
  cnpj: string | null;
  plano_da_api: string;
  nome_do_plano: string;
  criada_em: string;
  suspensa_em: string | null;
  motivo_da_suspensao: string | null;
  limites: LimitesDoPlanoV1;
  consumo: ConsumoDoMesV1;
  /** As chaves que ocupam vaga no limite do plano. */
  chaves_ativas: number;
  chaves: ChaveDaOrganizacaoV1[];
  direitos: DireitoEmVigorV1[];
  ainda_desligado: ConjuntoDesligadoV1[];
  /** Só o estado da permissão; quem liga é o dono, pelo script. */
  pessoa_na_tela: boolean;
  /** Quantas contas estão vinculadas (só o número). */
  membros: number;
}
