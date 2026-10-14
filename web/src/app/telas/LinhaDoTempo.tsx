// Linha do tempo no app novo: a curva do ativo em base 100 (nunca o preço) com um ponto em cada
// documento que a empresa publicou na CVM ou na SEC, e a tabela dos documentos com o link original.
import type { PaginaDoApp } from "../../conteudo";
import { formatarData } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { LinhaDoTempoDoAtivoV1, MarcoV1 } from "../tipos";
import { TelaDoContrato } from "./TelaDoContrato";

/** Só vira link o que é http(s): a API já limpa, e a tela confere de novo (um link "javascript:"
 * rodaria código no navegador de quem clicasse). */
export function linkSeguro(link: string): string | null {
  return /^https?:\/\//i.test(link.trim()) ? link.trim() : null;
}

function Tabela({ marcos }: { marcos: MarcoV1[] }) {
  return (
    <div className="tabela-rolavel">
      <table className="tabela-do-app">
        <caption>Acontecimentos do período</caption>
        <thead>
          <tr>
            <th scope="col">Data</th>
            <th scope="col">Documento</th>
            <th scope="col">Assunto</th>
            <th scope="col">Documento original</th>
          </tr>
        </thead>
        <tbody>
          {marcos.map((m) => {
            const link = linkSeguro(m.link);
            return (
              <tr key={`${m.data}-${m.descricao}`}>
                <td className="numero">{formatarData(m.data)}</td>
                <td>{m.rotulo}</td>
                <td>{m.assunto}</td>
                <td>
                  {link ? (
                    <a href={link} target="_blank" rel="noopener noreferrer">
                      Abrir
                    </a>
                  ) : (
                    <span className="apagado">sem link</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Resultado({ dados }: { dados: LinhaDoTempoDoAtivoV1 }) {
  const linha = dados.linha_do_tempo;
  return (
    <>
      {dados.ativo.aviso_da_origem ? (
        <p className="erro-do-app" role="note">
          {dados.ativo.aviso_da_origem}
        </p>
      ) : null}
      <GraficoDeLinha
        titulo={`${dados.ativo.codigo} em base 100, com os acontecimentos`}
        datas={linha.curva.datas}
        series={[{ nome: dados.ativo.codigo, cor: "var(--serie-1)", valores: linha.curva.valores }]}
        referencia={100}
        marcos={linha.marcos.map((m) => ({ dia: m.dia_no_grafico, valor: m.valor_no_grafico, descricao: m.descricao }))}
      />
      <p className="apagado">{linha.aviso}</p>
      {linha.marcos.length === 0 ? (
        <p>{linha.sem_acontecimentos}</p>
      ) : (
        <Tabela marcos={linha.marcos} />
      )}
      {linha.texto_fora_do_grafico ? <p className="apagado">{linha.texto_fora_do_grafico}</p> : null}
    </>
  );
}

export function LinhaDoTempo({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <TelaDoContrato<LinhaDoTempoDoAtivoV1>
      pagina={pagina}
      carregando="Montando a linha do tempo…"
      resultado={(dados) => <Resultado dados={dados} />}
    />
  );
}
