import { Link } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { FundoDoApp } from "../FundoDoApp";
import { TELAS_DO_APP, temTelaPronta } from "../rotas";
import type { PulseV1 } from "../tipos";
import { ErroDaTela } from "./ErroDaTela";
import { AcontecimentosNovos } from "./workspace/Acontecimentos";
import { EstrategiasAcompanhadas } from "./workspace/Estrategias";
import { usarPulse } from "./workspace/usarPulse";
import { VariacaoDoPreco } from "./workspace/Variacao";

// o caminho do analista (linha 822), na ordem em que se usa; a página que ainda não abre no app novo fica fora
const CHAVES_DOS_PASSOS = ["encontrar_empresas", "ficha_da_empresa", "comparar_empresas"];
const telaPronta = (chave: string) => TELAS_DO_APP.find((p) => p.chave === chave && temTelaPronta(chave));
const PASSOS: PaginaDoApp[] = CHAVES_DOS_PASSOS.flatMap((chave) => telaPronta(chave) ?? []);
const O_QUE_MUDOU = telaPronta("o_que_mudou");

/** Os passos do analista: o título e a frase de cada um vêm de src/paginas.py, como no menu e no site. */
function PassosDoAnalista() {
  return (
    <ol className="telas-do-app" aria-label="Passos">
      {PASSOS.map((pagina, indice) => (
        <li key={pagina.chave} className="cartao">
          <p className="olho">Passo {indice + 1}</p>
          <Link to={`/${pagina.url}`}>{pagina.titulo}</Link>
          <p className="apagado">{pagina.descricao}</p>
        </li>
      ))}
    </ol>
  );
}

/** A conta acompanha algo (estratégia salva ou ativo guardado)? Leitura que falhou conta: não esconde o aviso. */
function acompanhaAlgo(dados: PulseV1): boolean {
  const ativos = dados.variacoes.length + dados.sem_variacao.length + dados.avisos_dos_ativos.length;
  return dados.estrategias.length > 0 || ativos > 0 || dados.acontecimentos === null || dados.acontecimentos.length > 0;
}

/** O Workspace (ADR 0062), de um pedido só ao Pulse. Só aparece para quem acompanha algo: enquanto o Pulse
 * não chega, nada (senão o bloco piscaria para o analista, que não acompanha ativo); se falha, um aviso só. */
function Workspace() {
  const pedido = usarPulse();
  if (pedido.estado === "carregando") return null;
  if (pedido.estado === "erro") {
    return (
      <section className="cartao-do-workspace" aria-labelledby="titulo-do-workspace">
        <h2 id="titulo-do-workspace">Seu Workspace</h2>
        <ErroDaTela erro={pedido.erro} />
      </section>
    );
  }
  if (!acompanhaAlgo(pedido.dados)) return null;
  return (
    <>
      <h2>Seu Workspace</h2>
      <p className="apagado">{pedido.dados.janela.texto}</p>
      <AcontecimentosNovos dados={pedido.dados} />
      <VariacaoDoPreco dados={pedido.dados} />
      <EstrategiasAcompanhadas dados={pedido.dados} />
    </>
  );
}

/** O começo do app novo é o caminho do analista: encontrar, abrir a ficha e comparar. O Workspace fica
 * embaixo, só para a conta que acompanha algum ativo ou estratégia. */
export function Inicio() {
  return (
    <section>
      <FundoDoApp>
        <p className="olho">Início</p>
        <h1>Por onde começar</h1>
        <p>Estude uma empresa pelo CNPJ, um passo de cada vez. Cada campo vem com a fonte e a data.</p>
      </FundoDoApp>
      <PassosDoAnalista />
      {O_QUE_MUDOU && (
        <p>
          <Link to={`/${O_QUE_MUDOU.url}`}>O que mudou no app</Link>
        </p>
      )}
      <Workspace />
    </section>
  );
}
