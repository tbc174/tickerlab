// Ficha da empresa (tela do analista, linha 798): o analista digita o CNPJ e vê o cadastro na Receita e,
// da companhia aberta, as entregas de balanço à CVM, cada campo com a fonte e o dia em que ficou público,
// e baixa tudo em Excel. A rota usa o mesmo leitor e o mesmo portão da API externa: o que a API negaria
// não aparece aqui. Como na Busca por CNPJ, o CNPJ vai no corpo do POST, nunca no endereço, e nada é
// pedido antes de a pessoa buscar. "Limites e cuidados" fica sempre à vista depois da busca.
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { useEstadoDaNavegacaoUmaVez } from "../estadoDaNavegacao";
import { formatarData } from "../formatar";
import { Abas } from "../pecas/Abas";
import { Baixar } from "../pecas/Baixar";
import { Cabecalho, CabecalhoDaTela } from "../pecas/Cabecalho";
import { CartaoDeNumero } from "../pecas/CartaoDeNumero";
import { Carregando } from "../pecas/Carregando";
import { Erro } from "../pecas/Erro";
import { Fonte, Fontes } from "../pecas/Fonte";
import { Limites } from "../pecas/Limites";
import { Selo } from "../pecas/Selo";
import type { BlocoDaFichaV1, FichaDaEmpresaV1, FichaDoCnpjV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ContatoDaFicha } from "./ContatoDaFicha";
import { EventosDaFicha } from "./EventosDaFicha";
import { SociosDaFicha } from "./SociosDaFicha";
import { TitularDaFicha } from "./TitularDaFicha";
import { VinculosDaFicha } from "./VinculosDaFicha";
import { fraseDoTopo, nomeDaEmpresa, numerosDoResumo } from "./resumoDaFicha";
import { SEM_VALOR, cnpjComPontuacao, nomeDoCampo, textoDoValor } from "./valoresDaFicha";

const NOME_DA_PLANILHA = "ficha-da-empresa-tickerlab.xlsx"; // sem o CNPJ: o nome do arquivo não carrega dado
export { cnpjComPontuacao, textoDoValor };
export const TAMANHO_MAXIMO_DO_CNPJ = 20; // com a pontuação cabem 18; sobra folga para espaços colados

// a lista dos campos do cadastro não consultados vem com o nome de fora da API (src/api_externa/nomes.py);
// a tela os mostra pelo nome da tabela acima. Campo sem par aparece com o nome de fora, nunca some; o
// teste tests/test_tela_ficha_campos_de_fora.py confere este mapa contra a API e os rótulos acima
const CHAVE_DO_CAMPO_DE_FORA: Record<string, string> = {
  registration_status: "situacao_cadastral",
  registration_status_date: "data_situacao_cadastral",
  registration_status_reason: "motivo_situacao",
  head_office: "matriz",
  snapshot_month: "mes_do_retrato",
  simples_nacional: "optante_simples",
  simples_nacional_since: "data_opcao_simples",
  simples_nacional_until: "data_exclusao_simples",
  legal_name: "razao_social",
  legal_nature_code: "natureza_juridica",
  registry_snapshot_month: "mes_do_retrato_do_cadastro",
};

/** "A", "A e B", "A, B e C". */
const juntarEmLista = (itens: string[]) =>
  itens.length < 2 ? itens.join("") : `${itens.slice(0, -1).join(", ")} e ${itens[itens.length - 1]}`;

/** Os campos não consultados na voz da tela, no masculino plural ("os dados do campo “X”" ou "os dados dos
 * campos “X” e “Y”"): a frase "Não consultados... A falta deles" concorda com um campo ou com vários. */
function camposNaoConsultados(deFora: string[]): string {
  const nomes = deFora.map((nome) => `“${nomeDoCampo(CHAVE_DO_CAMPO_DE_FORA[nome] ?? nome)}”`);
  return `os dados ${nomes.length === 1 ? "do campo" : "dos campos"} ${juntarEmLista(nomes)}`;
}

