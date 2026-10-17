// O botão de baixar a cópia de tudo o que o TickerLab guarda sobre a pessoa (LGPD, art. 18). Fica num
// arquivo próprio porque aparece em dois lugares: na tela Meus dados e na tela do aceite dos termos
// (quem não aceita os termos novos ainda pode levar os dados embora). Recebe o token pronto: assim não
// importa `conta.tsx`, que importa este arquivo.
import { useState } from "react";
import { ErroDaApi, baixar } from "./api";

const NOME_DO_ARQUIVO = "meus-dados-tickerlab.json"; // o mesmo do botão do Streamlit

export function mensagemDe(falha: unknown): string {
  return falha instanceof ErroDaApi ? falha.message : "Não deu agora. Tente de novo em instantes.";
}

export function BaixarMeusDados({ token }: { token: string | null }) {
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
