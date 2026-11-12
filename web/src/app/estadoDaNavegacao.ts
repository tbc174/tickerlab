// O estado da navegação que uma tela recebe de outra (o CNPJ da lista para a ficha, por exemplo) vale uma
// vez só (linha 822, P2 da revisão do #999): o `state` fica na entrada do histórico do navegador e
// sobreviveria a "Sair" e a outra conta na mesma aba, que abriria a ficha da conta anterior em nome da nova.
// A tela lê o estado ao abrir e logo o apaga da entrada do histórico (sem criar entrada nova).
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";

export function useEstadoDaNavegacaoUmaVez(): unknown {
  const local = useLocation();
  const navegar = useNavigate();
  const [estado] = useState<unknown>(local.state); // o que veio quando a tela abriu
  useEffect(() => {
    if (local.state !== null && local.state !== undefined) {
      navegar(`${local.pathname}${local.search}${local.hash}`, { replace: true, state: null });
    }
  }, [local, navegar]);
  return estado;
}
