// Peça única: o botão de baixar um arquivo de uma rota da v1 (Excel, PDF, deck). Pede com a sessão, salva
// com o nome dado e, se falhar, mostra a mensagem da API ao lado. O nome do arquivo nunca leva dado da
// consulta (CNPJ, nome de empresa): é quem chama que escolhe, e o padrão do app é um nome fixo.
import { useState } from "react";
import { ErroDaApi, baixar } from "../api";
import { useConta } from "../conta";

const NAO_DEU = "Não deu agora. Tente de novo em instantes.";

interface Propriedades {
  /** O texto do botão: "Baixar em Excel", "Baixar PDF". */
  rotulo: string;
  /** A rota inteira da v1, com o sufixo do arquivo: "/v1/empresas/ficha/planilha". */
  rota: string;
  /** O nome com que o arquivo é salvo. */
  nome: string;
  /** Com corpo, o pedido é um POST (o CNPJ não pode ir no endereço). */
  corpo?: unknown;
  /** Parâmetros do endereço, para o que não é dado sensível (o setor, o formato). */
  parametros?: Record<string, string>;
  /** O botão principal da tela (azul cheio); o padrão é o botão comum. */
  principal?: boolean;
}

/** Entrega o arquivo ao navegador como um download com o nome dado. */
function salvar(arquivo: Blob, nome: string) {
  const endereco = URL.createObjectURL(arquivo);
  const ancora = document.createElement("a");
  ancora.href = endereco;
  ancora.download = nome;
  ancora.click();
  URL.revokeObjectURL(endereco);
}

export function Baixar({ rotulo, rota, nome, corpo, parametros, principal }: Propriedades) {
  const token = useConta()?.token ?? null;
  const [baixando, setBaixando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const baixarAgora = () => {
    if (token === null) return;
    setBaixando(true);
    setFalha(null);
    baixar(rota, token, corpo, parametros)
      .then((arquivo) => salvar(arquivo, nome))
      .catch((erro: unknown) => setFalha(erro instanceof ErroDaApi ? erro.message : NAO_DEU))
      .finally(() => setBaixando(false));
  };
  return (
    <>
      <button
        type="button"
        className={principal ? "botao primario" : "botao"}
        disabled={baixando}
        aria-busy={baixando}
        onClick={baixarAgora}
      >
        {rotulo}
      </button>
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </>
  );
}
