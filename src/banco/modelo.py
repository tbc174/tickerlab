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
# por que uma conta foi bloqueada no incidente (0045): só o código, nunca texto livre
MOTIVOS_DO_BLOQUEIO = ("abuso", "acesso_de_terceiro", "incidente", "pedido_do_titular")
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
    # vazio na conta criada pela Microsoft ou por e-mail (0039); a fonte é a tabela identidades
    sa.Column("google_sub", sa.String(64), unique=True),
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
    # bloqueio de uma conta só, no incidente (0045): o login e as sessões param, nada se apaga
    sa.Column("bloqueada_em", sa.DateTime(timezone=True)),
    sa.Column("motivo_do_bloqueio", sa.String(30)),
    sa.CheckConstraint("papel IN ('usuario', 'admin')", name="papel"),
    sa.CheckConstraint("plano IN ('gratuito', 'plus', 'pro')", name="plano"),
    sa.CheckConstraint(
        "motivo_do_bloqueio IS NULL OR motivo_do_bloqueio IN ("
        + ", ".join(f"'{m}'" for m in MOTIVOS_DO_BLOQUEIO)
        + ")",
        name="motivo_do_bloqueio",
    ),
    sa.CheckConstraint(
        "(bloqueada_em IS NULL) = (motivo_do_bloqueio IS NULL)", name="bloqueio"
    ),
)
sa.Index("ix_usuarios_email", usuarios.c.email)

PROVEDORES_DE_LOGIN = ("google", "microsoft", "email")
_REGRA_DOS_PROVEDORES = "provedor IN ('google', 'microsoft', 'email')"

