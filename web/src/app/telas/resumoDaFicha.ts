// O Resumo da ficha em abas (linha 903, PR B): a frase do topo e os números que importam, só do que a ficha
// já traz (nenhum dado novo). Cada número leva a fonte e o dia em que ficou público; o que a ficha não tem
// vira "Não temos", nunca um zero ou um traço que pareça valor. Funções puras: a tela só desenha.
import type { FichaDoCnpjV1 } from "../tipos";
import { cnpjComPontuacao, textoDoValor } from "./valoresDaFicha";

export const NAO_TEMOS = "Não temos";

/** As abas da ficha, na ordem da tela; `chave` vai no estado da aba e nos testes. */
export const ABAS_DA_FICHA = [
  { chave: "resumo", titulo: "Resumo" },
  { chave: "cadastro", titulo: "Cadastro" },
  { chave: "quem_controla", titulo: "Quem controla" },
  { chave: "sinais", titulo: "Sinais" },
  { chave: "eventos", titulo: "Eventos" },
  { chave: "vinculos", titulo: "Vínculos" },
  { chave: "fontes", titulo: "Fontes e limites" },
] as const;

export type ChaveDaAba = (typeof ABAS_DA_FICHA)[number]["chave"];

export type NumeroDoResumo = {
  rotulo: string;
  valor: string;
  fonte: string | null; // null quando o valor é "Não temos"
  publicoEm: string | null; // AAAA-MM-DD
};

const valorDe = (ficha: FichaDoCnpjV1, chave: string) => ficha.cadastro_na_receita[chave];

/** A razão social como a Receita publicou, ou null se a ficha não a trouxe. */
export function nomeDaEmpresa(ficha: FichaDoCnpjV1): string | null {
  const valor = valorDe(ficha, "razao_social")?.valor;
  return typeof valor === "string" && valor.trim() !== "" ? valor : null;
}

/** Uma frase só, de fato: quem é, a situação na Receita e se é matriz. Sem adjetivo, sem recomendação. */
export function fraseDoTopo(ficha: FichaDoCnpjV1, barrados: ReadonlySet<string> = new Set()): string {
  const nome = nomeDaEmpresa(ficha) ?? `A empresa do CNPJ ${cnpjComPontuacao(ficha.cnpj)}`;
  const situacao = valorDe(ficha, "situacao_cadastral");
  const desde = valorDe(ficha, "data_situacao_cadastral");
  const matriz = valorDe(ficha, "matriz")?.valor;
  const partes: string[] = [];
  if (situacao && situacao.valor !== null) {
    const texto = textoDoValor("situacao_cadastral", situacao.valor).toLowerCase();
    partes.push(
      desde && desde.valor !== null
        ? `consta como ${texto} na Receita desde ${textoDoValor("data_situacao_cadastral", desde.valor)}`
        : `consta como ${texto} na Receita`,
    );
  } else if (barrados.has("situacao_cadastral")) {
    // campo não liberado para a tela não é campo que a empresa não tem (linha 899)
    partes.push("tem a situação cadastral fora desta consulta");
  } else {
    partes.push("não tem a situação cadastral na base");
  }
  if (typeof matriz === "boolean") partes.push(matriz ? "é a matriz" : "é uma filial");
  return `${nome} ${partes.join("; ")}.`;
}

function numeroDoCampo(
  ficha: FichaDoCnpjV1,
  rotulo: string,
  chave: string,
  barrados: ReadonlySet<string>,
): NumeroDoResumo {
  const campo = valorDe(ficha, chave);
  if (barrados.has(chave)) return { rotulo, valor: "Não consultado", fonte: null, publicoEm: null };
  if (!campo || campo.valor === null) return { rotulo, valor: NAO_TEMOS, fonte: null, publicoEm: null };
  return { rotulo, valor: textoDoValor(chave, campo.valor), fonte: campo.fonte, publicoEm: campo.publico_em };
}

/** As entregas à CVM: a contagem só quando a lista está completa; documento barrado vira "Não consultado". */
function numeroDasEntregas(ficha: FichaDoCnpjV1): NumeroDoResumo {
  const rotulo = "Entregas de balanço à CVM";
  const entregas = ficha.entregas;
  if (!entregas || entregas.length === 0) return { rotulo, valor: NAO_TEMOS, fonte: null, publicoEm: null };
  if ((ficha.entregas_nao_disponiveis ?? []).length > 0) {
    return { rotulo, valor: "Não consultado por inteiro", fonte: null, publicoEm: null };
  }
  // a lista traz também o que era devido e não foi entregue: a contagem é só do que foi entregue
  const entregues = entregas.filter((entrega) => entrega.situacao_da_entrega?.valor !== "not_filed");
  if (entregues.length === 0) return { rotulo, valor: NAO_TEMOS, fonte: null, publicoEm: null };
  const campos = entregues.flatMap((entrega) => Object.values(entrega));
  const datas = campos.map((campo) => campo.publico_em).sort();
  return {
    rotulo,
    valor: String(entregues.length),
    fonte: [...new Set(campos.map((campo) => campo.fonte))].join(", "),
    publicoEm: datas[datas.length - 1] ?? null,
  };
}

/** Os quatro números do Resumo, na ordem em que a conversa de venda os lê. */
export function numerosDoResumo(ficha: FichaDoCnpjV1, barrados: ReadonlySet<string> = new Set()): NumeroDoResumo[] {
  return [
    numeroDoCampo(ficha, "Situação cadastral", "situacao_cadastral", barrados),
    numeroDoCampo(ficha, "Situação desde", "data_situacao_cadastral", barrados),
    numeroDoCampo(ficha, "Optante pelo Simples", "optante_simples", barrados),
    numeroDasEntregas(ficha),
  ];
}
