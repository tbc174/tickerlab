// O campo de setor das ferramentas do analista: uma caixa de busca nas atividades do CNAE (o combobox com lista
// do WAI-ARIA, como o campo Ativo). Digita-se o nome ("farmácia", "transporte de carga") ou o código; as setas
// andam na lista, Enter escolhe e Esc fecha; no celular, toca-se na sugestão. Cada sugestão mostra o nome e o
// código. Quem sabe o código digita os 5 ou 7 dígitos e segue sem escolher na lista.
import { useEffect, useState } from "react";
import { type AtividadeDoCnae, carregarCnaes, cnaeComPontuacao, sugestoesDeCnae } from "../buscaDeCnaes";
import { CaixaDeSugestoes } from "./CaixaDeSugestoes";

/** As atividades do CNAE, carregadas quando a tela abre (null enquanto não chegam). */
export function useAtividadesDoCnae(): AtividadeDoCnae[] | null {
  const [atividades, setAtividades] = useState<AtividadeDoCnae[] | null>(null);
  useEffect(() => {
    let viva = true;
    void carregarCnaes().then((lista) => {
      if (viva) setAtividades(lista);
    });
    return () => {
      viva = false;
    };
  }, []);
  return atividades;
}

interface Propriedades {
  rotulo: string;
  texto: string;
  atividades: AtividadeDoCnae[] | null;
  dica?: string; // a linha de baixo (o código escolhido, ou como usar o campo)
  aoDigitar(texto: string): void;
  aoEscolher(atividade: AtividadeDoCnae): void;
}

export function CampoDoSetor({ rotulo, texto, atividades, dica, aoDigitar, aoEscolher }: Propriedades) {
  const sugestoes = (digitado: string) =>
    (atividades ? sugestoesDeCnae(atividades, digitado) : []).map((a) => ({
      chave: a.codigo,
      nome: a.nome,
      codigo: cnaeComPontuacao(a.codigo),
    }));
  const escolher = (codigo: string) => {
    const atividade = atividades?.find((a) => a.codigo === codigo);
    if (atividade) aoEscolher(atividade);
  };
  return (
    <CaixaDeSugestoes
      rotulo={rotulo}
      texto={texto}
      sugestoes={sugestoes}
      rotuloDaLista="Atividades do CNAE"
      placeholder="Ex.: farmácia, transporte de carga ou 4771-7/01"
      dica={dica}
      aoDigitar={aoDigitar}
      aoEscolher={escolher}
    />
  );
}