function Cadastro({ ficha }: { ficha: FichaDoCnpjV1 }) {
  // o campo barrado não foi consultado: a tabela sem ele não pode parecer "a empresa não tem" (linha 899)
  const deFora = ficha.campos_do_cadastro_nao_disponiveis ?? [];
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
      {deFora.length > 0 ? (
        <p>
          Não consultados, por ainda não estarem liberados para a tela: {camposNaoConsultados(deFora)}. A falta deles
          aqui não quer dizer que a empresa não tenha.
        </p>
      ) : null}
    </section>
  );
}

function Entregas({ ficha }: { ficha: FichaDoCnpjV1 }) {
  const entregas = ficha.entregas;
  // o documento barrado (DFP, ITR) não foi consultado: a lista vazia (ou curta) não pode parecer "não entregou"
  // cada documento vai no masculino plural ("os documentos ITR"): a frase concorda com um ou com vários
  const naoConsultados = (ficha.entregas_nao_disponiveis ?? []).map((documento) => `os documentos ${documento}`);
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
      ) : naoConsultados.length > 0 ? (
        <p className="apagado">Nenhuma entrega dos documentos consultados.</p>
      ) : (
        <p className="apagado">
          Sem entregas nesta ficha: só as companhias do cadastro de companhias abertas da CVM têm entregas na base.
        </p>
      )}
      {naoConsultados.length > 0 ? (
        <p>
          Não consultados, por ainda não estarem liberados para a tela: {naoConsultados.join(" e ")}. A falta deles
          aqui não quer dizer que a empresa não os tenha entregado.
        </p>
      ) : null}
    </section>
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

const ROTULO_DAS_ABAS = "Partes da ficha";
const PARAMETRO_DA_ABA = "aba"; // `?aba=cadastro`: o link copiado abre na mesma aba

/** A data de um número do Resumo no formato curto da peça `Fonte` ("03/11/2005"). */
const dataDaFonte = (publicoEm: string | null) => (publicoEm === null ? null : formatarData(publicoEm));

function Resumo({ ficha }: { ficha: FichaDoCnpjV1 }) {
  return (
    <section aria-label="Resumo da ficha">
      <p>{fraseDoTopo(ficha)}</p>
      <div className="numeros">
        {numerosDoResumo(ficha).map((numero) => (
          <CartaoDeNumero
            key={numero.rotulo}
            rotulo={numero.rotulo}
            valor={numero.valor}
            fonte={numero.fonte === null ? null : <Fonte nome={numero.fonte} data={dataDaFonte(numero.publicoEm)} />}
          />
        ))}
      </div>
    </section>
  );
}

/** Pessoa física: o servidor decide a cada pedido (permissão `pessoa_na_tela`); sem ela a aba fica sem nada e
 * sem aviso, para a tela não revelar que existe lista de pessoa (testes de duas organizações). */
function QuemControla({ rota, cnpj }: { rota: string; cnpj: string }) {
  return (
    <>
      <SociosDaFicha rota={rota} cnpj={cnpj} />
      <TitularDaFicha rota={rota} cnpj={cnpj} />
    </>
  );
}

function Sinais({ ficha }: { ficha: FichaDoCnpjV1 }) {
  return (
    <>
      <Entregas ficha={ficha} />
      <p className="apagado">
        Sanções, dívida ativa e autuações ambientais não são mostradas nesta ficha: a falta delas aqui não quer dizer
        que a empresa não as tenha.
      </p>
    </>
  );
}

function FontesELimites({ dados }: { dados: FichaDaEmpresaV1 }) {
  return (
    <>
      <Fontes fontes={dados.fontes} id="fontes-da-ficha" />
      <Limites itens={dados.limites} id="limites-da-ficha" />
    </>
  );
}

