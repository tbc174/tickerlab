// A análise completa da empresa na ficha (19/11/2026): a mesma montagem da rota /analysis da API e da ferramenta
// do conector, pelo portão da tela (POST /v1/analista/ficha/analise, com o CNPJ no corpo). A tela não faz conta:
// mostra a frase do topo, cada bloco com o título, o que ele traz e cada valor com a fonte e o dia em que ficou
// público, a linha do tempo, as leituras (dedução do TickerLab, à parte dos fatos), o que não foi achado e o que
// esta tela não consulta. Sem pessoa física: o servidor só manda empresa e sócio pessoa jurídica.
// O corpo de cada bloco é o do leitor da API, de formas diferentes por bloco; a tela o percorre sem conhecer o
// bloco: campo no envelope {valor, fonte, publico_em}, grupo de campos (vira lista de definições) ou lista de
// linhas (vira tabela). Assim, bloco novo na montagem aparece sem mudar esta tela.
import { formatarData } from "../formatar";
import { Carregando } from "../pecas/Carregando";
import { Erro } from "../pecas/Erro";
import { Fontes } from "../pecas/Fonte";
import { Limites } from "../pecas/Limites";
import type { AnaliseCompletaV1, BlocoDaAnaliseCompletaV1, CampoComFonteV1, FonteDaFichaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { SEM_VALOR, nomeDoCampo, textoDoValor } from "./valoresDaFicha";

const CAMINHO = "/analise"; // depois da rota da ficha
const CORTADA = "cortada"; // marca do leitor: a lista parou no limite de linhas

type NomesDasFontes = Record<string, string>;

const ehEnvelope = (valor: unknown): valor is CampoComFonteV1 =>
  typeof valor === "object" && valor !== null && !Array.isArray(valor) && "valor" in valor && "fonte" in valor;

const ehObjeto = (valor: unknown): valor is Record<string, unknown> =>
  typeof valor === "object" && valor !== null && !Array.isArray(valor);

// "Fonte: Receita Federal, dados abertos do CNPJ (CC BY)" → "Receita Federal, dados abertos do CNPJ (CC BY)"
const nomesDasFontes = (fontes: FonteDaFichaV1[]): NomesDasFontes =>
  Object.fromEntries(fontes.map((f) => [f.fonte, f.atribuicao.replace(/^Fonte:\s*/, "")]));

const nomeDaFonte = (nomes: NomesDasFontes, fonte: string) => nomes[fonte] ?? fonte;

/** Os envelopes de uma linha, inclusive os de dentro de um campo composto (a outra ponta, por exemplo). */
function envelopesDe(valor: unknown): CampoComFonteV1[] {
  if (ehEnvelope(valor)) return [valor];
  if (Array.isArray(valor)) return valor.flatMap(envelopesDe);
  if (ehObjeto(valor)) return Object.values(valor).flatMap(envelopesDe);
  return [];
}

const unicos = (textos: string[]) => [...new Set(textos.filter((t) => t !== ""))].join(", ");

function fonteEDia(valor: unknown, nomes: NomesDasFontes) {
  const envelopes = envelopesDe(valor);
  return {
    fonte: unicos(envelopes.map((e) => nomeDaFonte(nomes, e.fonte))),
    dia: unicos(envelopes.map((e) => (e.publico_em ? formatarData(e.publico_em) : ""))),
  };
}

/** O texto de uma célula: o valor do envelope, o texto simples ou os valores de um campo composto. */
function textoDaCelula(chave: string, valor: unknown): string {
  if (valor === undefined || valor === null || valor === "") return SEM_VALOR;
  if (ehEnvelope(valor)) return textoDoValor(chave, valor.valor);
  if (Array.isArray(valor)) return valor.map((item) => textoDaCelula(chave, item)).join("; ") || SEM_VALOR;
  if (ehObjeto(valor)) {
    const partes = Object.entries(valor).map(([k, v]) => textoDaCelula(k, v));
    return partes.filter((p) => p !== SEM_VALOR).join(" · ") || SEM_VALOR;
  }
  return textoDoValor(chave, valor as CampoComFonteV1["valor"]);
}

function Grupo({ campos, nomes }: { campos: Record<string, unknown>; nomes: NomesDasFontes }) {
  return (
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
          {Object.entries(campos).map(([chave, valor]) => {
            const { fonte, dia } = fonteEDia(valor, nomes);
            return (
              <tr key={chave}>
                <th scope="row">{nomeDoCampo(chave)}</th>
                <td>{textoDaCelula(chave, valor)}</td>
                <td>{fonte || SEM_VALOR}</td>
                <td>{dia || SEM_VALOR}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Linhas({ linhas, nomes }: { linhas: Record<string, unknown>[]; nomes: NomesDasFontes }) {
  const colunas = [...new Set(linhas.flatMap((linha) => Object.keys(linha)))];
  return (
    <div className="tabela-rolavel">
      <table className="tabela-do-app">
        <thead>
          <tr>
            {colunas.map((coluna) => (
              <th scope="col" key={coluna}>
                {nomeDoCampo(coluna)}
              </th>
            ))}
            <th scope="col">Fonte</th>
            <th scope="col">Publicado em</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha, i) => {
            const { fonte, dia } = fonteEDia(linha, nomes);
            return (
              // a posição serve de chave: a lista vem pronta da API
              <tr key={i}>
                {colunas.map((coluna) => (
                  <td key={coluna}>{textoDaCelula(coluna, linha[coluna])}</td>
                ))}
                <td>{fonte || SEM_VALOR}</td>
                <td>{dia || SEM_VALOR}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Uma parte do corpo do bloco: um grupo de campos, uma lista de linhas, uma lista de nomes ou um valor só. */
function Parte({ chave, valor, nomes }: { chave: string; valor: unknown; nomes: NomesDasFontes }) {
  if (chave === CORTADA) {
    return valor === true ? <p className="apagado">A lista parou no limite: a aba do bloco na ficha traz o resto.</p> : null;
  }
  if (Array.isArray(valor)) {
    if (valor.length === 0) return null; // lista vazia: o bloco já diz o que não foi achado
    const titulo = <h4>{nomeDoCampo(chave)}</h4>;
    if (valor.every(ehObjeto)) {
      return (
        <>
          {titulo}
          <Linhas linhas={valor} nomes={nomes} />
        </>
      );
    }
    return (
      <p>
        <strong>{nomeDoCampo(chave)}:</strong> {valor.map((item) => nomeDoCampo(String(item))).join(", ")}
      </p>
    );
  }
  if (ehObjeto(valor) && !ehEnvelope(valor)) {
    return (
      <>
        <h4>{nomeDoCampo(chave)}</h4>
        <Grupo campos={valor} nomes={nomes} />
      </>
    );
  }
  return <Grupo campos={{ [chave]: valor }} nomes={nomes} />;
}

function Bloco({ bloco, nomes }: { bloco: BlocoDaAnaliseCompletaV1; nomes: NomesDasFontes }) {
  const id = `analise-${bloco.nome}`;
  return (
    <section className="secao-do-relatorio" aria-labelledby={id}>
      <h3 id={id}>{bloco.titulo}</h3>
      {bloco.o_que_traz ? <p className="apagado">{bloco.o_que_traz}</p> : null}
      {Object.entries(bloco.corpo).map(([chave, valor]) => (
        <Parte key={chave} chave={chave} valor={valor} nomes={nomes} />
      ))}
    </section>
  );
}

function LinhaDoTempo({ dados, nomes }: { dados: AnaliseCompletaV1; nomes: NomesDasFontes }) {
  if (dados.linha_do_tempo.length === 0) return null;
  return (
    <section className="secao-do-relatorio" aria-labelledby="analise-linha-do-tempo">
      <h3 id="analise-linha-do-tempo">Linha do tempo</h3>
      <div className="tabela-rolavel">
        <table className="tabela-do-app">
          <thead>
            <tr>
              <th scope="col">Dia</th>
              <th scope="col">O que aconteceu</th>
              <th scope="col">Bloco</th>
              <th scope="col">Fonte</th>
              <th scope="col">Publicado em</th>
            </tr>
          </thead>
          <tbody>
            {dados.linha_do_tempo.map((marco, i) => (
              <tr key={i}>
                <td>{formatarData(marco.dia)}</td>
                <td>{marco.o_que}</td>
                <td>{marco.titulo_do_bloco}</td>
                <td>{marco.fonte ? nomeDaFonte(nomes, marco.fonte) : SEM_VALOR}</td>
                <td>{marco.publico_em ? formatarData(marco.publico_em) : SEM_VALOR}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Leituras({ dados }: { dados: AnaliseCompletaV1 }) {
  if (dados.leituras.length === 0) return null;
  const titulos = Object.fromEntries(dados.blocos.map((b) => [b.nome, b.titulo]));
  return (
    <section className="secao-do-relatorio" aria-labelledby="analise-leituras">
      <h3 id="analise-leituras">Leituras (dedução do TickerLab, não fato de uma fonte)</h3>
      <ul>
        {dados.leituras.map((leitura) => (
          <li key={leitura.texto}>
            {leitura.texto}{" "}
            <span className="apagado">(a partir de: {leitura.a_partir_de.map((n) => titulos[n] ?? n).join(", ")})</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function OQueFalta({ dados }: { dados: AnaliseCompletaV1 }) {
  const semDado = [...dados.nao_encontrado, ...dados.nao_respondeu_a_tempo];
  return (
    <section className="secao-do-relatorio" aria-labelledby="analise-o-que-falta">
      <h3 id="analise-o-que-falta">O que não foi achado ou não foi consultado</h3>
      {semDado.length > 0 ? (
        <ul>
          {semDado.map((item) => (
            <li key={item.bloco}>
              <strong>{item.titulo}:</strong> {item.por_que}
            </li>
          ))}
        </ul>
      ) : null}
      {dados.ainda_nao_traz.length > 0 ? (
        <>
          <h4>Não consultado nesta tela</h4>
          <ul>
            {dados.ainda_nao_traz.map((texto) => (
              <li key={texto}>{texto}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function Pronta({ dados }: { dados: AnaliseCompletaV1 }) {
  const nomes = nomesDasFontes(dados.fontes);
  return (
    <>
      {dados.frase ? (
        <p>
          <strong>{dados.frase.texto}</strong>
        </p>
      ) : null}
      {dados.como_era_em ? (
        <p className="apagado">Como a base conhecia a empresa em {formatarData(dados.como_era_em)}.</p>
      ) : null}
      {dados.blocos.map((bloco) => (
        <Bloco key={bloco.nome} bloco={bloco} nomes={nomes} />
      ))}
      <LinhaDoTempo dados={dados} nomes={nomes} />
      <Leituras dados={dados} />
      <OQueFalta dados={dados} />
    </>
  );
}

function Conteudo({ dados }: { dados: AnaliseCompletaV1 }) {
  return (
    <>
      {/* dado de piloto nunca aparece sem o aviso (D11.3): a frase vem do servidor */}
      {dados.aviso_de_piloto ? (
        <p className="erro-do-app" role="note">
          {dados.aviso_de_piloto}
        </p>
      ) : null}
      {dados.estado === "nao_liberada" ? (
        <p className="apagado" role="note">
          Análise não disponível: os dados dela ainda não foram liberados para a tela.
        </p>
      ) : dados.estado === "nao_disponivel" ? (
        <p className="apagado" role="note">
          Análise não disponível para este CNPJ.
        </p>
      ) : (
        <Pronta dados={dados} />
      )}
      <Fontes fontes={dados.fontes} id="fontes-da-analise" />
      <Limites itens={dados.limites} id="limites-da-analise" />
    </>
  );
}

export function AnaliseDaFicha({ rota, cnpj }: { rota: string; cnpj: string }) {
  const pedido = usarPedido<AnaliseCompletaV1>(`${rota}${CAMINHO}`, {}, { cnpj });
  return (
    <section aria-labelledby="analise-da-ficha">
      <h2 id="analise-da-ficha">Análise completa</h2>
      {pedido.estado === "carregando" ? (
        <Carregando tipo="lista" rotulo="Montando a análise completa" />
      ) : pedido.estado === "erro" ? (
        <Erro erro={pedido.erro} />
      ) : (
        <Conteudo dados={pedido.dados} />
      )}
    </section>
  );
}
