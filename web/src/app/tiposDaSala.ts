// O formato das respostas da sala de dados (src/api_v1/sala_painel.py). Fora de tipos.ts de propósito:
// aquele arquivo é conferido contra o contrato público (docs/api/openapi-v1.json), e a sala só abre
// para administradores, então não está nele.

export interface OpcaoV1 {
  valor: string;
  rotulo: string;
}

export interface OperacaoDaListaV1 {
  id: string;
  tipo: string;
  nome: string;
  situacao: "aberta" | "encerrada";
  retencao_ate: string;
  criada_em: string;
  dias_ate_sumir: number;
  aviso_de_prazo: string | null;
  documentos: number;
  contradicoes_abertas: number;
}

export interface SalaV1 {
  conceitos: Record<string, string>;
  tipos: OpcaoV1[];
  prazos_em_dias: number[];
  prazo_padrao_em_dias: number;
  operacoes: OperacaoDaListaV1[];
}

export interface DocumentoDoPainelV1 {
  id: string;
  nome: string;
  tipo: string;
  tamanho_bytes: number;
  paginas: number | null;
  situacao: string;
  rotulo_da_situacao: string;
  recebido_em: string;
}

export interface EvidenciaDoPainelV1 {
  id: string;
  documento: string;
  metrica: string;
  periodo: string;
  valor: string;
  pagina: number | null;
  trecho: string | null;
  conferida: boolean;
  estado_de_revisao: string;
}

export interface ContradicaoDoPainelV1 {
  id: string;
  estado: "aberta" | "explicada" | "descartada";
  rotulo_do_estado: string;
  nota: string | null;
  metrica: string;
  periodo: string;
  documento_a: string;
  documento_b: string;
  valor_a: string;
  valor_b: string;
}

export interface ItemDoPainelV1 {
  codigo: string;
  titulo: string;
  ajuda: string;
  estado: string;
  rotulo_do_estado: string;
  documento: string | null;
  nota: string | null;
}

export interface PainelV1 {
  operacao: OperacaoDaListaV1;
  tipo_rotulo: string;
  documentos: DocumentoDoPainelV1[];
  evidencias: EvidenciaDoPainelV1[];
  contradicoes: ContradicaoDoPainelV1[];
  checklist: ItemDoPainelV1[];
  estados_do_checklist: OpcaoV1[];
  itens_a_revisar: number;
}
