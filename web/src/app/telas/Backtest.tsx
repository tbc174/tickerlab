// Backtest simples no app novo: a estratégia escolhida, com os custos, no passado do ativo. As
// métricas saem na ordem e no formato do Streamlit (src/formatos.py) e a curva de capital em base 100.
// Embaixo, a ficha "Foi sorte?" (src/ficha.py, pela API). Proteções, Monte Carlo e o detalhe técnico
// da validação continuam só no app atual.
import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { type PaginaDoApp, conteudoDoApp } from "../../conteudo";
import { linkDoApp } from "../../site/textos";
import { Ajuda } from "../Ajuda";
import { mensagemDe } from "../BaixarMeusDados";
import { corpoDoPedido, valoresIniciais } from "../Formulario";
import { VereditoDaFicha } from "../VereditoDaFicha";
import { ErroDaApi, pedir } from "../api";
import { useConta } from "../conta";
import { formatar } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { BacktestDoAtivoV1, FichaV1, MinhasSimulacoesV1 } from "../tipos";
import { ErroDaTela } from "./ErroDaTela";
import { TelaDoContrato } from "./TelaDoContrato";

const { metricas_por_formato, ficha: textosDaFicha } = conteudoDoApp.backtest;

/** O formato de uma métrica, pelo nome (o mesmo de src/formatos.formato_da_metrica). */
function formatoDa(nome: string): string {
  const achado = Object.entries(metricas_por_formato).find(([, nomes]) => nomes.includes(nome));
  return achado ? achado[0] : "decimal";
}

function Numero({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="numero-do-painel">
      <span className="numero-rotulo">
        <span>{rotulo}</span>
      </span>
      <span className="numero-valor">{valor}</span>
    </div>
  );
}

function Ficha({ ficha }: { ficha: FichaV1 }) {
  const { veredito } = ficha;
  return (
    <>
      <VereditoDaFicha
        resultado={veredito.resultado}
        titulo={veredito.titulo}
        texto={veredito.texto}
        checagens={ficha.checagens}
        nivel={3}
      />
      <p>{ficha.texto_das_tentativas}</p>
      <p className="apagado">{ficha.nota}</p>
    </>
  );
}

/** A seção "Foi sorte?": a ficha ou, sem ela, o motivo (o backtest em cima continua valendo). */
function FoiSorte({ dados }: { dados: BacktestDoAtivoV1 }) {
  return (
    <section aria-label={textosDaFicha.termo} className="ficha-foi-sorte">
      <h2>
        {textosDaFicha.termo}
        <Ajuda termo={textosDaFicha.termo} rotulo={textosDaFicha.termo} />
      </h2>
      <p className="apagado">{textosDaFicha.explicacao}</p>
      {dados.ficha ? (
        <Ficha ficha={dados.ficha} />
      ) : (
        <p className="erro-do-app" role="note">
          {dados.motivo_sem_ficha}
        </p>
      )}
    </section>
  );
}

function Resultado({ dados }: { dados: BacktestDoAtivoV1 }) {
  const { backtest, ativo } = dados;
  return (
    <section aria-label="Resultado do backtest" className="painel-de-numeros">
      {ativo.aviso_da_origem ? (
        <p className="erro-do-app" role="note">
          {ativo.aviso_da_origem}
        </p>
      ) : null}
      <h2>{dados.estrategia}</h2>
      <div className="numeros">
        {Object.entries(backtest.metricas).map(([nome, valor]) => (
          <Numero key={nome} rotulo={nome} valor={formatar(valor, formatoDa(nome))} />
        ))}
        <Numero rotulo="Operações" valor={formatar(backtest.operacoes, "inteiro")} />
      </div>
      <h2>Curva de capital</h2>
      <GraficoDeLinha
        titulo={`Curva de capital de ${dados.estrategia} em ${ativo.codigo} (base 100)`}
        datas={backtest.curva_de_capital.datas}
        series={[{ nome: dados.estrategia, cor: "var(--serie-1)", valores: backtest.curva_de_capital.valores }]}
        referencia={100}
      />
      <p className="apagado">
        Resultado no passado, com os custos de cada operação; não é promessa de rentabilidade. Proteções
        (stop, alvo), Monte Carlo e o detalhe técnico da validação estão no{" "}
        <a href={linkDoApp("backtest")}>app atual</a>.
      </p>
    </section>
  );
}

