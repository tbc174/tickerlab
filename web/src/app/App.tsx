// O app em React (série 3 da ADR 0048), o principal em app.tickerlab.com.br/; o Streamlit é a versão
// clássica em /classico. Link antigo de página que ainda só existe lá é levado para lá (src/app/rotas.tsx).
// Sem a API de leitura ligada, só mostra o aviso e o caminho para a versão clássica; com ela, tudo
// fica atrás do login com o Google (src/app/conta.tsx), menos o link compartilhado (/c), que é público.
import { Navigate, Route, Routes, useLocation } from "react-router";
import { useConfiguracao } from "./configuracao";
import { ExigeLogin, ProvedorDaConta } from "./conta";
import { Moldura } from "./Moldura";
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

export function App() {
  const api = useConfiguracao();
  const { pathname } = useLocation();
  // o link antigo vem antes de tudo: não depende da API ligada nem do login do app novo
  const doClassico = enderecoSoDoClassico(pathname);
  if (doClassico !== null) {
    return (
      <Moldura comMenu={false}>
        <ParaOClassico endereco={doClassico} />
      </Moldura>
    );
  }
  if (eAInicialDoClassico(pathname)) return <Navigate to="/" replace />;
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
      {/* a moldura (menu, topo e rodapé) só depois de entrar: antes, a página de entrada */}
      <ExigeLogin>
        <Moldura comMenu aviso={pathname.replace(/\/$/, "") === "/radar-imobiliario" ? "Nada aqui é recomendação de investimento. O radar usa dados das prefeituras, sujeitos a revisões. Consulte as fontes, o método e os limites na própria tela." : undefined}>
          <Routes>
            <Route index element={<Inicio />} />
            {TELAS_DO_APP.map((pagina) => (
              <Route key={pagina.chave} path={pagina.url} element={telaDa(pagina)} />
            ))}
            <Route path="*" element={<NaoEncontrada />} />
          </Routes>
        </Moldura>
      </ExigeLogin>
    </ProvedorDaConta>
  );
}
