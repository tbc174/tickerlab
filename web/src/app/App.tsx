// O app em React (série 3 da ADR 0048), servido em app.tickerlab.com.br/novo/ ao lado do Streamlit.
// Sem a API de leitura ligada, só mostra o aviso e o caminho para o app atual.
import { Route, Routes } from "react-router";
import { useConfiguracao } from "./configuracao";
import { Moldura } from "./Moldura";
import { TELAS_DO_APP, telaDa } from "./rotas";
import { Carregando, EmPreparacao, ForaDoAr, NaoEncontrada } from "./telas/Avisos";
import { Inicio } from "./telas/Inicio";

export function App() {
  const api = useConfiguracao();
  if (api.estado !== "ligada") {
    const aviso = {
      carregando: <Carregando />,
      desligada: <EmPreparacao />,
      "fora do ar": <ForaDoAr />,
    }[api.estado];
    return <Moldura comMenu={false}>{aviso}</Moldura>;
  }
  return (
    <Moldura comMenu>
      <Routes>
        <Route index element={<Inicio />} />
        {TELAS_DO_APP.map((pagina) => (
          <Route key={pagina.chave} path={pagina.url} element={telaDa(pagina)} />
        ))}
        <Route path="*" element={<NaoEncontrada />} />
      </Routes>
    </Moldura>
  );
}
