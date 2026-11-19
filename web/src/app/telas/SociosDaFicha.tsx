// Sócios pessoa física da empresa da ficha (linha 808; ADR 0128, Emenda 1): nome, qualificação e data de
// entrada, do cadastro público da Receita. Quem decide se a conta vê é o servidor, a cada pedido: só a
// organização com a permissão `pessoa_na_tela` recebe a lista (POST /v1/analista/ficha/pessoas, com o CNPJ
// no corpo). Para as outras contas a rota responde o 404 de um endereço que não existe, e este componente
// não desenha nada. O mesmo vale para qualquer outra falha: a ficha não pode quebrar, nem ganhar um aviso
// sobre sócios, por causa de uma lista que a conta talvez nem possa ver. Nada de pessoa vem no pacote do
// app: os nomes só existem na resposta da API.
import { formatarData } from "../formatar";
import { usarPedido } from "../usarPedido";

export type SocioDaEmpresaV1 = {
  nome: string;
  qualificacao: string;
  entrou_em: string | null; // AAAA-MM-DD
};

/** A resposta de POST /v1/analista/ficha/pessoas (src/api_v1/analista_pessoas.py). */
export type SociosDaEmpresaV1 = {
  estado: "pronta" | "sem_socios";
  socios: SocioDaEmpresaV1[];
  total: number; // a lista pode vir cortada: `total` diz quantos são
  fonte: { fonte: string; atribuicao: string; mes_do_retrato: string | null }; // mês em AAAA-MM
  limites: string[];
};

const CAMINHO = "/pessoas"; // depois da rota da ficha
const SEM_DATA = "—";
const MES_ISO = /^(\d{4})-(\d{2})$/;

function Lista({ dados }: { dados: SociosDaEmpresaV1 }) {
  if (dados.socios.length === 0) {
    return <p className="apagado">Nenhum sócio pessoa física adulto no quadro desta empresa na Receita.</p>;
  }
  return (
    <>
      {dados.total > dados.socios.length ? (
        <p className="apagado">
          Mostrando {dados.socios.length} de {dados.total} sócios.
        </p>
      ) : null}
      <div className="tabela-rolavel">
        <table className="tabela-do-app">
          <thead>
            <tr>
              <th scope="col">Nome</th>
              <th scope="col">Qualificação</th>
              <th scope="col">Entrou em</th>
            </tr>
          </thead>
          <tbody>
            {dados.socios.map((socio, i) => (
              // a posição serve de chave: a lista vem pronta da API e pode ter nomes iguais
              <tr key={i}>
                <th scope="row">{socio.nome}</th>
                <td>{socio.qualificacao}</td>
                <td>{socio.entrou_em === null ? SEM_DATA : formatarData(socio.entrou_em)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function SociosDaFicha({ rota, cnpj }: { rota: string; cnpj: string }) {
  const pedido = usarPedido<SociosDaEmpresaV1>(`${rota}${CAMINHO}`, {}, { cnpj });
  if (pedido.estado !== "pronto") return null; // carregando, sem a permissão (404) ou qualquer falha
  const { fonte, limites } = pedido.dados;
  const mes = fonte.mes_do_retrato?.replace(MES_ISO, "$2/$1") ?? null;
  return (
    <section className="secao-do-relatorio" aria-labelledby="socios-da-ficha">
      <h2 id="socios-da-ficha">Sócios pessoa física</h2>
      <Lista dados={pedido.dados} />
      <p className="apagado">
        Fonte: {fonte.atribuicao} ({fonte.fonte}){mes === null ? "" : `, retrato de ${mes}`}.
      </p>
      <ul className="apagado">
        {limites.map((limite) => (
          <li key={limite}>{limite}</li>
        ))}
      </ul>
    </section>
  );
}
