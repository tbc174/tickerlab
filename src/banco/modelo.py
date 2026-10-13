"""As tabelas do banco de dados (SQLAlchemy Core).

O esquema é criado e alterado só pelas migrações (`migracoes/`). Este arquivo descreve as tabelas
para o código consultar; os tipos são portáteis, então os testes rodam em SQLite e em PostgreSQL.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

CONVENCAO_DE_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

PAPEIS = ("usuario", "admin")
PLANOS = ("gratuito", "plus", "pro")
TIPOS_DE_RELATORIO = (
    "ativo",
    "comparacao",
    "backtest",
    "carteira",
    "minha_carteira",
    "newsletter",
    "empresa",  # relatório completo de empresa (série 2 da base de ML, PR 7)
)

metadata = sa.MetaData(naming_convention=CONVENCAO_DE_NOMES)

# JSON portátil: JSONB no PostgreSQL (permite índices e consultas), JSON comum no resto
JSON_PORTATIL = sa.JSON().with_variant(JSONB(), "postgresql")


def _chave_do_usuario(primaria: bool = False) -> sa.Column:
    return sa.Column(
        "usuario_id",
        sa.Uuid,
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
        primary_key=primaria,
        nullable=False,
    )


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


usuarios = sa.Table(
    "usuarios",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("google_sub", sa.String(64), nullable=False, unique=True),
    sa.Column("email", sa.String(320), nullable=False),
    sa.Column("nome", sa.String(200)),
    sa.Column("foto_url", sa.String(1000)),
    sa.Column("papel", sa.String(20), nullable=False, server_default="usuario"),
    sa.Column("plano", sa.String(20), nullable=False, server_default="gratuito"),
    _momento("criado_em"),
    sa.Column("ultimo_acesso", sa.DateTime(timezone=True)),
    sa.Column("excluido_em", sa.DateTime(timezone=True)),
    # versão dos termos de uso e da política de privacidade que a pessoa aceitou, e quando
    sa.Column("termos_versao", sa.String(20)),
    sa.Column("termos_aceitos_em", sa.DateTime(timezone=True)),
    sa.CheckConstraint("papel IN ('usuario', 'admin')", name="papel"),
    sa.CheckConstraint("plano IN ('gratuito', 'plus', 'pro')", name="plano"),
)
sa.Index("ix_usuarios_email", usuarios.c.email)

preferencias = sa.Table(
    "preferencias",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("dados", JSON_PORTATIL, nullable=False),
    _momento("atualizado_em"),
)

favoritos = sa.Table(
    "favoritos",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("ticker", sa.String(20), primary_key=True),
    sa.Column("ordem", sa.Integer, nullable=False, server_default="0"),
    _momento("criado_em"),
)

# Ficha "Foi sorte?" (0027): cada configuração diferente do backtest que a pessoa rodou num ativo,
# guardada só pela impressão (SHA-256); serve para contar as tentativas (ADR 0037, D2)
tentativas = sa.Table(
    "tentativas",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("ticker", sa.String(20), primary_key=True),
    sa.Column("impressao", sa.String(64), primary_key=True),
    _momento("criada_em"),
)

# Pulse (onda 3, PR E): a última vez que a pessoa abriu o Pulse (o "desde a última visita") e o
# veredito da ficha "Foi sorte?" que ela já viu em cada estratégia salva (id da simulação → resultado)
pulse = sa.Table(
    "pulse",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("visto_em", sa.DateTime(timezone=True), nullable=False),
    sa.Column("vereditos", JSON_PORTATIL, nullable=False),
)

simulacoes = sa.Table(
    "simulacoes",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("tipo", sa.String(30), nullable=False),
    sa.Column("nome", sa.String(120), nullable=False),
    sa.Column("parametros", JSON_PORTATIL, nullable=False),
    sa.Column("resultado", JSON_PORTATIL, nullable=False),
    _momento("criada_em"),
)
sa.Index("ix_simulacoes_usuario_id", simulacoes.c.usuario_id)

# Research (0007): cada mudança de parâmetros é uma versão nova; nada é sobrescrito.
# alvo "" = o padrão do usuário; senão, o ticker (ou a watchlist, numa etapa futura).
ESCOPOS_DE_PRESET = ("global", "watchlist", "ativo")
presets = sa.Table(
    "presets",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("escopo", sa.String(20), nullable=False),
    sa.Column("alvo", sa.String(40), nullable=False, server_default=""),
    sa.Column("versao", sa.Integer, nullable=False),
    sa.Column("nome", sa.String(80), nullable=False, server_default=""),
    sa.Column("parametros", JSON_PORTATIL, nullable=False),
    sa.Column("motivo", sa.String(200), nullable=False, server_default=""),
    _momento("criado_em"),
    sa.CheckConstraint("escopo IN ('global', 'watchlist', 'ativo')", name="escopo"),
    sa.CheckConstraint("versao >= 1", name="versao"),
    sa.UniqueConstraint("usuario_id", "escopo", "alvo", "versao"),
)

# Research (0009): listas com nome (watchlists) de cada usuário
watchlists = sa.Table(
    "watchlists",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("nome", sa.String(60), nullable=False),
    sa.Column("tickers", JSON_PORTATIL, nullable=False),  # na ordem escolhida
    _momento("criado_em"),
    _momento("atualizado_em"),
    sa.UniqueConstraint("usuario_id", "nome"),
)

# Research (0017): a fotografia da carteira (só ticker → peso em %), com consentimento próprio
carteiras_do_research = sa.Table(
    "carteiras_do_research",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("pesos", JSON_PORTATIL, nullable=False),  # {"PETR4.SA": 0.1234, ...}
    sa.Column("enviada_em", sa.Date, nullable=False),
    sa.Column("versao_do_consentimento", sa.String(20), nullable=False),
    _momento("consentido_em"),
)

# Research (0018): Newsletter por e-mail. Inscrição opt-in (uma por usuário) e cada envio
# (a chave usuário + período impede mandar a mesma edição duas vezes)
CADENCIAS_DO_EMAIL = ("diaria", "semanal")
SITUACOES_DO_ENVIO = ("enviado", "retido", "falhou")
inscricoes_da_newsletter = sa.Table(
    "inscricoes_da_newsletter",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("lista", sa.String(60), nullable=False),  # nome da lista no Research
    sa.Column("cadencia", sa.String(20), nullable=False),
    sa.Column("versao_do_consentimento", sa.String(20), nullable=False),
    # código aleatório do link "descadastrar" (funciona sem login)
    sa.Column("codigo_para_sair", sa.String(64), nullable=False, unique=True),
    _momento("inscrito_em"),
    sa.CheckConstraint("cadencia IN ('diaria', 'semanal')", name="cadencia"),
)
envios_da_newsletter = sa.Table(
    "envios_da_newsletter",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("periodo", sa.String(20), primary_key=True),  # "2026-10-12" ou "2026-W42"
    sa.Column("situacao", sa.String(20), nullable=False),
    sa.Column("detalhe", sa.String(200), nullable=False, server_default=""),
    _momento("registrado_em"),
    sa.CheckConstraint("situacao IN ('enviado', 'retido', 'falhou')", name="situacao"),
)

# Research (0015): alertas compostos de cada usuário (a regra em JSON; ver src/alertas.py)
alertas = sa.Table(
    "alertas",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("nome", sa.String(80), nullable=False),
    sa.Column("regra", JSON_PORTATIL, nullable=False),
    _momento("criado_em"),
    _momento("atualizado_em"),
    sa.UniqueConstraint("usuario_id", "nome"),
)

# Research (0010): demonstrações financeiras da CVM (DFP e ITR), dados públicos
demonstracoes = sa.Table(
    "demonstracoes",
    metadata,
    sa.Column("cnpj", sa.String(18), primary_key=True),
    sa.Column("documento", sa.String(3), primary_key=True),  # DFP ou ITR
    sa.Column(
        "referencia", sa.Date, primary_key=True
    ),  # data do balanço / fim do período
    sa.Column(
        "periodo", sa.String(20), primary_key=True
    ),  # posicao, exercicio, acumulado...
    sa.Column("fim", sa.Date, primary_key=True),
    sa.Column(
        "conta", sa.String(30), primary_key=True
    ),  # receita, lucro_liquido, caixa...
    sa.Column("inicio", sa.Date),
    sa.Column("versao", sa.Integer, nullable=False),
    sa.Column("valor", sa.Float, nullable=False),  # em reais (ou quantidade, nas ações)
)
documentos_financeiros = sa.Table(
    "documentos_financeiros",
    metadata,
    sa.Column("cnpj", sa.String(18), primary_key=True),
    sa.Column("documento", sa.String(3), primary_key=True),
    sa.Column("referencia", sa.Date, primary_key=True),
    sa.Column("versao", sa.Integer, nullable=False),
    sa.Column("empresa", sa.String(200), nullable=False),
    sa.Column("recebido_em", sa.Date),  # quando o documento ficou público na CVM
    sa.Column("link", sa.String(500), nullable=False),
    _momento("coletado_em"),
)
setores_cvm = sa.Table(
    "setores_cvm",
    metadata,
    sa.Column("cnpj", sa.String(18), primary_key=True),
    sa.Column("setor", sa.String(120), nullable=False),
)

# Research (0008): dados públicos da CVM, iguais para todos (nada pessoal aqui)
tickers_dos_emissores = sa.Table(
    "tickers_dos_emissores",
    metadata,
    sa.Column("ticker", sa.String(12), primary_key=True),  # PETR4.SA
    sa.Column("codigo", sa.String(8), nullable=False),  # PETR4
    sa.Column("cnpj", sa.String(18), nullable=False),
    sa.Column("empresa", sa.String(200), nullable=False),
    sa.Column("valor_mobiliario", sa.String(80), nullable=False, server_default=""),
    _momento("atualizado_em"),
)
sa.Index("ix_tickers_dos_emissores_cnpj", tickers_dos_emissores.c.cnpj)

eventos = sa.Table(
    "eventos",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("fonte", sa.String(20), nullable=False),  # cvm_ipe
    sa.Column("protocolo", sa.String(60), nullable=False),
    sa.Column("versao", sa.Integer, nullable=False, server_default="1"),
    sa.Column("cnpj", sa.String(18), nullable=False),
    sa.Column("empresa", sa.String(200), nullable=False),
    sa.Column("categoria", sa.String(160), nullable=False),
    sa.Column("tipo", sa.String(300), nullable=False, server_default=""),
    sa.Column("assunto", sa.Text, nullable=False, server_default=""),
    sa.Column("rotulo", sa.String(60), nullable=False),
    sa.Column("tema", sa.String(20), nullable=False),
    sa.Column("materialidade", sa.Integer, nullable=False),
    sa.Column("referencia", sa.Date),  # data a que o documento se refere
    sa.Column(
        "publicado_em", sa.Date, nullable=False
    ),  # quando ficou público (entrega)
    sa.Column("link", sa.String(500), nullable=False),  # documento original na fonte
    _momento("ingerido_em"),
    sa.UniqueConstraint("fonte", "protocolo"),
)
sa.Index("ix_eventos_cnpj_publicado_em", eventos.c.cnpj, eventos.c.publicado_em)

# Radar PR 3 (0024): toda versão de cada evento, só acréscimo. A tabela `eventos` continua sendo a
# vigente (o app não muda); aqui a versão substituída ganha `substituido_em` e nunca é apagada.
eventos_versoes = sa.Table(
    "eventos_versoes",
    metadata,
    sa.Column("fonte", sa.String(20), primary_key=True),
    sa.Column("protocolo", sa.String(60), primary_key=True),
    sa.Column("versao", sa.Integer, primary_key=True),
    sa.Column("cnpj", sa.String(18), nullable=False),
    sa.Column("empresa", sa.String(200), nullable=False),
    sa.Column("categoria", sa.String(160), nullable=False),
    sa.Column("tipo", sa.String(300), nullable=False, server_default=""),
    sa.Column("assunto", sa.Text, nullable=False, server_default=""),
    sa.Column("rotulo", sa.String(60), nullable=False),
    sa.Column("tema", sa.String(20), nullable=False),
    sa.Column("materialidade", sa.Integer, nullable=False),
    sa.Column("referencia", sa.Date),
    sa.Column("publicado_em", sa.Date, nullable=False),
    sa.Column("link", sa.String(500), nullable=False),
    _momento("registrado_em"),
    sa.Column("substituido_em", sa.DateTime(timezone=True)),
)

# Research R2 (0011): compras e vendas de pessoas de dentro (CVM VLMO e SEC Form 4). Dados
# públicos; guardamos só o CARGO, nunca o nome da pessoa (decisão 0018).
negociacoes_internas = sa.Table(
    "negociacoes_internas",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("fonte", sa.String(20), nullable=False),  # cvm_vlmo ou sec_form4
    sa.Column("documento", sa.String(60), nullable=False),  # um documento entregue
    sa.Column("versao", sa.Integer, nullable=False),
    sa.Column("cnpj", sa.String(18), nullable=False),  # CNPJ ou CIK com prefixo
    sa.Column("empresa", sa.String(200), nullable=False),
    sa.Column("cargo", sa.String(20), nullable=False),
    sa.Column("cargo_descricao", sa.String(120), nullable=False, server_default=""),
    sa.Column("operacao", sa.String(10), nullable=False),  # compra ou venda
    sa.Column("ativo", sa.String(80), nullable=False, server_default=""),
    sa.Column("data", sa.Date),  # dia da negociação (pode faltar na CVM)
    sa.Column(
        "referencia", sa.Date, nullable=False
    ),  # mês (CVM) ou data do relatório (SEC)
    sa.Column("entregue_em", sa.Date, nullable=False),  # quando ficou público
    sa.Column("quantidade", sa.Float, nullable=False),
    sa.Column("preco", sa.Float),
    sa.Column("valor", sa.Float),
    sa.Column("moeda", sa.String(3), nullable=False),
    sa.Column("plano_10b5_1", sa.Boolean),  # EUA: venda programada com antecedência
    sa.Column("link", sa.String(500), nullable=False),
    _momento("ingerido_em"),
)
sa.Index(
    "ix_negociacoes_internas_cnpj_data",
    negociacoes_internas.c.cnpj,
    negociacoes_internas.c.entregue_em,
)
sa.Index(
    "ix_negociacoes_internas_documento",
    negociacoes_internas.c.fonte,
    negociacoes_internas.c.documento,
)
# documentos já lidos, mesmo os que não renderam nada (a maioria dos Form 4 não tem compra nem
# venda em bolsa): a coleta não baixa de novo
documentos_lidos = sa.Table(
    "documentos_lidos",
    metadata,
    sa.Column("fonte", sa.String(20), primary_key=True),
    sa.Column("documento", sa.String(60), primary_key=True),
    _momento("lido_em"),
)

assinaturas = sa.Table(
    "assinaturas",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("stripe_customer_id", sa.String(64), nullable=False, unique=True),
    sa.Column("stripe_subscription_id", sa.String(64), unique=True),
    sa.Column("status", sa.String(30), nullable=False),
    sa.Column("periodo_fim", sa.DateTime(timezone=True)),
    sa.Column("cancela_no_fim", sa.Boolean, nullable=False, server_default=sa.false()),
    # momento (do Stripe) do último evento aplicado: eventos mais velhos que isso são ignorados
    sa.Column("evento_em", sa.BigInteger, nullable=False, server_default="0"),
    # o plano que o usuário tinha ao ganhar o Pro: é para ele que volta quando o Pro termina
    sa.Column("plano_sem_o_pro", sa.String(20)),
    _momento("atualizada_em"),
)

# um registro por evento do Stripe já processado: o Stripe repete entregas, e isto evita aplicar
# o mesmo evento duas vezes (idempotência)
eventos_stripe = sa.Table(
    "eventos_stripe",
    metadata,
    sa.Column("id", sa.String(100), primary_key=True),
    sa.Column("tipo", sa.String(100), nullable=False),
    _momento("processado_em"),
)

# registro do que aconteceu de importante (ações de administrador, aceite dos termos, conta
# apagada). Guarda ids, nunca e-mail nem nome: assim sobrevive à exclusão da conta sem manter
# dados pessoais. O ator vira nulo se a conta dele for apagada.
auditoria = sa.Table(
    "auditoria",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("ator_id", sa.Uuid, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
    sa.Column("acao", sa.String(60), nullable=False),
    sa.Column("alvo_id", sa.Uuid),
    sa.Column("detalhes", JSON_PORTATIL, nullable=False),
    _momento("criado_em"),
)
sa.Index("ix_auditoria_criado_em", auditoria.c.criado_em)


# Relatórios em PDF gerados: só o tipo e a hora, para contar o limite do plano (o PDF não é
# guardado). Apagados junto com a conta.
relatorios = sa.Table(
    "relatorios",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("tipo", sa.String(20), nullable=False),
    _momento("criado_em"),
    # biblioteca (0006): título e parâmetros para reabrir; ao excluir, só tipo e hora ficam
    sa.Column("titulo", sa.String(200)),
    sa.Column("parametros", JSON_PORTATIL),
    sa.Column("apagado_em", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "tipo IN ('ativo', 'comparacao', 'backtest', 'carteira', 'minha_carteira', "
        "'newsletter')",
        name="tipo",
    ),
)
sa.Index(
    "ix_relatorios_usuario_id_criado_em",
    relatorios.c.usuario_id,
    relatorios.c.criado_em,
)

# biblioteca (0019, ADR 0021): o PDF original de cada relatório, como foi entregue. Some junto com
# a conta (cascata), ao excluir da biblioteca, depois de 1 ano e quando passa da cota do plano.
# O relatório "Minha carteira" nunca é guardado (a planilha da B3 não fica no TickerLab).
pdfs_originais = sa.Table(
    "pdfs_originais",
    metadata,
    sa.Column(
        "relatorio_id",
        sa.Uuid,
        sa.ForeignKey("relatorios.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    _chave_do_usuario(),
    sa.Column("pdf", sa.LargeBinary, nullable=False),
    sa.Column(
        "sha256", sa.String(64), nullable=False
    ),  # prova de que é o mesmo arquivo
    sa.Column("tamanho", sa.Integer, nullable=False),  # bytes
    # versão das fórmulas, do app e de onde vieram os dados: reproduzir o que o PDF mostrava
    sa.Column("versoes", JSON_PORTATIL, nullable=False),
    _momento("gerado_em"),
)
sa.Index(
    "ix_pdfs_originais_usuario_id_gerado_em",
    pdfs_originais.c.usuario_id,
    pdfs_originais.c.gerado_em,
)

# Research R3 (0012): quem tem cada ação. Fundos da CVM (carteira mensal, CDA) e gestores da SEC
# (13F, trimestral). Nomes de fundos e gestores são de pessoas jurídicas.
detentores_por_acao = sa.Table(
    "detentores_por_acao",
    metadata,
    sa.Column("fonte", sa.String(20), primary_key=True),  # cvm_cda ou sec_13f
    sa.Column("competencia", sa.Date, primary_key=True),  # fim do mês ou do trimestre
    sa.Column("codigo", sa.String(12), primary_key=True),  # PETR4, AAPL
    sa.Column("detentores", sa.Integer, nullable=False),
    sa.Column("valor", sa.Float, nullable=False),
    sa.Column("quantidade", sa.Float, nullable=False),
    sa.Column(
        "vendidos", sa.Integer, nullable=False
    ),  # fundos com posição vendida (só CVM)
    sa.Column("valor_vendido", sa.Float, nullable=False),
    sa.Column("valor_emprestado", sa.Float, nullable=False),
    sa.Column("compras_no_mes", sa.Float, nullable=False),
    sa.Column("vendas_no_mes", sa.Float, nullable=False),
    _momento("coletado_em"),
)
maiores_detentores = sa.Table(
    "maiores_detentores",
    metadata,
    sa.Column("fonte", sa.String(20), primary_key=True),
    sa.Column("competencia", sa.Date, primary_key=True),
    sa.Column("codigo", sa.String(12), primary_key=True),
    sa.Column("tipo", sa.String(10), primary_key=True),  # comprado ou vendido
    sa.Column("posicao", sa.Integer, primary_key=True),  # 1 = o maior
    sa.Column("nome", sa.String(200), nullable=False),
    sa.Column(
        "documento", sa.String(20), nullable=False
    ),  # CNPJ do fundo ou CIK do gestor
    sa.Column("valor", sa.Float, nullable=False),
    sa.Column("quantidade", sa.Float, nullable=False),
)
# quantos fundos (ou gestores) informaram posições em cada competência: a cobertura do arquivo.
# Muda muito (sigilo de até 90 dias na CVM; mês recente ainda chegando) e decide o que comparar.
cobertura_de_detentores = sa.Table(
    "cobertura_de_detentores",
    metadata,
    sa.Column("fonte", sa.String(20), primary_key=True),
    sa.Column("competencia", sa.Date, primary_key=True),
    sa.Column("informantes", sa.Integer, nullable=False),
    _momento("coletado_em"),
)

# Research R4 (0014): ações dos EUA fora do S&P 500 buscadas na hora por alguém; entram na coleta
# diária da SEC. Sem `usuario_id`: guarda só o ticker e quando foi pedido (nada pessoal).
tickers_sob_demanda = sa.Table(
    "tickers_sob_demanda",
    metadata,
    sa.Column("ticker", sa.String(12), primary_key=True),
    sa.Column("cnpj", sa.String(18), nullable=False),  # o CIK com prefixo
    _momento("pedido_em"),
)

# Research R5 (0016): leitura dos documentos pelo algoritmo próprio (src/leitura.py). Dados
# públicos: o resumo de cada fato relevante e a comparação dos fatores de risco dos 10-K.
leituras = sa.Table(
    "leituras",
    metadata,
    sa.Column("fonte", sa.String(20), primary_key=True),  # cvm_ipe ou sec_edgar
    sa.Column(
        "documento", sa.String(60), primary_key=True
    ),  # protocolo do documento lido
    sa.Column("tipo", sa.String(20), primary_key=True),  # resumo ou riscos
    sa.Column("cnpj", sa.String(18), nullable=False),
    sa.Column("referencia", sa.Date),
    sa.Column("resultado", JSON_PORTATIL, nullable=False),
    sa.Column("versao", sa.String(10), nullable=False),
    _momento("lido_em"),
)
sa.Index("ix_leituras_cnpj", leituras.c.cnpj)
# Radar, PR 1 (ADR 0024 do autor): uma linha por arquivo baixado das fontes oficiais, com de onde
# veio, quando, o tamanho, o SHA-256 e a licença. Só dado público: nada de usuário aqui.
SITUACOES_DA_COLETA = ("ok", "nao_encontrado", "falhou")
coletas = sa.Table(
    "coletas",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("fonte", sa.String(40), nullable=False),  # ex.: cvm-ipe, sec-13f
    sa.Column("url", sa.String(1000), nullable=False),
    sa.Column("situacao", sa.String(20), nullable=False),
    sa.Column("bytes", sa.BigInteger),
    sa.Column("sha256", sa.String(64)),
    sa.Column("licenca", sa.String(80), nullable=False),
    sa.Column("detalhe", sa.String(300)),
    sa.Column("caminho_do_original", sa.String(200)),  # no acervo (src/acervo.py)
    _momento("baixado_em"),
    sa.CheckConstraint(
        "situacao IN ('ok', 'nao_encontrado', 'falhou')", name="ck_coletas_situacao"
    ),
)
sa.Index("ix_coletas_fonte_baixado_em", coletas.c.fonte, coletas.c.baixado_em)

# Séries macro com safras (Radar, PR 5; ADR 0024 do autor): só acréscimo. Uma revisão oficial
# acrescenta uma linha com o novo `divulgado_em`; a anterior nunca é apagada.
series = sa.Table(
    "series",
    metadata,
    sa.Column("codigo", sa.String(60), primary_key=True),  # ex.: bcb-sgs-433
    sa.Column("nome", sa.String(120), nullable=False),
    sa.Column("unidade", sa.String(40), nullable=False),
    sa.Column("frequencia", sa.String(20), nullable=False),
    sa.Column("licenca", sa.String(80), nullable=False),
    # Yahoo: guardado só para uso interno, nunca exportado nem redistribuído (ADR 0024)
    sa.Column("uso_interno", sa.Boolean, nullable=False, server_default=sa.false()),
)

observacoes = sa.Table(
    "observacoes",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "serie",
        sa.String(60),
        sa.ForeignKey("series.codigo", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "referencia", sa.Date, nullable=False
    ),  # o período a que o valor se refere
    sa.Column("valor", sa.Float, nullable=False),
    sa.Column("divulgado_em", sa.Date, nullable=False),  # a safra
    _momento("registrado_em"),
)
sa.Index(
    "ix_observacoes_serie_referencia",
    observacoes.c.serie,
    observacoes.c.referencia,
    observacoes.c.divulgado_em,
)

# Radar PR 4 (0025): toda versão das demonstrações, negociações e detentores, só acréscimo. As
# tabelas de cima continuam sendo as vigentes (o app não muda); aqui a versão substituída ganha
# `substituido_em` e nunca é apagada. As colunas são as da original, menos as de controle.
CHAVES_DAS_VERSOES = {
    "demonstracoes": ("cnpj", "documento", "referencia"),
    "documentos_financeiros": ("cnpj", "documento", "referencia"),
    "negociacoes_internas": ("fonte", "documento"),
    "detentores_por_acao": ("fonte", "competencia"),
    "maiores_detentores": ("fonte", "competencia"),
    "cobertura_de_detentores": ("fonte", "competencia"),
}
COLUNAS_DE_CONTROLE = ("id", "ingerido_em", "coletado_em")


def _versoes_de(original: sa.Table) -> sa.Table:
    versoes = sa.Table(
        f"{original.name}_versoes",
        metadata,
        sa.Column(
            "id_da_versao",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        *[
            sa.Column(c.name, c.type, nullable=c.nullable)
            for c in original.columns
            if c.name not in COLUNAS_DE_CONTROLE
        ],
        _momento("registrado_em"),
        sa.Column("substituido_em", sa.DateTime(timezone=True)),
    )
    chave = CHAVES_DAS_VERSOES[original.name]
    sa.Index(f"ix_{versoes.name}_chave", *[versoes.c[c] for c in chave])
    return versoes


demonstracoes_versoes = _versoes_de(demonstracoes)
documentos_financeiros_versoes = _versoes_de(documentos_financeiros)
negociacoes_internas_versoes = _versoes_de(negociacoes_internas)
detentores_por_acao_versoes = _versoes_de(detentores_por_acao)
maiores_detentores_versoes = _versoes_de(maiores_detentores)
cobertura_de_detentores_versoes = _versoes_de(cobertura_de_detentores)

# Série 1 da base de ML, PR 3 (0026; ADRs 0027 e 0028 do autor): os achados das regras fixas do
# selo "dado em conferência" (`base/regras.py`). Só acréscimo: o achado que some numa rodada nova
# ganha `fechado_em` e nunca é apagado. "Como era em D" = `valido_desde` até D e não fechado até D.
achados_de_qualidade = sa.Table(
    "achados_de_qualidade",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("regra", sa.String(4), nullable=False),  # R1 a R11
    sa.Column("cnpj", sa.String(18), nullable=False),
    sa.Column("documento", sa.String(3), nullable=False),  # DFP ou ITR
    sa.Column("referencia", sa.Date, nullable=False),
    sa.Column(
        "grupo", sa.String(3), nullable=False, server_default=""
    ),  # con, ind ou vazio
    sa.Column("conta", sa.String(20), nullable=False, server_default=""),
    sa.Column("valor", sa.Float),
    sa.Column("valor_esperado", sa.Float),
    sa.Column("porque", sa.Text, nullable=False),
    sa.Column("versao_das_regras", sa.String(10), nullable=False),
    # quando a informação passou a existir (a entrega do documento): o selo histórico não olha o futuro
    sa.Column("valido_desde", sa.DateTime(timezone=True), nullable=False),
    sa.Column("calculado_em", sa.DateTime(timezone=True), nullable=False),
    sa.Column("fechado_em", sa.DateTime(timezone=True)),
)
sa.Index(
    "ix_achados_de_qualidade_cnpj_referencia",
    achados_de_qualidade.c.cnpj,
    achados_de_qualidade.c.referencia,
)
sa.Index(
    "ix_achados_de_qualidade_documento_referencia",
    achados_de_qualidade.c.documento,
    achados_de_qualidade.c.referencia,
)

# Série 2 da base de ML, PR 4 (0028; ADR 0033): os padrões por setor que as notas usam (percentis
# de cada indicador por grupo de setores, calculados só com o que era público na data de corte).
# É dado derivado: recalcular o mesmo corte substitui as linhas dele.
padroes_setoriais = sa.Table(
    "padroes_setoriais",
    metadata,
    sa.Column("data_de_corte", sa.Date, primary_key=True),
    sa.Column("grupo", sa.String(30), primary_key=True),  # src/setores.py
    sa.Column(
        "indicador", sa.String(40), primary_key=True
    ),  # src/padroes.py::INDICADORES
    sa.Column("versao", sa.String(10), primary_key=True),
    sa.Column("empresas", sa.Integer, nullable=False),
    sa.Column(
        "percentis", JSON_PORTATIL, nullable=False
    ),  # {"10": 0.03, "50": 0.08, ...}
    sa.Column("calculado_em", sa.DateTime(timezone=True), nullable=False),
)

# Série 2 da base de ML, PR 6 (0029): proventos e eventos de capital do FRE (até o FRE de 2022,
# quando a CVM tirou essas tabelas do FRE aberto). O mesmo exercício aparece no FRE de vários anos:
# fica o documento mais novo.
fre_proventos = sa.Table(
    "fre_proventos",
    metadata,
    sa.Column("cnpj", sa.String(18), primary_key=True),
    sa.Column("exercicio", sa.Date, primary_key=True),  # fim do exercício social
    sa.Column("referencia", sa.Date, nullable=False),  # o FRE de onde veio
    sa.Column("versao", sa.Integer, nullable=False),
    sa.Column("lucro_ajustado", sa.Float),
    sa.Column("dividendo_total", sa.Float),
    sa.Column("payout", sa.Float),  # fração do lucro ajustado (0,5 = 50%)
    sa.Column("dividendos", sa.Float),
    sa.Column("jcp", sa.Float),
    _momento("coletado_em"),
)
fre_eventos_de_capital = sa.Table(
    "fre_eventos_de_capital",
    metadata,
    sa.Column("cnpj", sa.String(18), primary_key=True),
    # desdobramento, grupamento, bonificação ou aumento
    sa.Column("tipo", sa.String(30), primary_key=True),
    sa.Column("data", sa.Date, primary_key=True),  # aprovação ou deliberação
    # ações depois do evento (ou as novas, no aumento)
    sa.Column("quantidade", sa.BigInteger, primary_key=True),
    sa.Column("referencia", sa.Date, nullable=False),
    sa.Column("versao", sa.Integer, nullable=False),
    sa.Column("acoes_antes", sa.Float),
    sa.Column("acoes_depois", sa.Float),
    sa.Column("fator", sa.Float),  # depois / antes (desdobramento de 1 para 10 = 10)
    sa.Column("acoes_novas", sa.Float),
    sa.Column("valor", sa.Float),
    _momento("coletado_em"),
)
