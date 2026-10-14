// Fontes e metodologia: de onde vêm os números, como são calculados e o que eles não dizem.
// Era `metodologia()` de scripts/gerar_site.py.
import { metodologia, qualidade } from "../conteudo";
import { EMAIL_DE_CONTATO, URL_DO_CODIGO } from "../site/textos";

export const DADOS = {
  caminho: "/metodologia.html",
  titulo: "Fontes e metodologia",
  descricao:
    "De onde vêm os dados do TickerLab, como os números são calculados, as notas e os padrões " +
    "do relatório de empresa, os limites dos testes de estratégia e a privacidade.",
  atual: "/metodologia.html",
};

/** O selo "dado em conferência" e as regras fixas, com os mesmos textos do app. */
function QualidadeDosDados() {
  return (
    <>
      <h2 id={qualidade.ancora}>Qualidade dos dados: o selo "{qualidade.titulo_do_selo}"</h2>
      <p>{qualidade.explicacao}</p>
      <p>
        Todo dia, depois da coleta, regras fixas conferem as demonstrações da CVM (DFP e ITR). Na
        página Fundamentos, o documento com achado ganha o selo, e cada achado traz o porquê, com
        os números. As regras são as mesmas para todas as empresas; mudou uma regra, muda a
        versão e os achados são refeitos. Regras em uso:
      </p>
      <ul>
        {qualidade.regras.map((r) => (
          <li key={r.titulo}>
            <strong>{r.titulo}:</strong> {r.o_que_confere}
          </li>
        ))}
      </ul>
      <p>
        Cada achado vale a partir do dia em que a informação ficou pública (a entrega do
        documento): ao olhar o passado, o selo mostra só o que se podia saber naquela data.
      </p>
    </>
  );
}

/** Padrões por setor, notas e fórmulas do Relatório da empresa, com os mesmos textos do app. */
function PadroesNotasEFormulas() {
  return (
    <>
      <h2 id={metodologia.ancora}>Relatório da empresa: padrões, notas e fórmulas</h2>
      <h3>Padrões por setor</h3>
      {metodologia.padroes.map((p) => (
        <p key={p}>{p}</p>
      ))}
      <p>Grupos de setores (pelo setor que a empresa informa à CVM):</p>
      <ul>
        {metodologia.grupos.map((g) => (
          <li key={g.nome}>
            <strong>{g.nome}:</strong> {g.setores_da_cvm}
          </li>
        ))}
      </ul>
      <h3>Notas</h3>
      {metodologia.notas.map((p) => (
        <p key={p}>{p}</p>
      ))}
      <p>A direção de cada indicador com nota de qualidade:</p>
      <ul>
        {metodologia.indicadores.map((i) => (
          <li key={i.nome}>
            <strong>{i.nome}:</strong> {i.direcao}
          </li>
        ))}
      </ul>
      <h3>Fórmulas</h3>
      <ul>
        {metodologia.formulas.map((f) => (
          <li key={f.nome}>
            <strong>{f.nome}:</strong> <code>{f.formula}</code>. {f.leitura}
          </li>
        ))}
      </ul>
    </>
  );
}

