// A página pública do link compartilhado: a ficha "Foi sorte?" congelada ou o PDF original de um
// relatório. Abre sem login; nada aqui diz quem compartilhou.
import { useEffect, useState } from "react";
import { useLocation } from "react-router";
import { URL_DO_SITE } from "../../site/textos";
import {
  type FichaCompartilhadaV1,
  type LinkCompartilhadoV1,
  type PdfCompartilhadoV1,
  NAO_VALE,
  abrirLink,
  baixarPdf,
  codigoDoEndereco,
} from "../compartilhado";
import { VereditoDaFicha } from "../VereditoDaFicha";
import { formatarData, formatarPct } from "../formatar";
import { Carregando } from "./Avisos";

const FUSO = "America/Sao_Paulo";

/** Data e hora da API (UTC) no dia de Brasília: "13/10/2026". */
function dataEmBrasilia(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO }).format(new Date(iso));
}

function valor(v: number | string | boolean): string {
  if (typeof v === "boolean") return v ? "sim" : "não";
  return typeof v === "number" ? String(v).replace(".", ",") : v;
}

function Ficha({ ficha }: { ficha: FichaCompartilhadaV1 }) {
  const ajustes = Object.entries({ ...ficha.parametros, ...ficha.protecoes });
  return (
    <>
      <VereditoDaFicha
        titulo={ficha.titulo_do_veredito}
        texto={ficha.texto_do_veredito}
        checagens={ficha.checagens}
      />
      <p>{ficha.texto_das_tentativas}</p>
      <dl className="ficha-tecnica">
        <dt>Ativo</dt>
        <dd>{ficha.codigo}</dd>
        <dt>Estratégia</dt>
        <dd>
          {ficha.estrategia}
          {ajustes.length > 0 ? ` (${ajustes.map(([k, v]) => `${k}: ${valor(v)}`).join(", ")})` : ""}
        </dd>
        <dt>Período</dt>
        <dd>
          {formatarData(ficha.inicio)} a {formatarData(ficha.fim)}
        </dd>
        <dt>Custo por operação</dt>
        <dd>{formatarPct(ficha.custo_por_operacao)}</dd>
        <dt>Preços</dt>
        <dd>{ficha.fonte}</dd>
      </dl>
      <p className="apagado">
        Calculada em {dataEmBrasilia(ficha.calculada_em)}, com os dados até então. Não é recalculada:
        mostra exatamente o que a pessoa viu.
      </p>
    </>
  );
}

function Pdf({ pdf, codigo }: { pdf: PdfCompartilhadoV1; codigo: string }) {
  const [erro, setErro] = useState<string | null>(null);
  async function baixar() {
    setErro(null);
    try {
      const arquivo = URL.createObjectURL(await baixarPdf(codigo));
      const link = document.createElement("a");
      link.href = arquivo;
      link.download = pdf.nome_do_arquivo;
      link.click();
      URL.revokeObjectURL(arquivo);
    } catch (e) {
      setErro(e instanceof Error ? e.message : NAO_VALE);
    }
  }
  return (
    <>
      <p>
        O relatório em PDF como foi gerado em {dataEmBrasilia(pdf.gerado_em)} (
        {Math.max(1, Math.round(pdf.tamanho / 1024))} KB).
      </p>
      <button type="button" className="botao primario" onClick={() => void baixar()}>
        Baixar o PDF
      </button>
      {erro ? (
        <p className="erro-do-app" role="alert">
          {erro}
        </p>
      ) : null}
      <p className="apagado">
        Para conferir que o arquivo é o original, o SHA-256 dele é: <code>{pdf.sha256}</code>
      </p>
    </>
  );
}

type Estado =
  | { estado: "carregando" }
  | { estado: "erro"; mensagem: string }
  | { estado: "aberto"; link: LinkCompartilhadoV1; codigo: string };

export function Compartilhado() {
  const { hash } = useLocation();
  const [lido, setLido] = useState<Estado>({ estado: "carregando" });
  useEffect(() => {
    const codigo = codigoDoEndereco(hash);
    if (codigo === null) {
      setLido({ estado: "erro", mensagem: NAO_VALE });
      return;
    }
    let valendo = true;
    abrirLink(codigo).then(
      (link) => valendo && setLido({ estado: "aberto", link, codigo }),
      (e: unknown) =>
        valendo && setLido({ estado: "erro", mensagem: e instanceof Error ? e.message : NAO_VALE }),
    );
    return () => {
      valendo = false;
    };
  }, [hash]);

  if (lido.estado === "carregando") return <Carregando />;
  const convite = (
    <p>
      <a className="botao" href={URL_DO_SITE} rel="noopener noreferrer">
        Conheça o TickerLab
      </a>
    </p>
  );
  if (lido.estado === "erro") {
    return (
      <section className="aviso-do-app">
        <h1>Link compartilhado</h1>
        <p role="alert">{lido.mensagem}</p>
        {convite}
      </section>
    );
  }
  const { link, codigo } = lido;
  return (
    <article className="compartilhado">
      <p className="apagado">Compartilhado com você pelo TickerLab · vale até {dataEmBrasilia(link.expira_em)}</p>
      <h1>{link.titulo}</h1>
      {link.ficha ? <Ficha ficha={link.ficha} /> : null}
      {link.pdf ? <Pdf pdf={link.pdf} codigo={codigo} /> : null}
      <p className="apagado">{link.aviso}</p>
      {convite}
    </article>
  );
}
