// O esqueleto das telas com formulário: título, campos do contrato guardados no endereço, o pedido à
// rota do contrato e, conforme a resposta, "carregando", o erro da API ou o resultado.
import type { ReactNode } from "react";
import { useSearchParams } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { Formulario, buscaDosValores, parametrosDoPedido, valoresIniciais } from "../Formulario";
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
  const pedido = usarPedido<T>(pagina.contrato?.rota ?? "", parametrosDoPedido(entradas, valores));
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
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
