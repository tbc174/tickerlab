// O esqueleto das telas com formulário: título, campos do contrato guardados no endereço, o pedido à
// rota do contrato e, conforme a resposta, "carregando", o erro da API ou o resultado.
import type { ReactNode } from "react";
import { useSearchParams } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import {
  Formulario,
  buscaDosValores,
  corpoDoPedido,
  parametrosDoPedido,
  valoresIniciais,
} from "../Formulario";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

interface Propriedades<T> {
  pagina: PaginaDoApp;
  carregando: string;
  resultado(dados: T): ReactNode;
  // ajuste antes do pedido (ex.: o limite de ativos da comparação), com um aviso opcional
  ajustar?(valores: Record<string, string>): { valores: Record<string, string>; aviso: string | null };
}

export function TelaDoContrato<T>({ pagina, carregando, resultado, ajustar }: Propriedades<T>) {
  const [busca, setBusca] = useSearchParams();
  const entradas = pagina.contrato?.entradas ?? [];
  const iniciais = valoresIniciais(entradas, busca);
  const { valores, aviso } = ajustar ? ajustar(iniciais) : { valores: iniciais, aviso: null };
  const post = pagina.contrato?.metodo === "POST";
  const pedido = usarPedido<T>(
    pagina.contrato?.rota ?? "",
    post ? {} : parametrosDoPedido(entradas, valores),
    post ? corpoDoPedido(entradas, valores) : undefined,
  );
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      <Formulario
        key={busca.toString()}
        entradas={entradas}
        valores={iniciais}
        aoAnalisar={(novos) => setBusca(buscaDosValores(entradas, novos))}
      />
      {aviso ? (
        <p className="erro-do-app" role="note">
          {aviso}
        </p>
      ) : null}
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          {carregando}
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        resultado(pedido.dados)
      )}
    </section>
  );
}
