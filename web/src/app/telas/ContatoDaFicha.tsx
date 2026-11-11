// Contato dos estabelecimentos ativos da empresa da ficha (linha 808; ADR 0128, Emenda 1): endereço,
// telefones e e-mail do cadastro público da Receita. Como em SociosDaFicha, quem decide se a conta vê é o
// servidor, a cada pedido: só a organização com a permissão `pessoa_na_tela` recebe a lista
// (POST /v1/analista/ficha/contato, com o CNPJ no corpo). Para as outras contas a rota responde o 404 de um
// endereço que não existe, e este componente não desenha nada; o mesmo vale para qualquer outra falha.
// Nada de contato vem no pacote do app: só existe na resposta da API.
import { usarPedido } from "../usarPedido";

export type EstabelecimentoV1 = {
  cnpj: string; // 14 dígitos
  matriz: boolean;
  logradouro: string | null;
  bairro: string | null;
  cep: string | null;
  municipio: string | null;
  uf: string | null;
  telefones: string[]; // DDD e número, só dígitos
  email: string | null;
};

/** A resposta de POST /v1/analista/ficha/contato (src/api_v1/analista_pessoas.py). */
export type ContatoDaEmpresaV1 = {
  estado: "pronta" | "sem_contato";
  estabelecimentos: EstabelecimentoV1[];
  total: number; // a lista pode vir cortada: `total` diz quantos são
  fonte: { fonte: string; atribuicao: string; mes_do_retrato: string | null }; // mês em AAAA-MM
  limites: string[];
};

const CAMINHO = "/contato"; // depois da rota da ficha
const MES_ISO = /^(\d{4})-(\d{2})$/;
const CNPJ_14 = /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/;
const CEP_8 = /^(\d{5})(\d{3})$/;
const FONE = /^(\d{2})(\d{4,5})(\d{4})$/;

const cnpj = (digitos: string) => digitos.replace(CNPJ_14, "$1.$2.$3/$4-$5");
const cep = (digitos: string) => digitos.replace(CEP_8, "$1-$2");
const telefone = (digitos: string) => digitos.replace(FONE, "($1) $2-$3");

function endereco(e: EstabelecimentoV1): string {
  const cidade = [e.municipio, e.uf].filter(Boolean).join("/");
  const partes = [e.logradouro, e.bairro, cidade, e.cep ? `CEP ${cep(e.cep)}` : null];
  return partes.filter((parte) => parte).join(", ");
}

function Lista({ dados }: { dados: ContatoDaEmpresaV1 }) {
  if (dados.estabelecimentos.length === 0) {
    return <p className="apagado">Nenhum estabelecimento ativo desta empresa no retrato da Receita.</p>;
  }
  return (
    <>
      {dados.total > dados.estabelecimentos.length ? (
        <p className="apagado">
          Mostrando {dados.estabelecimentos.length} de {dados.total} estabelecimentos.
        </p>
      ) : null}
      <div className="tabela-rolavel">
        <table className="tabela-do-app">
          <thead>
            <tr>
              <th scope="col">Estabelecimento</th>
              <th scope="col">Endereço</th>
              <th scope="col">Telefones</th>
              <th scope="col">E-mail</th>
            </tr>
          </thead>
          <tbody>
            {dados.estabelecimentos.map((e) => (
              <tr key={e.cnpj}>
                <th scope="row">
                  {cnpj(e.cnpj)} {e.matriz ? "(matriz)" : "(filial)"}
                </th>
                <td>{endereco(e) || "—"}</td>
                <td>{e.telefones.length === 0 ? "—" : e.telefones.map(telefone).join(" · ")}</td>
                <td>{e.email ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function ContatoDaFicha({ rota, cnpj: cnpjDaFicha }: { rota: string; cnpj: string }) {
  const pedido = usarPedido<ContatoDaEmpresaV1>(`${rota}${CAMINHO}`, {}, { cnpj: cnpjDaFicha });
  if (pedido.estado !== "pronto") return null; // carregando, sem a permissão (404) ou qualquer falha
  const { fonte, limites } = pedido.dados;
  const mes = fonte.mes_do_retrato?.replace(MES_ISO, "$2/$1") ?? null;
  return (
    <section className="secao-do-relatorio" aria-labelledby="contato-da-ficha">
      <h2 id="contato-da-ficha">Contato dos estabelecimentos</h2>
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
