// Meus dados no app novo: baixar a cópia de tudo o que o TickerLab guarda (LGPD, a mesma exportação do
// Streamlit) e os links compartilhados, com revogar. Apagar a conta, o tema, as Novidades por e-mail e
// os PDFs guardados continuam no app atual por enquanto (apagar a conta não tem volta: tela própria).
import { useEffect, useState } from "react";
import type { PaginaDoApp } from "../../conteudo";
import { linkDoApp } from "../../site/textos";
import { ErroDaApi, baixar, pedir } from "../api";
import { useConta } from "../conta";
import type { MeusLinksV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const SEM_PARAMETROS = {};
const NOME_DO_ARQUIVO = "meus-dados-tickerlab.json"; // o mesmo do botão do Streamlit

function mensagemDe(falha: unknown): string {
  return falha instanceof ErroDaApi ? falha.message : "Não deu agora. Tente de novo em instantes.";
}

function BaixarMeusDados() {
  const token = useConta()?.token ?? null;
  const [falha, setFalha] = useState<string | null>(null);
  const [baixando, setBaixando] = useState(false);
  const baixarAgora = () => {
    if (token === null) return;
    setBaixando(true);
    setFalha(null);
    baixar("/v1/meus-dados", token)
      .then((arquivo) => {
        const endereco = URL.createObjectURL(arquivo);
        const ancora = document.createElement("a");
        ancora.href = endereco;
        ancora.download = NOME_DO_ARQUIVO;
        ancora.click();
        URL.revokeObjectURL(endereco);
      })
      .catch((erro: unknown) => setFalha(mensagemDe(erro)))
      .finally(() => setBaixando(false));
  };
  return (
    <section aria-label="Seus dados">
      <h2>Seus dados</h2>
      <p className="apagado">Uma cópia de tudo o que o TickerLab guarda sobre você, num arquivo JSON.</p>
      <button type="button" className="botao primario" disabled={baixando} onClick={baixarAgora}>
        Baixar meus dados (JSON)
      </button>
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </section>
  );
}

function Links({ inicial }: { inicial: MeusLinksV1 }) {
  const token = useConta()?.token ?? null;
  const [dados, setDados] = useState(inicial);
  const [falha, setFalha] = useState<string | null>(null);
  useEffect(() => setDados(inicial), [inicial]);
  const revogar = (id: string) => {
    if (token === null) return;
    setFalha(null);
    pedir<MeusLinksV1>("/v1/revogar-link", token, {}, { id })
      .then(setDados)
      .catch((erro: unknown) => setFalha(mensagemDe(erro)));
  };
  return (
    <section aria-label="Links compartilhados">
      <h2>Links compartilhados</h2>
      {dados.links.length === 0 ? (
        <p className="apagado">{dados.sem_links}</p>
      ) : (
        <>
          <p className="apagado">{dados.explicacao}</p>
          <ul className="links-da-conta" aria-label="Links compartilhados">
            {dados.links.map((link) => (
              <li key={link.id}>
                <div>
                  <strong>{link.titulo}</strong>
                  <p className="apagado">{link.descricao}</p>
                </div>
                {link.situacao === "ativo" ? (
                  <button type="button" className="botao pequeno" onClick={() => revogar(link.id)}>
                    Revogar
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </section>
  );
}

export function MeusDados({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<MeusLinksV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
      <BaixarMeusDados />
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          Lendo os seus links…
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Links inicial={pedido.dados} />
      )}
      <h2>No app atual</h2>
      <p className="apagado">
        Apagar a conta (não tem volta), a aparência, as Novidades por e-mail e o .zip dos PDFs guardados
        continuam no app atual por enquanto.
      </p>
      <a className="botao" href={linkDoApp("meus-dados")}>
        Apagar a conta, tema, Novidades e PDFs (no app atual)
      </a>
    </section>
  );
}
