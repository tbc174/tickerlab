// Relatório do setor no app novo (molde D): quem está no setor, as seções que a API monta (tamanho,
// concentração com a faixa do CADE, lado a lado) e, sempre à vista, "O que não temos" e "Limites e
// cuidados". A tranca do plano é do servidor: esta tela só mostra. O setor não é dado pessoal, então
// a escolha vai no endereço (GET), e o relatório já abre no primeiro setor da lista.
import { useState } from "react";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import { ErroDaApi, baixar } from "../api";
import { Carregando } from "../Carregando";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import type { RelatorioDoSetorV1, SetoresV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";
import { ConviteDoPro, Secao, fimDoPrimeiroBloco } from "./RelatorioEmpresa";

function BaixarPdf({ rota, setor }: { rota: string; setor: string }) {
  const token = useConta()?.token ?? null;
  const [baixando, setBaixando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const baixarAgora = () => {
    if (token === null) return;
    setBaixando(true);
    setFalha(null);
    baixar(`${rota}/pdf`, token, undefined, { setor })
      .then((arquivo) => {
        const endereco = URL.createObjectURL(arquivo);
        const ancora = document.createElement("a");
        ancora.href = endereco;
        ancora.download = `relatorio-do-setor-${setor}-tickerlab.pdf`;
        ancora.click();
        URL.revokeObjectURL(endereco);
      })
      .catch((erro: unknown) =>
        setFalha(erro instanceof ErroDaApi ? erro.message : "Não deu agora. Tente de novo em instantes."),
      )
      .finally(() => setBaixando(false));
  };
  return (
    <>
      <button type="button" className="botao" disabled={baixando} onClick={baixarAgora}>
        Baixar PDF
      </button>
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </>
  );
}

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

function Membros({ dados }: { dados: RelatorioDoSetorV1 }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby="membros-do-setor">
      <h2 id="membros-do-setor">Quem está no setor ({dados.membros.length})</h2>
      {dados.membros.length === 0 ? (
        <p className="apagado">A noite ainda não trouxe companhias abertas para este setor.</p>
      ) : (
        <ul>
          {dados.membros.map((membro) => (
            <li key={membro.cnpj}>
              <strong>{membro.empresa}</strong>
              {membro.tickers.length > 0 ? ` · ${membro.tickers.join(", ")}` : ""}
              <span className="apagado"> · {membro.motivo}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function NaoTemos({ dados }: { dados: RelatorioDoSetorV1 }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby="nao-temos-do-setor">
      <h2 id="nao-temos-do-setor">O que não temos</h2>
      <ul>
        {dados.nao_temos.map((falta) => (
          <li key={falta.kpi}>
            <strong>{falta.kpi}</strong>: {falta.motivo}
            <span className="apagado"> · Fonte: {falta.fonte}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Frases({ dados }: { dados: RelatorioDoSetorV1 }) {
  if (dados.frases.length === 0) return null;
  return <Lista id="frases-do-setor" titulo="O que os dados mostram" itens={dados.frases.map((f) => f.texto)} />;
}

function Relatorio({ dados }: { dados: RelatorioDoSetorV1 }) {
  const fimDoBloco = fimDoPrimeiroBloco(dados.secoes);
  return (
    <>
      <p>
        <strong>{dados.nome}</strong>
        {dados.como_era_em ? (
          <span className="apagado"> · ficha de {formatarData(dados.como_era_em)}</span>
        ) : null}
      </p>
      {dados.avisos.map((aviso) => (
        <p key={aviso} className="erro-do-app" role="note">
          {aviso}
        </p>
      ))}
      <Membros dados={dados} />
      <Frases dados={dados} />
      {dados.secoes.map((secao, i) => (
        <div key={secao.chave}>
          <Secao secao={secao} />
          {i === fimDoBloco ? <ConviteDoPro /> : null}
        </div>
      ))}
      <NaoTemos dados={dados} />
      {dados.fontes.length > 0 ? <p className="apagado">Fontes: {dados.fontes.join("; ")}.</p> : null}
      <Lista id="limites-do-setor" titulo="Limites e cuidados" itens={dados.limites} />
    </>
  );
}

function Resultado({ rota, setor }: { rota: string; setor: string }) {
  const pedido = usarPedido<RelatorioDoSetorV1>(rota, { setor });
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Montando o relatório do setor…" />;
  if (pedido.estado === "erro") return <ErroDaTela erro={pedido.erro} />;
  return (
    <>
      <BaixarPdf rota={rota} setor={setor} />
      <Relatorio dados={pedido.dados} />
    </>
  );
}

function Escolha({ pagina, setores }: { pagina: PaginaDoApp; setores: SetoresV1["setores"] }) {
  const [escolhido, setEscolhido] = useState(setores[0]?.chave ?? "");
  return (
    <>
      <form className="formulario-do-app" onSubmit={(evento) => evento.preventDefault()}>
        <div className="campos-do-formulario">
          <label>
            <span>Setor</span>
            <select value={escolhido} onChange={(ev) => setEscolhido(ev.target.value)}>
              {setores.map((setor) => (
                <option key={setor.chave} value={setor.chave}>
                  {setor.nome} ({setor.empresas} companhias abertas)
                </option>
              ))}
            </select>
          </label>
        </div>
      </form>
      {escolhido === "" ? null : <Resultado key={escolhido} rota={pagina.contrato?.rota ?? ""} setor={escolhido} />}
    </>
  );
}

export function RelatorioDoSetor({ pagina }: { pagina: PaginaDoApp }) {
  const lista = usarPedido<SetoresV1>("/v1/setores", {});
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      {lista.estado === "carregando" ? <Carregando tipo="painel" rotulo="Carregando os setores…" /> : null}
      {lista.estado === "erro" ? <ErroDaTela erro={lista.erro} /> : null}
      {lista.estado === "pronto" ? <Escolha pagina={pagina} setores={lista.dados.setores} /> : null}
    </section>
  );
}
