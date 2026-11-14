// Eventos da empresa na ficha (tela do analista, linha 798, PR 4): os documentos que a companhia aberta
// entregou à CVM e as trocas de auditor, do mais novo ao mais velho, cada um com a fonte e o dia em que
// ficou público (POST /v1/analista/ficha/eventos, com o CNPJ no corpo). A primeira página vem sozinha;
// "Carregar mais" pede a seguinte com o cursor da anterior. O assunto livre do documento e o auditor que
// pode ser pessoa física nunca chegam: o servidor não os manda. Sem dado liberado ou sem eventos para o
// CNPJ, a seção diz isso em uma frase (estado da tela, nunca erro); qualquer falha some em silêncio, para
// uma lista a mais não derrubar a ficha.
import { useEffect, useState } from "react";
import { pedir } from "../api";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import type { EventoDaEmpresaV1, EventosDaEmpresaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";

const CAMINHO = "/eventos"; // depois da rota da ficha
const SEM_VALOR = "—";
const NOME_DO_TIPO: Record<string, string> = {
  ipe_filing: "Documento à CVM",
  auditor_change: "Troca de auditor",
};
// no plural, para o aviso dos tipos que o portão não libera (linha 878)
const TIPOS_NO_PLURAL: Record<string, string> = {
  ipe_filing: "os documentos à CVM",
  auditor_change: "os eventos de troca de auditor", // no masculino plural: "Não consultados... A falta deles"
};
const LINK_SEGURO = /^https:\/\//;

const valor = (evento: EventoDaEmpresaV1, campo: string): string => {
  const v = evento.campos[campo]?.valor;
  return v === undefined || v === null || v === "" ? "" : String(v);
};

const dataDoEvento = (evento: EventoDaEmpresaV1): string => {
  const dia = valor(evento, evento.tipo === "auditor_change" ? "efetiva_em" : "referencia");
  return /^\d{4}-\d{2}-\d{2}/.test(dia) ? formatarData(dia.slice(0, 10)) : SEM_VALOR;
};

const descricao = (evento: EventoDaEmpresaV1): string => {
  if (evento.tipo === "auditor_change") {
    const anterior = valor(evento, "anterior") || SEM_VALOR;
    return `${anterior} → ${valor(evento, "novo") || SEM_VALOR}`;
  }
  return [valor(evento, "categoria"), valor(evento, "tipo")].filter(Boolean).join(" · ") || SEM_VALOR;
};

const fonteEDia = (evento: EventoDaEmpresaV1): { fonte: string; dia: string } => {
  const campos = Object.values(evento.campos);
  return {
    fonte: [...new Set(campos.map((c) => c.fonte))].join(", "),
    dia: [...new Set(campos.map((c) => formatarData(c.publico_em)))].join(", "),
  };
};

function Tabela({ eventos }: { eventos: EventoDaEmpresaV1[] }) {
  return (
    <div className="tabela-rolavel">
      <table className="tabela-do-app">
        <thead>
          <tr>
            <th scope="col">Evento</th>
            <th scope="col">Data</th>
            <th scope="col">O que é</th>
            <th scope="col">Fonte</th>
            <th scope="col">Publicado em</th>
          </tr>
        </thead>
        <tbody>
          {eventos.map((evento, i) => {
            const { fonte, dia } = fonteEDia(evento);
            const link = valor(evento, "link");
            return (
              // a posição serve de chave: a lista vem pronta da API e só cresce no fim
              <tr key={i}>
                <th scope="row">{NOME_DO_TIPO[evento.tipo] ?? evento.tipo}</th>
                <td>{dataDoEvento(evento)}</td>
                <td>
                  {descricao(evento)}
                  {LINK_SEGURO.test(link) ? (
                    <>
                      {" "}
                      <a href={link} target="_blank" rel="noopener noreferrer">
                        abrir
                      </a>
                    </>
                  ) : null}
                </td>
                <td>{fonte}</td>
                <td>{dia}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function EventosDaFicha({ rota, cnpj }: { rota: string; cnpj: string }) {
  const token = useConta()?.token ?? null;
  const rotaDosEventos = `${rota}${CAMINHO}`;
  const primeira = usarPedido<EventosDaEmpresaV1>(rotaDosEventos, {}, { cnpj });
  // as páginas seguintes levam o CNPJ de que vieram: uma resposta atrasada de outra empresa nunca entra na lista
  const [seguintes, setSeguintes] = useState<{ cnpj: string; pagina: EventosDaEmpresaV1 }[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [falhou, setFalhou] = useState(false);

  // outro CNPJ (ou nova primeira página): as páginas seguintes da anterior não valem mais
  useEffect(() => {
    setSeguintes([]);
    setFalhou(false);
  }, [cnpj]);

  if (primeira.estado !== "pronto") return null; // carregando ou qualquer falha: a ficha segue sem a seção
  const dados = primeira.dados;
  const todas = [dados, ...seguintes.filter((s) => s.cnpj === cnpj).map((s) => s.pagina)];
  const eventos = todas.flatMap((pagina) => pagina.eventos);
  const cursor = todas[todas.length - 1]?.proximo_cursor ?? null;
  // um tipo barrado não foi consultado: a lista vazia (ou curta) não pode parecer "a empresa não tem"
  const naoConsultados = (dados.tipos_nao_disponiveis ?? []).map((tipo) => TIPOS_NO_PLURAL[tipo] ?? tipo);

  async function carregarMais() {
    if (token === null || cursor === null) return;
    setCarregando(true);
    setFalhou(false);
    try {
      const pagina = await pedir<EventosDaEmpresaV1>(rotaDosEventos, token, {}, { cnpj, cursor });
      setSeguintes((anteriores) => [...anteriores, { cnpj, pagina }]);
    } catch {
      setFalhou(true);
    } finally {
      setCarregando(false);
    }
  }

  return (
    <section className="secao-do-relatorio" aria-labelledby="eventos-da-ficha">
      <h2 id="eventos-da-ficha">Documentos à CVM e trocas de auditor</h2>
      {dados.estado === "nao_liberada" ? (
        <p className="apagado">Dado ainda não liberado: os eventos da empresa entram quando a conferência terminar.</p>
      ) : eventos.length === 0 && naoConsultados.length > 0 ? (
        <p className="apagado">Nenhum evento dos tipos consultados.</p>
      ) : eventos.length === 0 ? (
        <p className="apagado">Sem eventos desta empresa na base: só as companhias abertas entregam documentos à CVM.</p>
      ) : (
        <Tabela eventos={eventos} />
      )}
      {dados.estado === "pronta" && naoConsultados.length > 0 ? (
        <p>
          Não consultados, por ainda não estarem liberados para a tela: {naoConsultados.join(" e ")}. A falta deles
          aqui não quer dizer que a empresa não tenha.
        </p>
      ) : null}
      {cursor !== null ? (
        <p>
          <button type="button" className="botao" onClick={carregarMais} disabled={carregando}>
            {carregando ? "Carregando…" : "Carregar mais"}
          </button>
          {falhou ? <span className="apagado"> Não deu para carregar agora. Tente de novo.</span> : null}
        </p>
      ) : null}
      {dados.estado === "pronta" && dados.fontes.length > 0 ? (
        <p className="apagado">Fontes: {dados.fontes.map((f) => `${f.atribuicao} (${f.fonte})`).join("; ")}.</p>
      ) : null}
      <ul className="apagado">
        {dados.limites.map((limite) => (
          <li key={limite}>{limite}</li>
        ))}
      </ul>
    </section>
  );
}