function abasDaFicha(dados: FichaDaEmpresaV1, ficha: FichaDoCnpjV1, rota: string, cnpj: string) {
  return [
    { chave: "resumo", rotulo: "Resumo", conteudo: <Resumo ficha={ficha} /> },
    {
      chave: "cadastro",
      rotulo: "Cadastro",
      conteudo: (
        <>
          <Cadastro ficha={ficha} />
          <ContatoDaFicha rota={rota} cnpj={cnpj} />
        </>
      ),
    },
    { chave: "quem_controla", rotulo: "Quem controla", conteudo: <QuemControla rota={rota} cnpj={cnpj} /> },
    { chave: "sinais", rotulo: "Sinais", conteudo: <Sinais ficha={ficha} /> },
    { chave: "eventos", rotulo: "Eventos", conteudo: <EventosDaFicha rota={rota} cnpj={cnpj} /> },
    { chave: "vinculos", rotulo: "Vínculos", conteudo: <VinculosDaFicha rota={rota} cnpj={cnpj} /> },
    { chave: "fontes", rotulo: "Fontes e limites", conteudo: <FontesELimites dados={dados} /> },
  ];
}

function SeloDaSituacao({ ficha }: { ficha: FichaDoCnpjV1 }) {
  const situacao = ficha.cadastro_na_receita.situacao_cadastral?.valor;
  if (situacao === undefined || situacao === null) return null;
  const ativa = String(situacao).padStart(2, "0") === "02";
  return <Selo tom={ativa ? "bom" : "atencao"}>{textoDoValor("situacao_cadastral", situacao)}</Selo>;
}

function Ficha({ dados, rota, cnpj }: { dados: FichaDaEmpresaV1; rota: string; cnpj: string }) {
  const ficha = dados.ficha;
  if (dados.estado === "nao_liberada") {
    return (
      <>
        <OQueVem blocos={dados.o_que_vem} />
        <Limites itens={dados.limites} id="limites-da-ficha" />
      </>
    );
  }
  if (ficha === null) {
    return (
      <>
        <p className="apagado" role="note">
          Ficha não disponível para este CNPJ.
        </p>
        <Limites itens={dados.limites} id="limites-da-ficha" />
      </>
    );
  }
  return (
    <>
      <Cabecalho
        olho="Empresas"
        titulo={nomeDaEmpresa(ficha) ?? `CNPJ ${cnpjComPontuacao(ficha.cnpj)}`}
        descricao={`CNPJ ${cnpjComPontuacao(ficha.cnpj)} · como a base conhecia em ${formatarData(ficha.como_era_em)}`}
        selos={<SeloDaSituacao ficha={ficha} />}
        acoes={
          <>
            <Baixar rotulo="Baixar em Excel" rota={`${rota}/planilha`} corpo={{ cnpj }} nome={NOME_DA_PLANILHA} />
            {/* o CNPJ vai pelo estado da navegação, nunca pelo endereço */}
            <Link className="botao" to="/comparar-empresas" state={{ cnpjs: [ficha.cnpj] }}>
              Pôr na comparação
            </Link>
          </>
        }
      />
      <Abas rotulo={ROTULO_DAS_ABAS} abas={abasDaFicha(dados, ficha, rota, cnpj)} parametro={PARAMETRO_DA_ABA} />
    </>
  );
}

function Resultado({
  pagina,
  cnpj,
  aoFicarPronta,
}: {
  pagina: PaginaDoApp;
  cnpj: string;
  aoFicarPronta: (pronta: boolean) => void;
}) {
  const rota = pagina.contrato?.rota ?? "";
  const pedido = usarPedido<FichaDaEmpresaV1>(rota, {}, { cnpj });
  const pronta = pedido.estado === "pronto" && pedido.dados.ficha !== null;
  // a ficha pronta traz o próprio título (o nome da empresa): o título da página sai para não haver dois h1
  useEffect(() => {
    aoFicarPronta(pronta);
    return () => aoFicarPronta(false);
  }, [pronta, aoFicarPronta]);
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Montando a ficha da empresa…" />;
  if (pedido.estado === "erro") return <Erro erro={pedido.erro} />;
  return <Ficha dados={pedido.dados} rota={rota} cnpj={cnpj} />;
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
  const vindo = cnpjDaNavegacao(useEstadoDaNavegacaoUmaVez());
  const [rascunho, setRascunho] = useState(vindo ?? "");
  const [fichaPronta, setFichaPronta] = useState(false);
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
      {fichaPronta ? null : <CabecalhoDaTela pagina={pagina} />}
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
        <Resultado key={buscado.vez} pagina={pagina} cnpj={buscado.cnpj} aoFicarPronta={setFichaPronta} />
      )}
    </section>
  );
}
