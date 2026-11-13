// O app em React (série 3 da ADR 0048), o principal em app.tickerlab.com.br/; o Streamlit é a versão
// clássica em /classico. Link antigo de página que ainda só existe lá é levado para lá (src/app/rotas.tsx).
// Sem a API de leitura ligada, só mostra o aviso e o caminho para a versão clássica; com ela, tudo
// fica atrás do login com o Google (src/app/conta.tsx), menos o link compartilhado (/c), que é público.
import { Fragment, type ReactNode, useRef } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import { useConfiguracao } from "./configuracao";
import { ExigeLogin, ProvedorDaConta } from "./conta";
import { Casca } from "./pecas/Casca";
import { ParaOClassico, TELAS_DO_APP, eAInicialDoClassico, enderecoSoDoClassico, telaDa } from "./rotas";
import {
  Carregando,
  EmPreparacao,
  ForaDoAr,
  LoginNaoConfigurado,
  NaoEncontrada,
} from "./telas/Avisos";
import { Compartilhado } from "./telas/Compartilhado";
import { Inicio } from "./telas/Inicio";

// o link compartilhado (onda 4): abre sem login, só com o código depois do "#"
const ROTA_PUBLICA_DO_LINK = "/c";

/** A tela aberta recomeça quando chega um estado novo de navegação. A busca do topo manda o CNPJ à ficha pelo
 * estado (nunca pelo endereço) e a ficha só o lê ao abrir: sem isto, buscar outro CNPJ com a ficha já aberta
 * não mudaria nada. Apagar o estado (o que a tela faz depois de ler) não recomeça a tela. */
function RecomecaComEstadoNovo({ children }: { children: ReactNode }) {
  const { state } = useLocation();
  const chegada = useRef({ estado: state as unknown, vez: 0 });
  if (state !== null && state !== undefined && state !== chegada.current.estado) {
    chegada.current = { estado: state, vez: chegada.current.vez + 1 };
  }
  return <Fragment key={chegada.current.vez}>{children}</Fragment>;
}

export function App() {
  const api = useConfiguracao();
  const { pathname } = useLocation();
  // o link antigo vem antes de tudo: não depende da API ligada nem do login do app novo
  const doClassico = enderecoSoDoClassico(pathname);
  if (doClassico !== null) {
    return (
      <Casca comMenu={false}>
        <ParaOClassico endereco={doClassico} />
      </Casca>
    );
  }
  if (eAInicialDoClassico(pathname)) return <Navigate to="/" replace />;
  if (api.estado !== "ligada") {
    const aviso = {
      carregando: <Carregando />,
      desligada: <EmPreparacao />,
      "fora do ar": <ForaDoAr />,
    }[api.estado];
    return <Casca comMenu={false}>{aviso}</Casca>;
  }
  if (pathname.replace(/\/$/, "") === ROTA_PUBLICA_DO_LINK) {
    return (
      <Casca comMenu={false}>
        <Compartilhado />
      </Casca>
    );
  }
  if (!api.googleClientId) {
    return (
      <Casca comMenu={false}>
        <LoginNaoConfigurado />
      </Casca>
    );
  }
  return (
    <ProvedorDaConta clientId={api.googleClientId}>
      {/* a casca (menu, topo e rodapé) só depois de entrar: antes, a página de entrada */}
      <ExigeLogin>
        <Casca comMenu>
          <RecomecaComEstadoNovo>
            <Routes>
              <Route index element={<Inicio />} />
              {TELAS_DO_APP.map((pagina) => (
                <Route key={pagina.chave} path={pagina.url} element={telaDa(pagina)} />
              ))}
              <Route path="*" element={<NaoEncontrada />} />
            </Routes>
          </RecomecaComEstadoNovo>
        </Casca>
      </ExigeLogin>
    </ProvedorDaConta>
  );
}
