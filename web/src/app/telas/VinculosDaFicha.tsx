// Vínculos da empresa na ficha (tela do analista, linha 798, PR 5): controle, coligação, participação e
// auditoria entre empresas, cada um com a fonte e o dia em que ficou público (POST /v1/analista/ficha/vinculos,
// com o CNPJ no corpo). Só empresa: o servidor não manda pessoa nem fundo, e o nome é o do dia da Receita.
// Sem dado liberado ou sem vínculos para o CNPJ, a seção diz isso em uma frase (estado da tela, nunca erro);
// qualquer falha some em silêncio, para uma lista a mais não derrubar a ficha. O tipo que o portão não libera
// não foi consultado e a seção diz isso (linha 889, o molde da linha 878 nos eventos). Cada tipo vai no
// masculino plural ("os vínculos de ..."): a frase concorda com um tipo ou com vários.
import { formatarData } from "../formatar";
import type { PontaDoVinculoV1, VinculoDaEmpresaV1, VinculosDaEmpresaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";

const CAMINHO = "/vinculos"; // depois da rota da ficha
const SEM_VALOR = "—";
const NOME_DO_TIPO: Record<string, string> = {
  subsidiary_of: "Controlada de",
  affiliate_of: "Coligada de",
  investee_of: "Participada de",
  audits: "Auditora de",
};
const TIPOS_NO_PLURAL: Record<string, string> = {
  subsidiary_of: "os vínculos de controle",
  affiliate_of: "os vínculos de coligação",
  investee_of: "os vínculos de participação",
  audits: "os vínculos de auditoria",
};

const valor = (vinculo: VinculoDaEmpresaV1, campo: string): string => {
  const v = vinculo.campos[campo]?.valor;
  return v === undefined || v === null || v === "" ? "" : String(v);
};

const ponta = (p: PontaDoVinculoV1): string => {
  const nome = p.razao_social?.valor ? String(p.razao_social.valor) : "";
  const raiz = p.raiz_do_cnpj ? `CNPJ ${p.raiz_do_cnpj}/…` : "";
  if (nome && raiz) return `${nome} (${raiz})`;
  return nome || raiz || SEM_VALOR;
};

const participacao = (vinculo: VinculoDaEmpresaV1): string => {
  const p = valor(vinculo, "participacao_no_capital");
  return p === "" ? SEM_VALOR : `${p}%`;
};

const desde = (vinculo: VinculoDaEmpresaV1): string => {
  const dia = valor(vinculo, "aconteceu_em");
  return /^\d{4}-\d{2}-\d{2}/.test(dia) ? formatarData(dia.slice(0, 10)) : SEM_VALOR;
};

const fonteEDia = (vinculo: VinculoDaEmpresaV1): { fonte: string; dia: string } => {
  const campos = Object.values(vinculo.campos);
  return {
    fonte: [...new Set(campos.map((c) => c.fonte))].join(", "),
    dia: [...new Set(campos.map((c) => formatarData(c.publico_em)))].join(", "),
  };
};

function Tabela({ vinculos }: { vinculos: VinculoDaEmpresaV1[] }) {
  return (
    <div className="tabela-rolavel">
      <table className="tabela-do-app">
        <thead>
          <tr>
            <th scope="col">Empresa</th>
            <th scope="col">Vínculo</th>
            <th scope="col">Com</th>
            <th scope="col">Participação</th>
            <th scope="col">Desde</th>
            <th scope="col">Fonte</th>
            <th scope="col">Publicado em</th>
          </tr>
        </thead>
        <tbody>
          {vinculos.map((vinculo, i) => {
            const { fonte, dia } = fonteEDia(vinculo);
            const tipo = valor(vinculo, "tipo");
            return (
              // a posição serve de chave: a lista vem pronta da API
              <tr key={i}>
                <th scope="row">{ponta(vinculo.de)}</th>
                <td>{NOME_DO_TIPO[tipo] ?? (tipo || SEM_VALOR)}</td>
                <td>{ponta(vinculo.para)}</td>
                <td>{participacao(vinculo)}</td>
                <td>{desde(vinculo)}</td>
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

export function VinculosDaFicha({ rota, cnpj }: { rota: string; cnpj: string }) {
  const pedido = usarPedido<VinculosDaEmpresaV1>(`${rota}${CAMINHO}`, {}, { cnpj });
  if (pedido.estado !== "pronto") return null; // carregando ou qualquer falha: a ficha segue sem a seção
  const dados = pedido.dados;
  // um tipo barrado não foi consultado: a lista vazia (ou curta) não pode parecer "a empresa não tem"
  const naoConsultados = (dados.tipos_de_vinculo_nao_disponiveis ?? []).map((tipo) => TIPOS_NO_PLURAL[tipo] ?? tipo);
  return (
    <section className="secao-do-relatorio" aria-labelledby="vinculos-da-ficha">
      <h2 id="vinculos-da-ficha">Vínculos com outras empresas</h2>
      {dados.estado === "nao_liberada" ? (
        <p className="apagado">Dado ainda não liberado: os vínculos da empresa entram quando a conferência terminar.</p>
      ) : dados.vinculos.length === 0 && naoConsultados.length > 0 ? (
        <p className="apagado">Nenhum vínculo dos tipos consultados.</p>
      ) : dados.vinculos.length === 0 ? (
        <p className="apagado">Sem vínculos desta empresa na base: só entram os que as companhias abertas declaram à CVM.</p>
      ) : (
        <Tabela vinculos={dados.vinculos} />
      )}
      {dados.estado === "pronta" && naoConsultados.length > 0 ? (
        <p>
          Não consultados, por ainda não estarem liberados para a tela: {naoConsultados.join(" e ")}. A falta deles
          aqui não quer dizer que a empresa não tenha.
        </p>
      ) : null}
      {dados.cortada ? <p className="apagado">A lista foi cortada no limite: há mais vínculos do que os mostrados.</p> : null}
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
