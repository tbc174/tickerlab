// Busca por CNPJ no app novo (molde B): o relatório do CNPJ de uma companhia aberta, nas mesmas
// seções do relatório da empresa. Não é uma TelaDoContrato: o CNPJ pode ser de MEI (dado pessoal,
// ADR 0077, item 1), então ele vai no corpo do POST e nunca no endereço, e nada é pedido antes de a
// pessoa buscar. "Limites e cuidados" e "O que ainda não aparece" ficam sempre à vista.
import { type FormEvent, useState } from "react";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import { Carregando } from "../Carregando";
import { formatarData } from "../formatar";
import type { BuscaPorCnpjV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";
import { ConviteDoPro, Secao, fimDoPrimeiroBloco } from "./RelatorioEmpresa";

const TAMANHO_MAXIMO_DO_CNPJ = 20; // com a pontuação cabem 18; sobra folga para espaços colados

function Lista({ titulo, itens, id }: { titulo: string; itens: string[]; id: string }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby={id}>
      <h2 id={id}>{titulo}</h2>
      <ul>
        {itens.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function Relatorio({ dados }: { dados: BuscaPorCnpjV1 }) {
  const fimDoBloco = fimDoPrimeiroBloco(dados.secoes);
  return (
    <>
      {dados.situacao === "encontrada" ? (
        <p>
          <strong>{dados.empresa}</strong> · CNPJ {dados.cnpj}
          {dados.tickers.length > 0 ? ` · ${dados.tickers.join(", ")}` : ""}
          {dados.como_era_em ? (
            <span className="apagado"> · ficha de {formatarData(dados.como_era_em)}</span>
          ) : null}
        </p>
      ) : null}
      {dados.avisos.map((aviso) => (
        <p key={aviso} className="erro-do-app" role="note">
          {aviso}
        </p>
      ))}
      {dados.secoes.map((secao, i) => (
        <div key={secao.chave}>
          <Secao secao={secao} />
          {i === fimDoBloco ? <ConviteDoPro /> : null}
        </div>
      ))}
      {dados.fontes.length > 0 ? <p className="apagado">Fontes: {dados.fontes.join("; ")}.</p> : null}
    </>
  );
}

function Resultado({ pagina, cnpj }: { pagina: PaginaDoApp; cnpj: string }) {
  const pedido = usarPedido<BuscaPorCnpjV1>(pagina.contrato?.rota ?? "", {}, { cnpj });
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Montando o relatório do CNPJ…" />;
  if (pedido.estado === "erro") return <ErroDaTela erro={pedido.erro} />;
  return (
    <>
      <Relatorio dados={pedido.dados} />
      <Lista id="limites-do-cnpj" titulo="Limites e cuidados" itens={pedido.dados.limites} />
      <Lista id="desligado-do-cnpj" titulo="O que ainda não aparece" itens={pedido.dados.desligado} />
    </>
  );
}

// antes da primeira busca os limites e o desligado não vêm da API; este é o resumo fixo da tela
const ANTES_DA_BUSCA =
  "No lançamento a busca mostra só as companhias abertas com ficha na base. Nada aqui é recomendação de investimento.";

export function BuscaPorCnpj({ pagina }: { pagina: PaginaDoApp }) {
  const [rascunho, setRascunho] = useState("");
  const [buscado, setBuscado] = useState<{ cnpj: string; vez: number } | null>(null);
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
          Buscar
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
