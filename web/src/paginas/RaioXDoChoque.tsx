// Raio-X do choque de 26/10/2026 (circuit breaker no dia seguinte ao 2º turno): o estudo pronto, com
// os números, os gráficos e os limites. Ele é feito fora do build, pela análise do dia (preços, CVM,
// IF.data do BC), e guardado em raio-x/: corpo.html (o texto) e dados.json (os números da chamada
// da página inicial). Aqui o estudo só entra na moldura do site, sem login.
import { join } from "node:path";
import { lerTexto } from "../arquivos";
import { Bruto } from "../site/Bruto";
import { ChamadaFinal } from "../site/comum";
import { TopoDaPagina } from "../site/Fundo";
import estudo from "./raio-x/dados.json";

export const RAIO_X = estudo;
export const PDF_DO_RAIO_X = "/estudos/raio-x-do-choque-2026-10-26.pdf";

export const DADOS = {
  caminho: "/raio-x-do-choque.html",
  titulo: "Raio-X do choque de 26/10/2026",
  descricao:
    "Quem caiu mais no circuit breaker de 26/10/2026 e por quê: beta, a alta entre os turnos, " +
    "dívida, setores e o Joesley Day, com fonte em cada número.",
  atual: "/relatorios.html",
  avisoRodape:
    "Nada aqui é recomendação de investimento. Os preços deste estudo são da B3; as demais " +
    "fontes e datas estão descritas no estudo. Rentabilidade passada não garante resultado futuro.",
  imagem: "/estudos/raio-x-do-choque-2026-10-26.png",
};

/** "Versão parcial (12h59)" enquanto o pregão não fechou; depois, "com o fechamento". */
export const MOMENTO_DO_RAIO_X = RAIO_X.parcial
  ? `versão parcial, com preços das ${RAIO_X.hora}`
  : "com os preços de fechamento";

const CORPO = lerTexto(join(process.cwd(), "src", "paginas", "raio-x", "corpo.html"));

export function RaioXDoChoque() {
  return (
    <>
      <TopoDaPagina
        olho="Raio-X do choque · 26/10/2026"
        titulo={RAIO_X.titulo}
        subtitulo={RAIO_X.subtitulo}
      />
      <Bruto html={CORPO} />
      <section className="faixa rx-baixar" aria-label="O estudo em PDF">
        <a className="botao secundario" href={PDF_DO_RAIO_X}>
          Baixar o Raio-X em PDF
        </a>
      </section>
      <ChamadaFinal />
    </>
  );
}
