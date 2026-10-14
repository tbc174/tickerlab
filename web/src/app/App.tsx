// O app em React (série 3 da ADR 0048), servido em app.tickerlab.com.br/novo/ ao lado do Streamlit.
// Sem a API de leitura ligada, só mostra o aviso e o caminho para o app atual; com ela, tudo
// fica atrás do login com o Google (src/app/conta.tsx), menos o link compartilhado (/c), que é público.
import { Route, Routes, useLocation } from "react-router";
import { useConfiguracao } from "./configuracao";
import { ExigeLogin, ProvedorDaConta } from "./conta";
import { Moldura } from "./Moldura";
import { TELAS_DO_APP, telaDa } from "./rotas";
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

export function App() {
  const api = useConfiguracao();
  const { pathname } = useLocation();
  if (api.estado !== "ligada") {
    const aviso = {
      carregando: <Carregando />,
      desligada: <EmPreparacao />,
      "fora do ar": <ForaDoAr />,
    }[api.estado];
    return <Moldura comMenu={false}>{aviso}</Moldura>;
  }
  if (pathname.replace(/\/$/, "") === ROTA_PUBLICA_DO_LINK) {
    return (
      <Moldura comMenu={false}>
        <Compartilhado />
      </Moldura>
    );
  }
  if (!api.googleClientId) {
    return (
      <Moldura comMenu={false}>
        <LoginNaoConfigurado />
      </Moldura>
    );
  }
  return (
    <ProvedorDaConta clientId={api.googleClientId}>
      <Moldura comMenu>
        <ExigeLogin>
          <Routes>
            <Route index element={<Inicio />} />
            {TELAS_DO_APP.map((pagina) => (
              <Route key={pagina.chave} path={pagina.url} element={telaDa(pagina)} />
            ))}
            <Route path="*" element={<NaoEncontrada />} />
          </Routes>
        </ExigeLogin>
      </Moldura>
    </ProvedorDaConta>
  );
}
