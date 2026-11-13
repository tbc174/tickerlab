// Comparar empresas (tela do analista, linha 798): de dois a cinco CNPJs lado a lado, uma coluna por empresa,
// cada campo com a fonte e o dia em que ficou público, e a comparação em Excel. A rota usa o mesmo leitor e o
// mesmo portão da ficha e da busca: o que a API negaria não aparece aqui. Os CNPJs vão no corpo do POST (e,
// vindos da ficha, pelo estado da navegação), nunca no endereço; nada é pedido antes de a pessoa comparar.
import { type FormEvent, useState } from "react";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../pecas/Cabecalho";
import { Carregando } from "../pecas/Carregando";
import { useEstadoDaNavegacaoUmaVez } from "../estadoDaNavegacao";
import { formatarData } from "../formatar";
import type { CampoComFonteV1, ComparacaoDeEmpresasV1, EmpresaComparadaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { Erro } from "../pecas/Erro";
import { Baixar } from "../pecas/Baixar";
import { Fontes } from "../pecas/Fonte";
import { Limites } from "../pecas/Limites";
import { TAMANHO_MAXIMO_DO_CNPJ, cnpjComPontuacao, textoDoValor } from "./FichaDaEmpresa";

const MINIMO = 2;
const MAXIMO = 5;
const NOME_DA_PLANILHA = "comparacao-de-empresas-tickerlab.xlsx"; // sem CNPJ: o nome do arquivo não carrega dado
const SEM_VALOR = "—";
const REAIS = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const INTEIRO = new Intl.NumberFormat("pt-BR");

type Campo = Exclude<
  keyof EmpresaComparadaV1,
  | "cnpj"
  | "estado"
  | "porte_descricao"
  | "cnae_descricao"
  | "municipio_nome"
  | "entregas_conhecidas"
  | "entregas_com_atraso"
>;

/** Uma linha da tabela: o campo, o nome na tela e, se precisa, como o valor vira texto. */
interface Linha {
  campo: Campo;
  nome: string;
  texto?: (empresa: EmpresaComparadaV1, campo: CampoComFonteV1) => string;
}

const comNome = (codigo: string, nome: string | null) => (nome ? `${codigo} · ${nome}` : codigo);

// a ordem é a da conversa de um analista: quem é, o tamanho aproximado, onde está e o que faz, as entregas
const LINHAS: Linha[] = [
  { campo: "razao_social", nome: "Razão social" },
  { campo: "situacao_cadastral", nome: "Situação cadastral" },
  { campo: "data_situacao_cadastral", nome: "Data da situação" },
  { campo: "natureza_juridica", nome: "Natureza jurídica (código da Receita)" },
  { campo: "porte", nome: "Porte (Receita)", texto: (e, c) => e.porte_descricao ?? String(c.valor) },
  { campo: "data_inicio_atividade", nome: "Abertura" },
  {
    campo: "cnae_principal",
    nome: "Atividade principal (CNAE)",
    texto: (e, c) => comNome(String(c.valor), e.cnae_descricao),
  },
  { campo: "uf", nome: "UF" },
  { campo: "municipio", nome: "Município", texto: (e, c) => e.municipio_nome ?? String(c.valor) },
  { campo: "matriz", nome: "Matriz" },
  {
    campo: "capital_social",
    nome: "Capital social declarado (aproximação do tamanho)",
    texto: (_e, c) => (typeof c.valor === "number" ? REAIS.format(c.valor) : textoDoValor("capital_social", c.valor)),
  },
  {
    campo: "n_estabelecimentos",
    nome: "Estabelecimentos ativos (aproximação do tamanho)",
    texto: (_e, c) => (typeof c.valor === "number" ? INTEIRO.format(c.valor) : textoDoValor("", c.valor)),
  },
  { campo: "optante_simples", nome: "Optante pelo Simples" },
  { campo: "data_opcao_simples", nome: "Entrou no Simples em" },
  { campo: "data_exclusao_simples", nome: "Saiu do Simples em" },
  { campo: "ultima_entrega_documento", nome: "Última entrega à CVM" },
  { campo: "ultima_entrega_referencia", nome: "Referência da última entrega" },
  {
    campo: "ultima_entrega_situacao",
    nome: "Situação da última entrega",
    texto: (_e, c) => textoDoValor("situacao_da_entrega", c.valor),
  },
  { campo: "mes_do_retrato", nome: "Mês do cadastro" },
];

function Celula({ empresa, linha }: { empresa: EmpresaComparadaV1; linha: Linha }) {
  const campo = empresa[linha.campo];
  if (campo === null || campo === undefined) return <td>{SEM_VALOR}</td>;
  const texto = linha.texto ? linha.texto(empresa, campo) : textoDoValor(linha.campo, campo.valor);
  return (
    <td className="celula-comparada">
      {texto}
      <small className="apagado">
        {campo.fonte} · {formatarData(campo.publico_em)}
      </small>
    </td>
  );
}

/** "2 de 9": as entregas com atraso sobre as conhecidas; conta nossa, sem fonte de fora. */
function CelulaDosAtrasos({ empresa }: { empresa: EmpresaComparadaV1 }) {
  if (empresa.entregas_conhecidas === null || empresa.entregas_com_atraso === null) return <td>{SEM_VALOR}</td>;
  return (
    <td className="celula-comparada">
      {empresa.entregas_com_atraso} de {empresa.entregas_conhecidas}
      <small className="apagado">conta nossa sobre as entregas à CVM</small>
    </td>
  );
}

function Tabela({ empresas }: { empresas: EmpresaComparadaV1[] }) {
  const prontas = empresas.filter((e) => e.estado === "pronta");
  // linha sem valor em nenhuma empresa não ocupa a tela (o portão pode ter negado o campo)
  const linhas = LINHAS.filter((linha) => prontas.some((e) => e[linha.campo] !== null && e[linha.campo] !== undefined));
  const comAtrasos = prontas.some((e) => e.entregas_conhecidas !== null);
  return (
    <section className="secao-do-relatorio" aria-labelledby="empresas-comparadas">
      <h2 id="empresas-comparadas">Lado a lado</h2>
      <div className="tabela-rolavel">
        <table className="tabela-do-app">
          <thead>
            <tr>
              <th scope="col">Campo</th>
              {empresas.map((empresa) => (
                <th key={empresa.cnpj} scope="col">
                  {cnpjComPontuacao(empresa.cnpj)}
                  {empresa.estado === "pronta" ? null : <small className="apagado"> · não disponível</small>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {linhas.map((linha) => (
              <tr key={linha.campo}>
                <th scope="row">{linha.nome}</th>
                {empresas.map((empresa) => (
                  <Celula key={empresa.cnpj} empresa={empresa} linha={linha} />
                ))}
              </tr>
            ))}
            {comAtrasos ? (
              <tr>
                <th scope="row">Entregas à CVM com atraso</th>
                {empresas.map((empresa) => (
                  <CelulaDosAtrasos key={empresa.cnpj} empresa={empresa} />
                ))}
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Comparacao({ dados, rota, cnpjs }: { dados: ComparacaoDeEmpresasV1; rota: string; cnpjs: string[] }) {
  if (dados.estado === "nao_liberada") {
    return (
      <p className="apagado" role="note">
        Dado ainda não liberado: a comparação entra nesta tela quando a conferência da tabela terminar.
      </p>
    );
  }
  const algumaPronta = dados.empresas.some((e) => e.estado === "pronta");
  return (
    <>
      <p className="apagado">Como a base conhecia em {formatarData(dados.como_era_em ?? "")}</p>
      {algumaPronta ? (
        <div className="acoes-da-ficha">
          <Baixar rotulo="Baixar em Excel" rota={`${rota}/planilha`} corpo={{ cnpjs }} nome={NOME_DA_PLANILHA} />
        </div>
      ) : (
        <p className="apagado" role="note">
          Nenhuma das empresas pedidas está disponível na base.
        </p>
      )}
      <Tabela empresas={dados.empresas} />
      {dados.fontes.length > 0 ? <Fontes fontes={dados.fontes} /> : null}
    </>
  );
}

function Resultado({ pagina, cnpjs }: { pagina: PaginaDoApp; cnpjs: string[] }) {
  const rota = pagina.contrato?.rota ?? "";
  const pedido = usarPedido<ComparacaoDeEmpresasV1>(rota, {}, { cnpjs });
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Pondo as empresas lado a lado…" />;
  if (pedido.estado === "erro") return <Erro erro={pedido.erro} />;
  return (
    <>
      <Comparacao dados={pedido.dados} rota={rota} cnpjs={cnpjs} />
      <Limites itens={pedido.dados.limites} />
    </>
  );
}

// antes da primeira comparação os limites não vêm da API; este é o resumo fixo da tela
const ANTES_DE_COMPARAR =
  "Ponha de duas a cinco empresas lado a lado pelo CNPJ: o cadastro da Receita Federal e, das companhias abertas, as entregas de balanço à CVM, com a fonte e a data de cada campo. Pessoa física, MEI e empresário individual não aparecem. Nada aqui é recomendação de investimento.";

/** Os CNPJs que outra tela (a ficha) manda pelo estado da navegação, nunca pelo endereço; só textos, até cinco. */
function cnpjsDaNavegacao(estado: unknown): string[] {
  const cnpjs = (estado as { cnpjs?: unknown } | null)?.cnpjs;
  if (!Array.isArray(cnpjs)) return [];
  return cnpjs.filter((c): c is string => typeof c === "string" && c !== "").slice(0, MAXIMO);
}

const completarAteOMinimo = (cnpjs: string[]) => [...cnpjs, ...Array(Math.max(0, MINIMO - cnpjs.length)).fill("")];

export function CompararEmpresas({ pagina }: { pagina: PaginaDoApp }) {
  const vindos = cnpjsDaNavegacao(useEstadoDaNavegacaoUmaVez());
  const [rascunhos, setRascunhos] = useState<string[]>(() => completarAteOMinimo(vindos));
  // com dois ou mais CNPJs vindos de outra tela, a comparação já sai; com um (da ficha), falta o segundo
  const [comparado, setComparado] = useState<{ cnpjs: string[]; vez: number } | null>(
    vindos.length >= MINIMO ? { cnpjs: vindos, vez: 1 } : null,
  );
  const mudar = (posicao: number, valor: string) =>
    setRascunhos((atuais) => atuais.map((atual, i) => (i === posicao ? valor : atual)));
  const tirar = (posicao: number) => setRascunhos((atuais) => atuais.filter((_, i) => i !== posicao));
  const comparar = (evento: FormEvent) => {
    evento.preventDefault();
    const cnpjs = rascunhos.map((r) => r.trim());
    if (cnpjs.every((c) => c !== "")) setComparado({ cnpjs, vez: (comparado?.vez ?? 0) + 1 });
  };
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      <form className="formulario-do-app" onSubmit={comparar}>
        <div className="cnpjs-da-comparacao">
          {rascunhos.map((rascunho, i) => (
            // a posição serve de chave: tirar um campo refaz a lista inteira, e o valor vem do estado
            <div key={i} className="campos-do-formulario">
              <label>
                <span>CNPJ {i + 1}</span>
                <input
                  value={rascunho}
                  onChange={(ev) => mudar(i, ev.target.value)}
                  required
                  type="text"
                  inputMode="text"
                  autoComplete="off"
                  maxLength={TAMANHO_MAXIMO_DO_CNPJ}
                  placeholder="00.000.000/0000-00"
                />
              </label>
              {rascunhos.length > MINIMO ? (
                <button type="button" className="botao" onClick={() => tirar(i)}>
                  Tirar o CNPJ {i + 1}
                </button>
              ) : null}
            </div>
          ))}
        </div>
        {rascunhos.length < MAXIMO ? (
          <button type="button" className="botao" onClick={() => setRascunhos((atuais) => [...atuais, ""])}>
            Mais uma empresa
          </button>
        ) : null}
        <button className="botao primario" type="submit">
          Comparar
        </button>
      </form>
      {comparado === null ? (
        <p className="apagado">{ANTES_DE_COMPARAR}</p>
      ) : (
        <Resultado key={comparado.vez} pagina={pagina} cnpjs={comparado.cnpjs} />
      )}
    </section>
  );
}