export function Metodologia() {
  return (
    <section className="faixa secao estreita texto-longo">
      <p className="olho">Confiança</p>
      <h1>Fontes e metodologia</h1>
      <p className="subtitulo">De onde vêm os números, como são calculados e o que eles não dizem.</p>

      <h2>Dados de mercado</h2>
      <ul>
        <li>
          <strong>Fonte:</strong> Yahoo Finance, histórico diário de preços de fechamento,
          ajustados por dividendos e desdobramentos. O CDI e a Selic vêm do Banco Central.
        </li>
        <li>
          <strong>Não é tempo real.</strong> Os dados podem ter atraso, lacunas e ajustes
          posteriores. O app guarda um histórico para não depender do Yahoo a cada visita e avisa
          quando usa dados guardados ou de exemplo.
        </li>
        <li>
          <strong>Cobertura da busca:</strong> ações, units, FIIs, ETFs e BDRs negociados na B3
          (cadastro público da B3), as empresas do S&amp;P 500, os principais índices, cinco
          criptomoedas e câmbio. Outros códigos do Yahoo também podem ser digitados.
        </li>
      </ul>

      <h2>Como os números são calculados</h2>
      <ul>
        <li>Retornos diários a partir do fechamento; ano de 252 pregões.</li>
        <li>Volatilidade: desvio padrão dos retornos diários, anualizado.</li>
        <li>
          Índice de Sharpe: retorno anualizado menos a taxa livre de risco, dividido pela
          volatilidade anual.
        </li>
        <li>Maior queda (drawdown): a pior queda a partir de um topo anterior.</li>
      </ul>

      <h2>Testes de estratégia (backtest)</h2>
      <ul>
        <li>
          <strong>Sem olhar o futuro:</strong> a decisão tomada com o fechamento de um dia só vale
          a partir do dia seguinte.
        </li>
        <li>
          <strong>Com custos:</strong> cada compra e venda paga um custo; há também imposto e o
          rendimento do CDI no caixa nas páginas que permitem.
        </li>
        <li>
          <strong>Validação:</strong> treino e teste, walk-forward, teste contra o acaso e Sharpe
          deflacionado, para separar sorte de padrão.
        </li>
        <li>
          <strong>Limites:</strong> não há derrapagem nem falta de liquidez na simulação, e os
          ativos escolhidos hoje carregam viés de sobrevivência.
        </li>
      </ul>

      <h2>Research: eventos e fundamentos</h2>
      <ul>
        <li>
          <strong>Eventos:</strong> os documentos que as empresas entregam aos reguladores, lidos
          uma vez por dia. Da <strong>CVM</strong> (empresas da B3): fatos relevantes,
          comunicados, avisos, proventos e resultados. Da <strong>SEC</strong> (empresas do
          S&amp;P 500): 8-K (resultados, mudanças na diretoria, aquisições...), 10-K (anual) e
          10-Q (trimestral). Cada evento tem o link para o documento original.
        </li>
        <li>
          <strong>Sinais de alerta:</strong> balanço (DFP ou ITR) entregue à CVM depois do prazo
          legal (a data de entrega é oficial; o prazo é calculado pelo TickerLab, sem feriados),
          aviso de atraso nos EUA (NT 10-K e NT 10-Q), troca de auditor, mudança de controle e
          vencimento antecipado de dívida.
        </li>
        <li>
          <strong>Participações:</strong> investidores que declaram ter 5% ou mais de uma empresa
          dos EUA (13D, com intenção ativa, e 13G, passivo).
        </li>
        <li>
          <strong>Pessoas de dentro:</strong> compras e vendas de ações por controladores,
          diretores e conselheiros. Na B3, o formulário mensal da CVM (somado por cargo, publicado
          até o dia 10 do mês seguinte); nos EUA, o Form 4 da SEC (em até 2 dias úteis, com a
          marcação de venda programada pelo plano 10b5-1). Mostramos o <strong>cargo</strong>,
          nunca o nome. Pela pesquisa, as compras costumam dizer mais que as vendas; ainda assim,
          é um fato, não uma recomendação.
        </li>
        <li>
          <strong>Donos e fundos:</strong> quais fundos brasileiros têm cada ação da B3 (carteira
          mensal entregue à CVM, com as posições vendidas, a aposta na queda) e quais grandes
          gestores têm cada ação dos EUA (Form 13F trimestral da SEC). Como muitos fundos mantêm
          posições em sigilo por até 90 dias, mostramos a fatia dos fundos que informaram e só
          comparamos meses com cobertura parecida.
        </li>
        <li>
          <strong>Newsletter:</strong> a edição da sua lista junta tudo isso num só lugar, na tela
          ou em PDF. É montada só com fatos dos documentos oficiais, em frases de modelo fixo
          (sem inteligência artificial), com o link de cada item, os parâmetros usados e os
          limites.
        </li>
        <li>
          <strong>Relevância:</strong> a ordem da lista vem de pesos que você ajusta (tipo do
          evento, quão recente é, a fonte). É uma regra editorial para organizar a leitura, não
          uma previsão de preço.
        </li>
        <li>
          <strong>Fundamentos:</strong> receita, margens, ROE, ROIC, dívida e múltiplos nos
          últimos 12 meses. Na B3, das demonstrações da CVM (DFP e ITR); nos EUA, dos números que
          as empresas marcam em XBRL nos relatórios 10-K e 10-Q entregues à SEC, respeitando o
          ano fiscal de cada uma (o da Apple termina em setembro). Bancos e seguradoras aparecem
          como "não se aplica" onde o indicador não faz sentido.
        </li>
      </ul>
      <QualidadeDosDados />
      <PadroesNotasEFormulas />
      <h2>Carteira B3</h2>
      <p>
        A API da Área do Investidor da B3 só atende empresas credenciadas (com CNPJ, certificado
        digital e contrato). O TickerLab não tem essa conexão. Você baixa a planilha de posição
        na Área do Investidor e a envia no app: ela é lida <strong>só na memória</strong>, não
        fica guardada e não vai para os registros. A análise usa os pesos de hoje no passado:
        mostra risco e concentração, não o seu resultado real.
      </p>

      <h2>Relatórios em PDF</h2>
      <p>
        Os relatórios usam os mesmos cálculos do app. Cada um traz a data e a hora da coleta dos
        dados, os parâmetros, a seção "Metodologia e reprodutibilidade" e a seção obrigatória
        "Limites e cuidados". O resumo executivo só repete, em frases neutras, números do próprio
        relatório.
      </p>

      <h2>Privacidade e segurança</h2>
      <ul>
        <li>Login com o Google; o app não vê nem guarda a sua senha.</li>
        <li>Você exporta os seus dados (JSON) e apaga a conta quando quiser.</li>
        <li>O site e o app não usam Google Fonts nem ferramentas de análise de terceiros.</li>
        <li>Pagamentos (em modo de teste) pelo Stripe; o TickerLab não recebe dados de cartão.</li>
      </ul>
      <p>
        Detalhes na <a href="/privacidade.html">Política de privacidade</a>.
      </p>

      <h2>O que o TickerLab não é</h2>
      <p>
        Não é corretora, não executa ordens, não é consultoria e não é recomendação de
        investimento. É uma plataforma de informação e análise por assinatura; o enquadramento
        regulatório da oferta comercial está em avaliação.
      </p>
      <p>
        Dúvidas, correções e pedidos: <a href={`mailto:${EMAIL_DE_CONTATO}`}>{EMAIL_DE_CONTATO}</a>
        .
      </p>
      <p className="apagado">
        Código aberto para conferência:{" "}
        <a href={URL_DO_CODIGO} rel="noopener">
          {URL_DO_CODIGO.replace(/^https:\/\//, "")}
        </a>
        .
      </p>
    </section>
  );
}