type Salvamento =
  | { estado: "parado" }
  | { estado: "salvando" }
  | { estado: "salva"; uso: string }
  | { estado: "erro"; erro: ErroDaApi };

/** "Salvar na minha conta" (Minhas simulações; Workspace, PR 1): manda à API o mesmo pedido que a
 * tela fez (lido do endereço, como TelaDoContrato) e o veredito da ficha, que o Pulse usa como o
 * "antes" quando recalcula. Os números e a ficha guardados são refeitos no servidor. */
function SalvarNaConta({ pagina, dados }: { pagina: PaginaDoApp; dados: BacktestDoAtivoV1 }) {
  const token = useConta()?.token ?? null;
  const [busca] = useSearchParams();
  const sugestao = `${dados.estrategia} · ${dados.ativo.codigo} · ${dados.ativo.periodo}`;
  const [nome, setNome] = useState(sugestao);
  const [salvamento, setSalvamento] = useState<Salvamento>({ estado: "parado" });
  const salvar = (evento: FormEvent) => {
    evento.preventDefault();
    if (token === null) return;
    const entradas = pagina.contrato?.entradas ?? [];
    setSalvamento({ estado: "salvando" });
    pedir<MinhasSimulacoesV1>("/v1/salvar-simulacao", token, {}, {
      nome: nome.trim() || sugestao,
      backtest: corpoDoPedido(entradas, valoresIniciais(entradas, busca)),
      veredito: dados.ficha?.veredito.resultado ?? null,
    })
      .then((lista) => setSalvamento({ estado: "salva", uso: lista.uso }))
      .catch((falha: unknown) => {
        const erro = falha instanceof ErroDaApi ? falha : new ErroDaApi("indisponivel", mensagemDe(falha));
        setSalvamento({ estado: "erro", erro });
      });
  };
  return (
    <section aria-label="Salvar na minha conta" className="salvar-simulacao">
      <h2>Salvar na minha conta</h2>
      <p className="apagado">
        A simulação fica em Minhas simulações, para reabrir depois com os dados de hoje. O veredito da ficha
        "Foi sorte?" de agora fica guardado para comparar com o de amanhã.
      </p>
      <form className="formulario-do-app" onSubmit={salvar}>
        <label>
          Nome da simulação
          <input value={nome} maxLength={120} required onChange={(e) => setNome(e.target.value)} />
        </label>
        <button type="submit" className="botao primario" disabled={salvamento.estado === "salvando"}>
          Salvar
        </button>
      </form>
      {salvamento.estado === "salva" ? (
        <p role="status">
          Simulação guardada ({salvamento.uso}). <Link to="/simulacoes">Ver minhas simulações</Link>
        </p>
      ) : null}
      {salvamento.estado === "erro" ? <ErroDaTela erro={salvamento.erro} /> : null}
    </section>
  );
}

export function Backtest({ pagina }: { pagina: PaginaDoApp }) {
  const [busca] = useSearchParams();
  return (
    <TelaDoContrato<BacktestDoAtivoV1>
      pagina={pagina}
      carregando="Rodando o backtest…"
      esqueleto="grafico"
      resultado={(dados) => (
        <>
          <Resultado dados={dados} />
          <FoiSorte dados={dados} />
          {/* a chave zera o nome sugerido e a mensagem a cada análise nova */}
          <SalvarNaConta key={busca.toString()} pagina={pagina} dados={dados} />
        </>
      )}
    />
  );
}