# Formas de entrar (0039): cada uma é um provedor + o identificador dele, ligada a uma conta. O e-mail
# confirmado é o que permite juntar duas formas de entrar na mesma conta (src/banco/usuarios.py)
identidades = sa.Table(
    "identidades",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("provedor", sa.String(20), nullable=False),
    sa.Column("sub", sa.String(255), nullable=False),
    sa.Column("email", sa.String(320), nullable=False),
    sa.Column("email_confirmado", sa.Boolean, nullable=False),
    _momento("criada_em"),
    sa.Column("ultimo_uso", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("provedor", "sub"),
    sa.CheckConstraint(_REGRA_DOS_PROVEDORES, name="provedor"),
)
sa.Index("ix_identidades_usuario_id", identidades.c.usuario_id)
sa.Index("ix_identidades_email", identidades.c.email)

# Sessões do app novo (0039): o cookie leva um código aleatório; aqui fica só o hash dele
sessoes_de_login = sa.Table(
    "sessoes_de_login",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("hash_do_token", sa.String(64), nullable=False, unique=True),
    sa.Column("provedor", sa.String(20), nullable=False),
    _momento("criada_em"),
    sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ultimo_uso", sa.DateTime(timezone=True)),
    sa.Column("encerrada_em", sa.DateTime(timezone=True)),
    sa.CheckConstraint(_REGRA_DOS_PROVEDORES, name="provedor"),
)
sa.Index("ix_sessoes_de_login_usuario_id", sessoes_de_login.c.usuario_id)

# Códigos de entrada por e-mail (0039): só hashes, sem chave para a conta (o primeiro acesso ainda
# não tem conta). Uso no PR 2 do login
codigos_de_entrada = sa.Table(
    "codigos_de_entrada",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("hash_do_email", sa.String(64), nullable=False),
    sa.Column("hash_do_codigo", sa.String(64), nullable=False),
    _momento("criado_em"),
    sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
    sa.Column("tentativas", sa.Integer, nullable=False, server_default="0"),
    sa.Column("usado_em", sa.DateTime(timezone=True)),
)
sa.Index("ix_codigos_de_entrada_hash_do_email", codigos_de_entrada.c.hash_do_email)

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

# Campanha (0035): de onde veio cada cadastro, lido do cookie próprio `tl_origem` no primeiro
# login (src/origem.py). Só a primeira origem fica; nada vai para Google ou Meta
origens_do_cadastro = sa.Table(
    "origens_do_cadastro",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("utm_source", sa.String(60)),
    sa.Column("utm_medium", sa.String(60)),
    sa.Column("utm_campaign", sa.String(60)),
    sa.Column("utm_content", sa.String(60)),
    sa.Column("ref", sa.String(60)),
    sa.Column("primeira_visita", sa.Date),
    _momento("gravada_em"),
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

# Diário de Teses (onda 3, PR F): anotações datadas da pessoa sobre um ativo. Não se editam (só se
# apagam), para o diário mostrar o que ela pensava naquele dia.
TAMANHO_MAXIMO_DA_TESE = 2000  # caracteres
teses = sa.Table(
    "teses",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("ticker", sa.String(20), nullable=False),
    sa.Column("texto", sa.Text, nullable=False),
    _momento("criada_em"),
    sa.CheckConstraint(
        f"length(texto) BETWEEN 1 AND {TAMANHO_MAXIMO_DA_TESE}", name="texto"
    ),
)
sa.Index("ix_teses_usuario_id_ticker", teses.c.usuario_id, teses.c.ticker)

# Os backtests salvos que sustentam cada anotação: apagar um dos dois apaga só a ligação
teses_estrategias = sa.Table(
    "teses_estrategias",
    metadata,
    sa.Column(
        "tese_id",
        sa.Uuid,
        sa.ForeignKey("teses.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "simulacao_id",
        sa.Uuid,
        sa.ForeignKey("simulacoes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
sa.Index("ix_teses_estrategias_simulacao_id", teses_estrategias.c.simulacao_id)

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

# Novidades e ofertas do TickerLab por e-mail (0037): opt-in próprio, separado da Newsletter e dos
# termos (o e-mail do login serve só para a conta). Uma inscrição por usuário e cada envio (a chave
# usuário + campanha impede mandar a mesma campanha duas vezes)
inscricoes_de_novidades = sa.Table(
    "inscricoes_de_novidades",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("versao_do_consentimento", sa.String(20), nullable=False),
    # código aleatório do link "sair" (funciona sem login)
    sa.Column("codigo_para_sair", sa.String(64), nullable=False, unique=True),
    _momento("inscrito_em"),
)
envios_de_novidades = sa.Table(
    "envios_de_novidades",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("campanha", sa.String(80), primary_key=True),  # "2026-11-lancamento"
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
# o cadastro público da companhia (cad_cia_aberta.csv): setor e, desde a 0044, situação, categoria e
# registro na CVM; as empresas dos EUA (`CIK...`) só têm o setor
setores_cvm = sa.Table(
    "setores_cvm",
    metadata,
    sa.Column("cnpj", sa.String(18), primary_key=True),
    sa.Column("setor", sa.String(120), nullable=False),
    sa.Column("situacao", sa.String(40)),  # ATIVO, CANCELADA...
    sa.Column("situacao_desde", sa.Date),  # desde quando a situação vale
    sa.Column("categoria", sa.String(40)),  # Categoria A ou B
    sa.Column("registro", sa.Date),  # a data do registro na CVM
    sa.Column("atualizado_em", sa.DateTime(timezone=True)),  # quando a coleta gravou
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

# Compartilhamento seguro (0034, onda 4 da ADR 0046): links secretos, com prazo e revogáveis,
# para a ficha "Foi sorte?" congelada ou um PDF original da biblioteca. Só o hash do código fica
# aqui (src/compartilhamentos.py). Somem com a conta e, os de PDF, junto com o PDF guardado.
compartilhamentos = sa.Table(
    "compartilhamentos",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("codigo_hash", sa.String(64), nullable=False, unique=True),
    sa.Column("tipo", sa.String(10), nullable=False),
    sa.Column(
        "relatorio_id",
        sa.Uuid,
        sa.ForeignKey("pdfs_originais.relatorio_id", ondelete="CASCADE"),
    ),
    sa.Column("ficha", JSON_PORTATIL),
    sa.Column("titulo", sa.String(200), nullable=False),
    _momento("criado_em"),
    sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revogado_em", sa.DateTime(timezone=True)),
    sa.Column("visitas", sa.Integer, nullable=False, server_default="0"),
    sa.Column("ultima_visita_em", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "(tipo = 'ficha' AND ficha IS NOT NULL AND relatorio_id IS NULL) OR "
        "(tipo = 'pdf' AND relatorio_id IS NOT NULL AND ficha IS NULL)",
        name="tipo",
    ),
    sa.CheckConstraint("expira_em > criado_em", name="prazo"),
    sa.CheckConstraint("visitas >= 0", name="visitas"),
    sa.CheckConstraint("length(titulo) >= 1", name="titulo"),
)
sa.Index(
    "ix_compartilhamentos_usuario_id_criado_em",
    compartilhamentos.c.usuario_id,
    compartilhamentos.c.criado_em,
)
sa.Index("ix_compartilhamentos_relatorio_id", compartilhamentos.c.relatorio_id)

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
    # o commit que baixou (migração 0036; vazio nas linhas de antes da exigência 13 da ADR 0055)
    sa.Column("versao_do_codigo", sa.String(60)),
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


# --- Sala de dados por operação (B-20, migração 0040; plano `2026-10-20-b20-sala-de-dados`) ---
# Cada operação (M&A, dívida, crédito, FIDC) é uma sala com os documentos dela. Isolamento no banco:
# toda tabela tem `usuario_id` e se liga à operação pela chave composta (operacao_id, usuario_id),
# então o banco recusa uma linha de uma conta na sala de outra; evidência, contradição e item do
# checklist só apontam coisas da mesma sala (chaves compostas com operacao_id). Tudo sai com a conta.
TIPOS_DE_OPERACAO = ("ma", "divida", "credito", "fidc")
SITUACOES_DA_OPERACAO = ("aberta", "encerrada")
TIPOS_DE_DOCUMENTO = ("pdf", "xlsx", "docx", "csv")
SITUACOES_DO_DOCUMENTO = ("na_fila", "lido", "sem_texto", "erro_na_leitura")
QUEM_EXTRAIU = ("pessoa", "regra")
REVISOES_DA_EVIDENCIA = ("automatico", "revisado", "contestado", "rejeitado")
ESTADOS_DA_CONTRADICAO = ("aberta", "explicada", "descartada")
ESTADOS_DO_CHECKLIST = (
    "pendente",
    "recebido",
    "revisado",
    "contestado",
    "nao_se_aplica",
)
TAMANHO_MAXIMO_DO_NOME_DA_OPERACAO = 200
TAMANHO_MAXIMO_DO_NOME_DO_DOCUMENTO = 255
TAMANHO_MAXIMO_DA_NOTA = 2000


def _entre(coluna: str, valores: tuple[str, ...]) -> str:
    return f"{coluna} IN ({', '.join(repr(v) for v in valores)})"


def _da_operacao(tabela: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["operacao_id", "usuario_id"],
        ["operacoes.id", "operacoes.usuario_id"],
        name=f"fk_{tabela}_operacao_id_operacoes",
        ondelete="CASCADE",
    )


def _da_mesma_sala(
    tabela: str, coluna: str, alvo: str, ondelete: str | None = "CASCADE"
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [coluna, "operacao_id", "usuario_id"],
        [f"{alvo}.id", f"{alvo}.operacao_id", f"{alvo}.usuario_id"],
        name=f"fk_{tabela}_{coluna}_{alvo}",
        ondelete=ondelete,
    )


operacoes = sa.Table(
    "operacoes",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("tipo", sa.String(10), nullable=False),
    sa.Column("nome", sa.String(TAMANHO_MAXIMO_DO_NOME_DA_OPERACAO), nullable=False),
    sa.Column("situacao", sa.String(10), nullable=False, server_default="aberta"),
    sa.Column("retencao_ate", sa.Date, nullable=False),
    # chave da operação embrulhada pela chave-mestra (PR 2); vazia até lá, e nunca sai do banco
    sa.Column("chave_cifrada", sa.LargeBinary),
    sa.Column("versao_da_chave", sa.Integer),
    _momento("criada_em"),
    _momento("atualizada_em"),
    sa.UniqueConstraint("id", "usuario_id", name="uq_operacoes_id_usuario_id"),
    sa.CheckConstraint(_entre("tipo", TIPOS_DE_OPERACAO), name="tipo"),
    sa.CheckConstraint(_entre("situacao", SITUACOES_DA_OPERACAO), name="situacao"),
    sa.CheckConstraint(
        f"length(nome) BETWEEN 1 AND {TAMANHO_MAXIMO_DO_NOME_DA_OPERACAO}", name="nome"
    ),
    sa.CheckConstraint(
        "(chave_cifrada IS NULL) = (versao_da_chave IS NULL)", name="chave"
    ),
)
sa.Index(
    "ix_operacoes_usuario_id_criada_em", operacoes.c.usuario_id, operacoes.c.criada_em
)
sa.Index("ix_operacoes_retencao_ate", operacoes.c.retencao_ate)

documentos_da_sala = sa.Table(
    "documentos_da_sala",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("operacao_id", sa.Uuid, nullable=False),
    sa.Column(
        "nome_original", sa.String(TAMANHO_MAXIMO_DO_NOME_DO_DOCUMENTO), nullable=False
    ),
    sa.Column("tipo", sa.String(10), nullable=False),
    sa.Column("tamanho_bytes", sa.BigInteger, nullable=False),
    sa.Column("paginas", sa.Integer),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("nonce", sa.LargeBinary),  # da cifra do arquivo (PR 2)
    sa.Column("situacao", sa.String(20), nullable=False, server_default="na_fila"),
    sa.Column("lido_por", sa.String(40)),  # versão do leitor
    _momento("recebido_em"),
    _da_operacao("documentos_da_sala"),
    sa.UniqueConstraint(
        "id", "operacao_id", "usuario_id", name="uq_documentos_da_sala_id_operacao"
    ),
    # o mesmo arquivo só é recusado dentro da mesma sala
    sa.UniqueConstraint("operacao_id", "sha256", name="uq_documentos_da_sala_sha256"),
    sa.CheckConstraint(_entre("tipo", TIPOS_DE_DOCUMENTO), name="tipo"),
    sa.CheckConstraint(_entre("situacao", SITUACOES_DO_DOCUMENTO), name="situacao"),
    sa.CheckConstraint("tamanho_bytes > 0", name="tamanho"),
    sa.CheckConstraint("paginas IS NULL OR paginas >= 0", name="paginas"),
    sa.CheckConstraint("length(sha256) = 64", name="sha256"),
    sa.CheckConstraint(
        f"length(nome_original) BETWEEN 1 AND {TAMANHO_MAXIMO_DO_NOME_DO_DOCUMENTO}",
        name="nome",
    ),
)
sa.Index("ix_documentos_da_sala_usuario_id", documentos_da_sala.c.usuario_id)

evidencias_da_sala = sa.Table(
    "evidencias_da_sala",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("operacao_id", sa.Uuid, nullable=False),
    sa.Column("documento_id", sa.Uuid, nullable=False),
    sa.Column("metrica", sa.String(120), nullable=False),
    sa.Column("periodo", sa.String(20), nullable=False),
    sa.Column("valor_numero", sa.Numeric(28, 6)),
    sa.Column("valor_texto", sa.String(500)),
    sa.Column("unidade", sa.String(20)),
    sa.Column("moeda", sa.String(3)),
    sa.Column("pagina", sa.Integer),
    sa.Column("secao", sa.String(200)),
    sa.Column("tabela", sa.String(200)),
    sa.Column("trecho", sa.String(TAMANHO_MAXIMO_DA_NOTA)),
    sa.Column("conferida", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("extraido_por", sa.String(10), nullable=False),
    sa.Column(
        "estado_de_revisao", sa.String(12), nullable=False, server_default="automatico"
    ),
    _momento("criada_em"),
    _da_operacao("evidencias_da_sala"),
    _da_mesma_sala("evidencias_da_sala", "documento_id", "documentos_da_sala"),
    sa.UniqueConstraint(
        "id", "operacao_id", "usuario_id", name="uq_evidencias_da_sala_id_operacao"
    ),
    sa.CheckConstraint(_entre("extraido_por", QUEM_EXTRAIU), name="extraido_por"),
    sa.CheckConstraint(
        _entre("estado_de_revisao", REVISOES_DA_EVIDENCIA), name="estado_de_revisao"
    ),
    sa.CheckConstraint(
        "valor_numero IS NOT NULL OR valor_texto IS NOT NULL", name="valor"
    ),
    sa.CheckConstraint("pagina IS NULL OR pagina >= 1", name="pagina"),
)
sa.Index("ix_evidencias_da_sala_usuario_id", evidencias_da_sala.c.usuario_id)
sa.Index(
    "ix_evidencias_da_sala_documento_id",
    evidencias_da_sala.c.documento_id,
    evidencias_da_sala.c.operacao_id,
    evidencias_da_sala.c.usuario_id,
)

contradicoes_da_sala = sa.Table(
    "contradicoes_da_sala",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("operacao_id", sa.Uuid, nullable=False),
    sa.Column("evidencia_a", sa.Uuid, nullable=False),
    sa.Column("evidencia_b", sa.Uuid, nullable=False),
    sa.Column("diferenca", sa.Numeric(28, 6)),
    sa.Column("estado", sa.String(12), nullable=False, server_default="aberta"),
    sa.Column("nota", sa.String(TAMANHO_MAXIMO_DA_NOTA)),
    _momento("criada_em"),
    _da_operacao("contradicoes_da_sala"),
    _da_mesma_sala("contradicoes_da_sala", "evidencia_a", "evidencias_da_sala"),
    _da_mesma_sala("contradicoes_da_sala", "evidencia_b", "evidencias_da_sala"),
    sa.UniqueConstraint(
        "evidencia_a", "evidencia_b", name="uq_contradicoes_da_sala_evidencias"
    ),
    sa.CheckConstraint("evidencia_a <> evidencia_b", name="duas_evidencias"),
    sa.CheckConstraint(_entre("estado", ESTADOS_DA_CONTRADICAO), name="estado"),
)
sa.Index("ix_contradicoes_da_sala_usuario_id", contradicoes_da_sala.c.usuario_id)
sa.Index(
    "ix_contradicoes_da_sala_evidencia_b",
    contradicoes_da_sala.c.evidencia_b,
    contradicoes_da_sala.c.operacao_id,
    contradicoes_da_sala.c.usuario_id,
)

checklist_da_sala = sa.Table(
    "checklist_da_sala",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("operacao_id", sa.Uuid, nullable=False),
    sa.Column("codigo", sa.String(60), nullable=False),  # do modelo de checklist (PR 4)
    sa.Column("estado", sa.String(15), nullable=False, server_default="pendente"),
    sa.Column("documento_id", sa.Uuid),
    sa.Column("nota", sa.String(TAMANHO_MAXIMO_DA_NOTA)),
    _momento("atualizado_em"),
    _da_operacao("checklist_da_sala"),
    # sem cascata: apagar o documento solta o item antes (src/banco/sala.py); o banco só impede
    # que o item aponte um documento de outra sala
    _da_mesma_sala(
        "checklist_da_sala", "documento_id", "documentos_da_sala", ondelete=None
    ),
    sa.UniqueConstraint("operacao_id", "codigo", name="uq_checklist_da_sala_codigo"),
    sa.CheckConstraint(_entre("estado", ESTADOS_DO_CHECKLIST), name="estado"),
)
sa.Index("ix_checklist_da_sala_usuario_id", checklist_da_sala.c.usuario_id)
sa.Index(
    "ix_checklist_da_sala_documento_id",
    checklist_da_sala.c.documento_id,
    checklist_da_sala.c.operacao_id,
    checklist_da_sala.c.usuario_id,
)


# --- Originação: o funil das operações (B-33, migração 0041; plano `2026-10-21-b33-crm-de-originacao`) ---
# Um negócio por operação (a chave primária é a própria operação) e os contatos que a pessoa anotou.
# Mesmo isolamento da sala: chave composta com `usuario_id`, cascata com a operação e a conta.
# Nenhuma coluna de e-mail ou telefone, de propósito: o registro é um caderno, não envia nada.
FASES_DO_NEGOCIO = (
    "ideia",
    "qualificacao",
    "analise",
    "proposta",
    "negociacao",
    "fechado",
    "perdido",
)
TAMANHO_MAXIMO_DO_TEXTO_DO_NEGOCIO = 300
TAMANHO_MAXIMO_DO_CONTATO = 500

negocios_da_originacao = sa.Table(
    "negocios_da_originacao",
    metadata,
    sa.Column("operacao_id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("fase", sa.String(12), nullable=False, server_default="ideia"),
    sa.Column("origem", sa.String(TAMANHO_MAXIMO_DO_TEXTO_DO_NEGOCIO), nullable=False),
    sa.Column("alvo", sa.String(TAMANHO_MAXIMO_DO_TEXTO_DO_NEGOCIO)),
    sa.Column("proximo_passo", sa.String(TAMANHO_MAXIMO_DO_TEXTO_DO_NEGOCIO)),
    sa.Column("responsavel", sa.String(TAMANHO_MAXIMO_DO_TEXTO_DO_NEGOCIO)),
    sa.Column("fase_desde", sa.Date, nullable=False),
    _momento("criado_em"),
    _momento("atualizado_em"),
    _da_operacao("negocios_da_originacao"),
    sa.UniqueConstraint(
        "operacao_id", "usuario_id", name="uq_negocios_da_originacao_operacao"
    ),
    sa.CheckConstraint(_entre("fase", FASES_DO_NEGOCIO), name="fase"),
)
sa.Index("ix_negocios_da_originacao_usuario_id", negocios_da_originacao.c.usuario_id)

contatos_do_negocio = sa.Table(
    "contatos_do_negocio",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("operacao_id", sa.Uuid, nullable=False),
    sa.Column("descricao", sa.String(TAMANHO_MAXIMO_DO_CONTATO), nullable=False),
    sa.Column("ocorreu_em", sa.Date, nullable=False),
    _momento("registrado_em"),
    sa.ForeignKeyConstraint(
        ["operacao_id", "usuario_id"],
        [
            "negocios_da_originacao.operacao_id",
            "negocios_da_originacao.usuario_id",
        ],
        name="fk_contatos_do_negocio_negocio",
        ondelete="CASCADE",
    ),
    sa.CheckConstraint(
        f"length(descricao) BETWEEN 1 AND {TAMANHO_MAXIMO_DO_CONTATO}", name="descricao"
    ),
)
sa.Index(
    "ix_contatos_do_negocio_negocio",
    contatos_do_negocio.c.operacao_id,
    contatos_do_negocio.c.usuario_id,
)
sa.Index("ix_contatos_do_negocio_usuario_id", contatos_do_negocio.c.usuario_id)


# --- Garantias das operações (B-17, migração 0042; plano `2026-10-21-b17-garantias`) ---
# A exposição é a dívida a cobrir; cada garantia aponta para uma exposição da mesma operação. Mesmo
# isolamento da sala: chave composta com `usuario_id`, cascata com a operação e com a conta. Titular só
# por id opaco (`titular_ref`): nenhuma coluna de nome, CPF ou endereço. O laudo é um documento da
# mesma sala, com a página citada; apagar o documento solta o laudo (src/banco/sala.py), não a garantia.
TIPOS_DE_GARANTIA = (
    "imovel",
    "recebiveis",
    "veiculo",
    "acoes",
    "fianca",
    "aval",
    "cessao_fiduciaria",
    "outro",
)
LIQUIDEZES_DA_GARANTIA = ("alta", "media", "baixa")
TAMANHO_MAXIMO_DO_ROTULO_DA_EXPOSICAO = 120
TAMANHO_MAXIMO_DO_TITULAR_REF = 60

exposicoes_da_operacao = sa.Table(
    "exposicoes_da_operacao",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("operacao_id", sa.Uuid, nullable=False),
    sa.Column(
        "rotulo", sa.String(TAMANHO_MAXIMO_DO_ROTULO_DA_EXPOSICAO), nullable=False
    ),
    sa.Column("valor", sa.Numeric(28, 6), nullable=False),
    sa.Column("moeda", sa.String(3), nullable=False),
    sa.Column("vencimento", sa.Date),
    _momento("criada_em"),
    _momento("atualizada_em"),
    _da_operacao("exposicoes_da_operacao"),
    sa.UniqueConstraint(
        "id", "operacao_id", "usuario_id", name="uq_exposicoes_da_operacao_id"
    ),
    sa.CheckConstraint("valor > 0", name="valor"),
    sa.CheckConstraint(
        f"length(rotulo) BETWEEN 1 AND {TAMANHO_MAXIMO_DO_ROTULO_DA_EXPOSICAO}",
        name="rotulo",
    ),
)
sa.Index("ix_exposicoes_da_operacao_usuario_id", exposicoes_da_operacao.c.usuario_id)
sa.Index(
    "ix_exposicoes_da_operacao_operacao",
    exposicoes_da_operacao.c.operacao_id,
    exposicoes_da_operacao.c.usuario_id,
)

garantias_da_operacao = sa.Table(
    "garantias_da_operacao",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("operacao_id", sa.Uuid, nullable=False),
    sa.Column("exposicao_id", sa.Uuid, nullable=False),
    sa.Column("tipo", sa.String(20), nullable=False),
    sa.Column("valor_avaliado", sa.Numeric(28, 6), nullable=False),
    sa.Column("moeda", sa.String(3), nullable=False),
    sa.Column("avaliado_em", sa.Date, nullable=False),
    sa.Column("haircut", sa.Numeric(7, 6), nullable=False),
    sa.Column("liquidez", sa.String(5), nullable=False),
    sa.Column("prioridade", sa.Integer, nullable=False, server_default="1"),
    sa.Column("onus_anteriores", sa.Numeric(28, 6), nullable=False, server_default="0"),
    sa.Column("valido_ate", sa.Date),
    sa.Column("titular_ref", sa.String(TAMANHO_MAXIMO_DO_TITULAR_REF)),
    sa.Column("laudo_id", sa.Uuid),
    sa.Column("laudo_pagina", sa.Integer),
    _momento("criada_em"),
    _momento("atualizada_em"),
    _da_operacao("garantias_da_operacao"),
    _da_mesma_sala("garantias_da_operacao", "exposicao_id", "exposicoes_da_operacao"),
    # sem cascata: apagar o documento solta o laudo antes (src/banco/sala.py)
    _da_mesma_sala(
        "garantias_da_operacao", "laudo_id", "documentos_da_sala", ondelete=None
    ),
    sa.CheckConstraint(_entre("tipo", TIPOS_DE_GARANTIA), name="tipo"),
    sa.CheckConstraint(_entre("liquidez", LIQUIDEZES_DA_GARANTIA), name="liquidez"),
    sa.CheckConstraint("haircut >= 0 AND haircut <= 1", name="haircut"),
    sa.CheckConstraint("valor_avaliado >= 0", name="valor_avaliado"),
    sa.CheckConstraint("onus_anteriores >= 0", name="onus_anteriores"),
    sa.CheckConstraint("prioridade >= 1", name="prioridade"),
    sa.CheckConstraint(
        "(laudo_id IS NULL) = (laudo_pagina IS NULL) "
        "AND (laudo_pagina IS NULL OR laudo_pagina >= 1)",
        name="laudo",
    ),
)
sa.Index("ix_garantias_da_operacao_usuario_id", garantias_da_operacao.c.usuario_id)
sa.Index(
    "ix_garantias_da_operacao_exposicao",
    garantias_da_operacao.c.exposicao_id,
    garantias_da_operacao.c.operacao_id,
    garantias_da_operacao.c.usuario_id,
)
sa.Index(
    "ix_garantias_da_operacao_laudo",
    garantias_da_operacao.c.laudo_id,
    garantias_da_operacao.c.operacao_id,
    garantias_da_operacao.c.usuario_id,
)


# API externa (N7, ADR 0108): quem entra. A organização é o cliente PJ, sem dado de pessoa (o contato
# fica no CRM); a chave guarda só o prefixo (não é segredo) e o SHA-256 da chave inteira. Nada aqui
# se apaga para suspender: suspender é preencher `suspensa_em` / `suspenso_em`.
PLANOS_DA_API = ("piloto",)
# `treino` é o modelo próprio do TickerLab: nunca vai para uma organização (plano N7, D6)
FINALIDADES_DA_ORGANIZACAO = ("analise", "credito")
CANAL_DA_CHAVE = "api_externa"  # a chave nunca abre `api_interna` (ADR 0108, linha 117)
MOTIVOS_DA_SUSPENSAO = ("contrato", "pagamento", "abuso", "pedido_do_cliente", "fonte")
TAMANHO_MAXIMO_DO_NOME_DA_ORGANIZACAO = 120
TAMANHO_MAXIMO_DO_CONJUNTO = 80


def _quem_fez(nome: str) -> sa.Column:
    # o admin que fez; a linha fica quando a conta dele é apagada
    return sa.Column(nome, sa.Uuid, sa.ForeignKey("usuarios.id", ondelete="SET NULL"))


organizacoes = sa.Table(
    "organizacoes",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("nome", sa.String(TAMANHO_MAXIMO_DO_NOME_DA_ORGANIZACAO), nullable=False),
    sa.Column("cnpj", sa.String(14), unique=True),
    sa.Column("plano_da_api", sa.String(20), nullable=False, server_default="piloto"),
    sa.Column("suspensa_em", sa.DateTime(timezone=True)),
    sa.Column("motivo_da_suspensao", sa.String(30)),
    _momento("criada_em"),
    _quem_fez("criada_por"),
    sa.CheckConstraint(_entre("plano_da_api", PLANOS_DA_API), name="plano_da_api"),
    sa.CheckConstraint(
        "motivo_da_suspensao IS NULL OR "
        + _entre("motivo_da_suspensao", MOTIVOS_DA_SUSPENSAO),
        name="motivo_da_suspensao",
    ),
    sa.CheckConstraint(
        "(suspensa_em IS NULL) = (motivo_da_suspensao IS NULL)", name="suspensao"
    ),
)

chaves_da_api = sa.Table(
    "chaves_da_api",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "organizacao_id",
        sa.Uuid,
        sa.ForeignKey("organizacoes.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("prefixo", sa.String(8), nullable=False, unique=True),
    sa.Column("hash_da_chave", sa.String(64), nullable=False, unique=True),
    _momento("criada_em"),
    _quem_fez("criada_por"),
    # preenchido na rotação: a chave antiga vale até aqui
    sa.Column("expira_em", sa.DateTime(timezone=True)),
    sa.Column("revogada_em", sa.DateTime(timezone=True)),
    sa.Column("ultimo_uso", sa.DateTime(timezone=True)),
    # para o consumo apontar para (chave, organização) e o banco recusar a chave de outra
    sa.UniqueConstraint("id", "organizacao_id", name="uq_chaves_da_api_organizacao"),
)
sa.Index("ix_chaves_da_api_organizacao_id", chaves_da_api.c.organizacao_id)

direitos_da_organizacao = sa.Table(
    "direitos_da_organizacao",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "organizacao_id",
        sa.Uuid,
        sa.ForeignKey("organizacoes.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("conjunto", sa.String(TAMANHO_MAXIMO_DO_CONJUNTO), nullable=False),
    sa.Column("finalidade", sa.String(12), nullable=False),
    sa.Column("vigente_desde", sa.Date, nullable=False),
    sa.Column("vigente_ate", sa.Date),
    sa.Column("suspenso_em", sa.DateTime(timezone=True)),
    _momento("criado_em"),
    _quem_fez("criado_por"),
    sa.UniqueConstraint(
        "organizacao_id",
        "conjunto",
        "finalidade",
        name="uq_direitos_da_organizacao_conjunto",
    ),
    sa.CheckConstraint(
        _entre("finalidade", FINALIDADES_DA_ORGANIZACAO), name="finalidade"
    ),
    sa.CheckConstraint(
        "vigente_ate IS NULL OR vigente_ate >= vigente_desde", name="vigencia"
    ),
)

# Medição agregada por dia (D10): sem IP, sem o que foi buscado, sem resposta
consumo_da_api = sa.Table(
    "consumo_da_api",
    metadata,
    sa.Column("organizacao_id", sa.Uuid, nullable=False),
    sa.Column("chave_id", sa.Uuid, nullable=False),
    sa.Column("dia", sa.Date, nullable=False),
    sa.Column("canal", sa.String(12), nullable=False),
    sa.Column("finalidade", sa.String(12), nullable=False),
    sa.Column("conjunto", sa.String(TAMANHO_MAXIMO_DO_CONJUNTO), nullable=False),
    sa.Column("pedidos", sa.Integer, nullable=False, server_default="0"),
    sa.Column("linhas", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("negados", sa.Integer, nullable=False, server_default="0"),
    sa.PrimaryKeyConstraint(
        "organizacao_id", "chave_id", "dia", "canal", "finalidade", "conjunto"
    ),
    sa.ForeignKeyConstraint(
        ["chave_id", "organizacao_id"],
        ["chaves_da_api.id", "chaves_da_api.organizacao_id"],
        name="fk_consumo_da_api_chave",
        ondelete="CASCADE",
    ),
    sa.CheckConstraint(f"canal = '{CANAL_DA_CHAVE}'", name="canal"),
    sa.CheckConstraint(
        _entre("finalidade", FINALIDADES_DA_ORGANIZACAO), name="finalidade"
    ),
)
