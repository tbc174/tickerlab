// O formato das respostas da Administração (src/api_v1/administracao.py, administracao_contas.py e
// administracao_registro.py). Fora de
// tipos.ts de propósito: aquele arquivo é conferido contra o contrato público (docs/api/openapi-v1.json), e
// estas rotas só abrem para administradores, então não estão nele. As organizações não trazem dado de conta
// (só quantas estão vinculadas); o e-mail e o nome de uma conta vêm só em `ContaV1`, a lista de contas do
// app, e em `AcaoV1`, o registro de ações (de quem fez e de quem sofreu a ação): ficam no estado da tela e
// em mais lugar nenhum. O valor de uma chave só existe em `ChaveNovaV1`:
// a resposta, uma única vez, de quem a emitiu ou trocou.

export interface OrganizacaoDaListaV1 {
  id: string;
  nome: string;
  plano_da_api: string;
  nome_do_plano: string;
  suspensa: boolean;
}

export interface PlanoDaApiV1 {
  plano_da_api: string;
  nome_do_plano: string;
}

export interface OrganizacoesV1 {
  organizacoes: OrganizacaoDaListaV1[];
  /** Os planos que uma organização nova pode ter (o formulário de criar). */
  planos_da_api: PlanoDaApiV1[];
  /** Os motivos que o servidor aceita ao suspender, em código. */
  motivos_da_suspensao: string[];
}

/** A resposta de suspender, reativar e revogar: `mudou` falso quer dizer que já estava assim. */
export interface MudouV1 {
  mudou: boolean;
}

/** A chave recém-emitida ou trocada. É a única resposta com o `valor`, e ele não volta em nenhuma leitura:
 * fica só no estado da tela, até ser tirado. */
export interface ChaveNovaV1 {
  id: string;
  prefixo: string;
  valor: string;
  /** Numa troca, por quantos dias a chave antiga ainda vale; nulo ao emitir. */
  antiga_vale_por_dias: number | null;
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

/** Os números do serviço: só contagens. */
export interface ResumoV1 {
  usuarios: number;
  gratuito: number;
  plus: number;
  pro: number;
  administradores: number;
  novos_na_semana: number;
  ativos_na_semana: number;
  simulacoes: number;
  assinaturas_ativas: number;
  eventos_do_stripe: number;
}

/** Uma conta do app, como o administrador a vê. */
export interface ContaV1 {
  id: string;
  email: string;
  nome: string | null;
  /** "usuario" ou "admin". */
  papel: string;
  /** "gratuito", "plus" ou "pro". */
  plano: string;
  criado_em: string;
  ultimo_acesso: string | null;
  /** O estado da assinatura no Stripe, em código (`active`, `canceled`...); nulo sem assinatura. */
  status_da_assinatura: string | null;
  simulacoes: number;
  bloqueada_em: string | null;
  motivo_do_bloqueio: string | null;
  /** É a conta de quem está olhando: a tela não oferece tirar o próprio acesso (quem recusa é o servidor). */
  e_voce: boolean;
}

export interface ContasV1 {
  contas: ContaV1[];
  /** Há mais contas do que as que vieram: a busca precisa ser afinada. */
  cortada: boolean;
  /** O que o servidor aceita em cada mudança, em código. */
  planos: string[];
  papeis: string[];
  motivos_do_bloqueio: string[];
}

/** A resposta de bloquear: quantas sessões da conta o servidor encerrou. */
export interface BloqueadaV1 {
  sessoes_encerradas: number;
}

/** Uma linha do registro de ações (a auditoria), como o administrador a vê. */
export interface AcaoV1 {
  id: string;
  /** Quando foi, em UTC. */
  quando: string;
  /** O código gravado na auditoria (`plano_alterado`, `chave_emitida`...). */
  acao: string;
  /** Nulo: a conta que fez foi apagada, ou foi o próprio serviço. */
  ator_id: string | null;
  /** Só de conta que ainda existe. */
  ator_email: string | null;
  alvo_id: string | null;
  /** Só quando o alvo é uma conta que ainda existe. */
  alvo_email: string | null;
  /** Foi a conta de quem está olhando. */
  foi_voce: boolean;
  /** Ids e dados técnicos, como a auditoria gravou. */
  detalhes: Record<string, unknown>;
}

export interface RegistroV1 {
  /** Das mais novas para as mais antigas. */
  acoes: AcaoV1[];
  /** Há ações mais antigas do que as que vieram. */
  cortado: boolean;
}

/** Um evento do Stripe que o webhook processou. */
export interface EventoDoStripeV1 {
  id: string;
  tipo: string;
  processado_em: string;
}

export interface EventosDoStripeV1 {
  eventos: EventoDoStripeV1[];
  cortado: boolean;
}
