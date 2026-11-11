// Ficha da empresa (tela do analista, linha 798): o analista digita o CNPJ e vê o cadastro na Receita e,
// da companhia aberta, as entregas de balanço à CVM, cada campo com a fonte e o dia em que ficou público,
// e baixa tudo em Excel. A rota usa o mesmo leitor e o mesmo portão da API externa: o que a API negaria
// não aparece aqui. Como na Busca por CNPJ, o CNPJ vai no corpo do POST, nunca no endereço, e nada é
// pedido antes de a pessoa buscar. "Limites e cuidados" fica sempre à vista depois da busca.
import { type FormEvent, useState } from "react";
import { Link, useLocation } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import { ErroDaApi, baixar } from "../api";
import { Carregando } from "../Carregando";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import type { BlocoDaFichaV1, CampoComFonteV1, FichaDaEmpresaV1, FichaDoCnpjV1, FonteDaFichaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";
import { EventosDaFicha } from "./EventosDaFicha";
import { SociosDaFicha } from "./SociosDaFicha";

const NOME_DA_PLANILHA = "ficha-da-empresa-tickerlab.xlsx"; // sem o CNPJ: o nome do arquivo não carrega dado
export const TAMANHO_MAXIMO_DO_CNPJ = 20; // com a pontuação cabem 18; sobra folga para espaços colados
const SEM_VALOR = "—";

// o nome de cada campo na tela; campo novo sem nome aparece com a chave, nunca some
const NOMES_DOS_CAMPOS: Record<string, string> = {
  razao_social: "Razão social",
  situacao_cadastral: "Situação cadastral",
  data_situacao_cadastral: "Data da situação",
  motivo_situacao: "Motivo da situação (código da Receita)",
  natureza_juridica: "Natureza jurídica (código da Receita)",
  matriz: "Matriz",
  optante_simples: "Optante pelo Simples",
  data_opcao_simples: "Entrou no Simples em",
  data_exclusao_simples: "Saiu do Simples em",
  mes_do_retrato: "Mês do cadastro",
  documento: "Documento",
  referencia: "Referência",
  prazo: "Prazo",
  primeira_entrega: "Primeira entrega",
  dias_uteis_de_atraso: "Dias úteis de atraso",
  situacao_da_entrega: "Situação da entrega",
};

// os cinco códigos do dicionário de dados do CNPJ (base/receita_codigos.py)
const SITUACOES_CADASTRAIS: Record<string, string> = {
  "01": "Nula",
  "02": "Ativa",
  "03": "Suspensa",
  "04": "Inapta",
  "08": "Baixada",
};

// a regra do TickerLab sobre o índice da CVM (src/api_externa/conjuntos/ficha.py)
const SITUACOES_DA_ENTREGA: Record<string, string> = {
  on_time: "No prazo",
  late: "Atrasou",
  gray_zone: "Atraso curto (um feriado local pode explicar)",
  severely_late: "Atraso grave",
  not_filed: "Não entregue",
};

const DATA_ISO = /^\d{4}-\d{2}-\d{2}$/;
const MES_ISO = /^(\d{4})-(\d{2})$/;
const CNPJ_SO_DIGITOS = /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/;

/** "02429144000193" → "02.429.144/0001-93", como o analista digita; outro formato sai como veio. */
export const cnpjComPontuacao = (cnpj: string) => cnpj.replace(CNPJ_SO_DIGITOS, "$1.$2.$3/$4-$5");

const nomeDoCampo = (chave: string) => NOMES_DOS_CAMPOS[chave] ?? chave;

export function textoDoValor(chave: string, valor: CampoComFonteV1["valor"]): string {
  if (valor === null) return SEM_VALOR;
  if (typeof valor === "boolean") return valor ? "Sim" : "Não";
  const texto = String(valor);
  if (chave === "situacao_cadastral") return SITUACOES_CADASTRAIS[texto.padStart(2, "0")] ?? `código ${texto}`;
  if (chave === "situacao_da_entrega") return SITUACOES_DA_ENTREGA[texto] ?? texto;
  if (DATA_ISO.test(texto)) return formatarData(texto);
  return texto.replace(MES_ISO, "$2/$1"); // "2026-09" → "09/2026" (o mês do cadastro)
}

function Cadastro({ ficha }: { ficha: FichaDoCnpjV1 }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby="cadastro-da-ficha">
      <h2 id="cadastro-da-ficha">Cadastro na Receita</h2>
      <div className="tabela-rolavel">
        <table className="tabela-do-app">
          <thead>
            <tr>
              <th scope="col">Campo</th>
              <th scope="col">Valor</th>
              <th scope="col">Fonte</th>
              <th scope="col">Publicado em</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(ficha.cadastro_na_receita).map(([chave, campo]) => (
              <tr key={chave}>
                <th scope="row">{nomeDoCampo(chave)}</th>
                <td>{textoDoValor(chave, campo.valor)}</td>
                <td>{campo.fonte}</td>
                <td>{formatarData(campo.publico_em)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Entregas({ entregas }: { entregas: Record<string, CampoComFonteV1>[] | null | undefined }) {
  const colunas = [...new Set((entregas ?? []).flatMap((entrega) => Object.keys(entrega)))];
  return (
    <section className="secao-do-relatorio" aria-labelledby="entregas-da-ficha">
      <h2 id="entregas-da-ficha">Entregas de balanço à CVM</h2>
      {entregas && entregas.length > 0 ? (
        <div className="tabela-rolavel">
          <table className="tabela-do-app">
            <thead>
              <tr>
                {colunas.map((coluna) => (
                  <th key={coluna} scope="col">
                    {nomeDoCampo(coluna)}
                  </th>
                ))}
                <th scope="col">Fonte</th>
                <th scope="col">Publicado em</th>
              </tr>
            </thead>
            <tbody>
              {entregas.map((entrega, i) => {
                const campos = Object.values(entrega);
                return (
                  // a posição serve de chave: a lista vem pronta da API e não muda de ordem na tela
                  <tr key={i}>
                    {colunas.map((coluna) => (
                      <td key={coluna}>{entrega[coluna] ? textoDoValor(coluna, entrega[coluna].valor) : SEM_VALOR}</td>
                    ))}
                    <td>{[...new Set(campos.map((c) => c.fonte))].join(", ")}</td>
                    <td>{[...new Set(campos.map((c) => formatarData(c.publico_em)))].join(", ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="apagado">
          Sem entregas nesta ficha: só as companhias do cadastro de companhias abertas da CVM têm entregas na base.
        </p>
      )}
    </section>
  );
}

export function Fontes({ fontes }: { fontes: FonteDaFichaV1[] }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby="fontes-da-ficha">
      <h2 id="fontes-da-ficha">Fontes</h2>
      <ul>
        {fontes.map((fonte) => (
          <li key={fonte.fonte}>
            {fonte.atribuicao} <span className="apagado">({fonte.fonte}; licença: {fonte.licenca})</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Limites({ itens }: { itens: string[] }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby="limites-da-ficha">
      <h2 id="limites-da-ficha">Limites e cuidados</h2>
      <ul>
        {itens.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

/** O botão do Excel: pede `${rota}/planilha` com o mesmo corpo da tela e salva com um nome sem dado. */
export function BaixarPlanilha({ rota, corpo, nome }: { rota: string; corpo: object; nome: string }) {
  const token = useConta()?.token ?? null;
  const [baixando, setBaixando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const baixarAgora = () => {
    if (token === null) return;
    setBaixando(true);
    setFalha(null);
    baixar(`${rota}/planilha`, token, corpo)
      .then((arquivo) => {
        const endereco = URL.createObjectURL(arquivo);
        const ancora = document.createElement("a");
        ancora.href = endereco;
        ancora.download = nome;
        ancora.click();
        URL.revokeObjectURL(endereco);
      })
      .catch((erro: unknown) =>
        setFalha(erro instanceof ErroDaApi ? erro.message : "Não deu agora. Tente de novo em instantes."),
      )
      .finally(() => setBaixando(false));
  };
  return (
    <>
      <button type="button" className="botao" disabled={baixando} onClick={baixarAgora}>
        Baixar em Excel
      </button>
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </>
  );
}

/** Enquanto o dado não é liberado: o que a ficha vai trazer, bloco a bloco, com a fonte de cada um. */
function OQueVem({ blocos }: { blocos: BlocoDaFichaV1[] }) {
  return (
    <>
      <p className="apagado" role="note">
        Dado ainda não liberado: a ficha entra nesta tela quando a conferência da tabela terminar.
      </p>
      {blocos.length > 0 ? (
        <section aria-label="O que a ficha vai trazer">
          <h2>O que a ficha vai trazer</h2>
          <ul className="telas-do-app">
            {blocos.map((bloco) => (
              <li key={bloco.titulo} className="cartao">
                <strong>{bloco.titulo}</strong>
                <p>{bloco.o_que_traz}</p>
                <p className="apagado">Fonte: {bloco.fonte}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

function Ficha({ dados, rota, cnpj }: { dados: FichaDaEmpresaV1; rota: string; cnpj: string }) {
  if (dados.estado === "nao_liberada") return <OQueVem blocos={dados.o_que_vem} />;
  if (dados.ficha === null) {
    return (
      <p className="apagado" role="note">
        Ficha não disponível para este CNPJ.
      </p>
    );
  }
  const ficha = dados.ficha;
  return (
    <>
      <p>
        CNPJ {cnpjComPontuacao(ficha.cnpj)}
        <span className="apagado"> · como a base conhecia em {formatarData(ficha.como_era_em)}</span>
      </p>
      <div className="acoes-da-ficha">
        <BaixarPlanilha rota={rota} corpo={{ cnpj }} nome={NOME_DA_PLANILHA} />
        {/* o CNPJ vai pelo estado da navegação, nunca pelo endereço */}
        <Link className="botao" to="/comparar-empresas" state={{ cnpjs: [ficha.cnpj] }}>
          Pôr na comparação
        </Link>
      </div>
      <Cadastro ficha={ficha} />
      <SociosDaFicha rota={rota} cnpj={cnpj} />
      <Entregas entregas={ficha.entregas} />
      <EventosDaFicha rota={rota} cnpj={cnpj} />
      {dados.fontes.length > 0 ? <Fontes fontes={dados.fontes} /> : null}
    </>
  );
}

function Resultado({ pagina, cnpj }: { pagina: PaginaDoApp; cnpj: string }) {
  const rota = pagina.contrato?.rota ?? "";
  const pedido = usarPedido<FichaDaEmpresaV1>(rota, {}, { cnpj });
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Montando a ficha da empresa…" />;
  if (pedido.estado === "erro") return <ErroDaTela erro={pedido.erro} />;
  return (
    <>
      <Ficha dados={pedido.dados} rota={rota} cnpj={cnpj} />
      <Limites itens={pedido.dados.limites} />
    </>
  );
}

// antes da primeira busca os limites não vêm da API; este é o resumo fixo da tela
const ANTES_DA_BUSCA =
  "A ficha mostra o cadastro da Receita Federal e, das companhias abertas, as entregas de balanço à CVM, com a fonte e a data de cada campo. Pessoa física, MEI e empresário individual não aparecem. Nada aqui é recomendação de investimento.";

/** O CNPJ que a tela "Encontrar empresas" manda pelo estado da navegação (nunca pelo endereço), se veio. */
function cnpjDaNavegacao(estado: unknown): string | null {
  const cnpj = (estado as { cnpj?: unknown } | null)?.cnpj;
  return typeof cnpj === "string" && cnpj !== "" ? cnpj : null;
}

export function FichaDaEmpresa({ pagina }: { pagina: PaginaDoApp }) {
  const vindo = cnpjDaNavegacao(useLocation().state);
  const [rascunho, setRascunho] = useState(vindo ?? "");
  const [buscado, setBuscado] = useState<{ cnpj: string; vez: number } | null>(
    vindo === null ? null : { cnpj: vindo, vez: 1 },
  );
  const buscar = (evento: FormEvent) => {
    evento.preventDefault();
    const cnpj = rascunho.trim();
    if (cnpj !== "") setBuscado({ cnpj, vez: (buscado?.vez ?? 0) + 1 });
  };
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      <form className="formulario-do-app" onSubmit={buscar}>
        <div className="campos-do-formulario">
          <label>
            <span>CNPJ</span>
            <input
              value={rascunho}
              onChange={(ev) => setRascunho(ev.target.value)}
              required
              type="text"
              inputMode="text"
              autoComplete="off"
              maxLength={TAMANHO_MAXIMO_DO_CNPJ}
              placeholder="00.000.000/0000-00"
            />
          </label>
        </div>
        <button className="botao primario" type="submit">
          Ver a ficha
        </button>
      </form>
      {buscado === null ? (
        <p className="apagado">{ANTES_DA_BUSCA}</p>
      ) : (
        <Resultado key={buscado.vez} pagina={pagina} cnpj={buscado.cnpj} />
      )}
    </section>
  );
}
