// Titular do empresário individual e do MEI na ficha (linha 808; ADR 0128, Emenda 1): o nome da pessoa, do
// cadastro público da Receita, sem CPF. Como em SociosDaFicha, quem decide se a conta vê é o servidor, a cada
// pedido: só a organização com a permissão `pessoa_na_tela` recebe o nome (POST /v1/analista/ficha/titular,
// com o CNPJ no corpo). Para as outras contas a rota responde o 404 de um endereço que não existe, e este
// componente não desenha nada; o mesmo vale para qualquer falha e para a empresa que não é individual (a
// maioria): sem seção vazia nem aviso. Nada de pessoa vem no pacote do app.
import { usarPedido } from "../usarPedido";

export type TitularV1 = { nome: string };

/** A resposta de POST /v1/analista/ficha/titular (src/api_v1/analista_pessoas.py). */
export type TitularDaEmpresaV1 = {
  estado: "pronta" | "sem_titular";
  titulares: TitularV1[];
  total: number;
  fonte: { fonte: string; atribuicao: string; mes_do_retrato: string | null }; // mês em AAAA-MM
  limites: string[];
};

const CAMINHO = "/titular"; // depois da rota da ficha
const MES_ISO = /^(\d{4})-(\d{2})$/;

export function TitularDaFicha({ rota, cnpj }: { rota: string; cnpj: string }) {
  const pedido = usarPedido<TitularDaEmpresaV1>(`${rota}${CAMINHO}`, {}, { cnpj });
  if (pedido.estado !== "pronto" || pedido.dados.titulares.length === 0) return null;
  const { titulares, fonte, limites } = pedido.dados;
  const mes = fonte.mes_do_retrato?.replace(MES_ISO, "$2/$1") ?? null;
  return (
    <section className="secao-do-relatorio" aria-labelledby="titular-da-ficha">
      <h2 id="titular-da-ficha">Titular (empresário individual ou MEI)</h2>
      <ul>
        {titulares.map((titular, i) => (
          // a posição serve de chave: a lista vem pronta da API
          <li key={i}>{titular.nome}</li>
        ))}
      </ul>
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
