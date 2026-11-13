import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";
import { conteudoDoApp, type PaginaDoApp } from "../../conteudo";
import { cnpjDigitado } from "../BuscaGlobal";
import { formatarData } from "../formatar";
import { FundoDoApp } from "../FundoDoApp";
import { TELAS_DO_APP, temTelaPronta } from "../rotas";
import type { OQueMudouV1, PulseV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { CartaoDeNumero } from "../pecas/CartaoDeNumero";
import { Erro } from "../pecas/Erro";
import { AcontecimentosNovos } from "./workspace/Acontecimentos";
import { EstrategiasAcompanhadas } from "./workspace/Estrategias";
import { usarPulse } from "./workspace/usarPulse";
import { VariacaoDoPreco } from "./workspace/Variacao";

// o caminho do analista (linha 822), na ordem em que se usa; a página que ainda não abre no app novo fica fora
const CHAVES_DOS_PASSOS = ["encontrar_empresas", "ficha_da_empresa", "comparar_empresas"];
const telaPronta = (chave: string) => TELAS_DO_APP.find((p) => p.chave === chave && temTelaPronta(chave));
const PASSOS: PaginaDoApp[] = CHAVES_DOS_PASSOS.flatMap((chave) => telaPronta(chave) ?? []);
const O_QUE_MUDOU = telaPronta("o_que_mudou");
const FICHA = telaPronta("ficha_da_empresa");
const ENCONTRAR = telaPronta("encontrar_empresas");
const COBERTURA = telaPronta("dados_e_cobertura");
const NOVIDADES_NO_INICIO = 3;
const SEM_PARAMETROS = {};
const inteiro = (n: number) => n.toLocaleString("pt-BR");

/** A pergunta do Início: qual empresa? O CNPJ digitado abre a ficha e vai pelo estado da navegação, nunca
 * pelo endereço (o mesmo caminho da busca do topo). */
function AbrirPeloCnpj({ ficha }: { ficha: PaginaDoApp }) {
  const navegar = useNavigate();
  const [texto, setTexto] = useState("");
  const [invalido, setInvalido] = useState(false);
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    const cnpj = cnpjDigitado(texto);
    setInvalido(cnpj === null);
    if (cnpj !== null) navegar(`/${ficha.url}`, { state: { cnpj } });
  };
  return (
    <form className="pergunta-do-inicio" onSubmit={enviar} aria-label="Abrir a ficha de uma empresa">
      <label htmlFor="cnpj-do-inicio">CNPJ da empresa</label>
      <div className="pergunta-do-inicio-linha">
        <input
          id="cnpj-do-inicio"
          inputMode="text"
          autoComplete="off"
          placeholder="00.000.000/0000-00"
          value={texto}
          aria-invalid={invalido}
          aria-describedby={invalido ? "erro-do-cnpj-do-inicio" : undefined}
          onChange={(evento) => {
            setTexto(evento.target.value);
            setInvalido(false);
          }}
        />
        <button type="submit" className="botao primario">
          Abrir a ficha
        </button>
      </div>
      {invalido && (
        <p id="erro-do-cnpj-do-inicio" role="alert">
          Digite o CNPJ inteiro, com os 14 caracteres.
        </p>
      )}
      {ENCONTRAR && (
        <p className="pergunta-do-inicio-nota">
          Não tem o CNPJ? <Link to={`/${ENCONTRAR.url}`}>Encontre empresas por setor e UF</Link>.
        </p>
      )}
    </form>
  );
}

/** Os passos do analista: o título e a frase de cada um vêm de src/paginas.py, como no menu e no site. */
function PassosDoAnalista() {
  return (
    <ol className="telas-do-app" aria-label="Passos">
      {PASSOS.map((pagina, indice) => (
        <li key={pagina.chave} className="cartao">
          <p className="olho numero-do-passo">Passo {indice + 1}</p>
          <Link to={`/${pagina.url}`}>{pagina.titulo}</Link>
          <p className="apagado">{pagina.descricao}</p>
        </li>
      ))}
    </ol>
  );
}

/** O que a base tem: as contagens do catálogo, as mesmas da página inicial do site (web/conteudo/app.json). */
function OQueABaseTem() {
  const { tabelas, ligadas_pelo_cnpj, orgaos, fontes } = conteudoDoApp.base;
  return (
    <div className="painel-do-inicio">
      <h2>O que a base tem</h2>
      <div className="numeros">
        <CartaoDeNumero rotulo="Tabelas" valor={inteiro(tabelas)} detalhe="cada uma com contrato" />
        <CartaoDeNumero rotulo="Ligadas pelo CNPJ" valor={inteiro(ligadas_pelo_cnpj)} detalhe="tabelas" />
        <CartaoDeNumero rotulo="Órgãos públicos" valor={inteiro(orgaos)} detalhe="nas tabelas com CNPJ" />
        <CartaoDeNumero rotulo="Fontes" valor={inteiro(fontes)} detalhe="no catálogo" />
      </div>
      <p className="apagado">
        Contado do catálogo da base.{" "}
        {COBERTURA && <Link to={`/${COBERTURA.url}`}>Ver {COBERTURA.titulo.toLowerCase()}</Link>}
      </p>
    </div>
  );
}

/** As últimas entregas do app (a mesma rota da tela "O que mudou"). Sem resposta, fica só o link. */
function OQueMudouNoInicio({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<OQueMudouV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  const entregas = pedido.estado === "pronto" ? pedido.dados.entregas.slice(0, NOVIDADES_NO_INICIO) : [];
  return (
    <div className="painel-do-inicio">
      <h2>{pagina.titulo}</h2>
      {entregas.length > 0 && (
        <ul className="novidades-do-inicio" aria-label="Últimas entregas">
          {entregas.map((entrega) => (
            <li key={`${entrega.data}-${entrega.url}`}>
              <span className="apagado">{formatarData(entrega.data)}</span>
              <Link to={`/${entrega.url}`}>{entrega.titulo}</Link>
            </li>
          ))}
        </ul>
      )}
      <p>
        <Link to={`/${pagina.url}`}>O que mudou no app</Link>
      </p>
    </div>
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
        <Erro erro={pedido.erro} />
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

/** O começo do app novo (linha 903, PR E): uma pergunta (qual empresa?), os três passos do analista e dois
 * painéis, o que a base tem e o que mudou. O Workspace fica embaixo, só para a conta que acompanha algum
 * ativo ou estratégia. */
export function Inicio() {
  return (
    <section>
      <FundoDoApp>
        <p className="olho">Início</p>
        <h1>Qual empresa você quer estudar?</h1>
        <p>Abra a ficha pelo CNPJ. Cada campo vem com a fonte e a data.</p>
        {FICHA && <AbrirPeloCnpj ficha={FICHA} />}
      </FundoDoApp>
      <h2>Ou siga pelos passos</h2>
      <PassosDoAnalista />
      <div className="paineis-do-inicio">
        <OQueABaseTem />
        {O_QUE_MUDOU && <OQueMudouNoInicio pagina={O_QUE_MUDOU} />}
      </div>
      <Workspace />
    </section>
  );
}
