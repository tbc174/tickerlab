"""Registro de coletas: uma linha por arquivo baixado das fontes oficiais (Radar, PR 1).

É o primeiro passo da base histórica (ADR 0024 do autor): saber de onde veio cada arquivo, quando,
o tamanho, o SHA-256 e sob qual licença. As coletas não mudam o que gravam; só passam a deixar
este registro. Um problema no registro nunca derruba a coleta (fica no log).
"""

import hashlib
import logging
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import NamedTuple

import requests
import sqlalchemy as sa

from src import acervo, rede
from src.banco.conexao import obter_engine
from src.banco.modelo import coletas
from src.versao_do_codigo import versao_do_codigo

log = logging.getLogger(__name__)

# a licença de cada família de fontes (licencas-por-fonte.md do autor); a fonte é "família-detalhe"
LICENCAS = {
    "cvm": "ODbL (dados abertos da CVM; citar a fonte)",
    "sec": "Acesso público (EDGAR, SEC)",
    "bcb": "ODbL (dados abertos do Banco Central; citar a fonte)",
    "ibge": "Domínio público (citar o IBGE)",
    # clima e geografia do café (lidos em 18/10/2026): o INMET não publica licença escrita
    "inmet": "Dados históricos do INMET: públicos e gratuitos, sem licença escrita (citar)",
    "chirps": "CHIRPS v2.0 (UCSB): domínio público; citar Funk et al. 2015",
    "chirps3": "CHIRPS v3.0 rnl (CHC): CC BY 4.0, domínio público; DOI 10.15780/G2JQ0P",
    "mapbiomas": "MapBiomas Coleção 11: CC BY-SA (citar Souza et al. 2020)",
    # preços mensais de referência (lidos em 18/10/2026): Pink Sheet sob CC BY 4.0 por padrão, mas
    # com fontes de terceiros; FMI com todos os direitos reservados e uso comercial sob permissão
    "bm": "CC BY 4.0 (Pink Sheet); preços de terceiros só com o consentimento deles",
    "fmi": "© FMI: uso comercial pede permissão por escrito; coleta citando o FMI (ADR 0102)",
    "tesouro": "Sem restrição (Fiscal Data, Tesouro dos EUA)",
    "iex": "Termos do IEX HIST (com atribuição)",
    "yahoo": "Uso pessoal: só interno, nunca exportar",
    # base de cripto (ADRs 0041 e 0045 do autor)
    "cftc": "Obra do governo dos EUA (17 U.S.C. §105; citar a CFTC)",
    "rfb": "Dados abertos da Receita Federal (Decreto 8.777/2016; citar a Receita)",
    "wiki": "CC0 (acessos às páginas da Wikimedia)",
    "gdelt": "GDELT Project (citar e linkar gdeltproject.org); só contagem e tom",
    "btc": "Blockchain pública lida por nó próprio (Bitcoin Core, MIT)",
    "kraken": "Termo da Kraken (19/10/2026): só uso próprio; veda cópia, comércio e robôs",
    "mb": "Sem termo de dados de mercado: uso sem autorização (ADR 0045); só interno",
    # arquivo das fontes que só mostram o "agora" (plano dos coletores em modo arquivo, 14/10/2026)
    "rfb-cnpj": "CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)",
    "cgu": "Dados abertos da CGU (Decreto 8.777/2016; citar a CGU)",
    # lote Brasil, segunda camada (22/10/2026): só CNPJ e agregados, sem pessoa física (ADR 0088)
    "transparencia": "Portal da Transparência da CGU (Decreto 8.777/2016, CC BY; citar a CGU). Só CNPJ",
    "bndes": "ODbL (dados abertos do BNDES; citar o BNDES, compartilhar igual). Só CNPJ",
    "inss": "Dados abertos do INSS (Decreto 8.777/2016; citar o INSS). Só agregados",
    "pgfn": "Dados abertos da PGFN (rodapé CC BY-ND do site: perguntar a licença)",
    "ibama": "Dados abertos do IBAMA ('Outra (Aberta)'; citar o IBAMA)",
    "mte": "Cadastro de empregadores do MTE (dado público; citar o MTE)",
    "gleif": "CC0 (GLEIF, Global LEI Index)",
    "termos": "Termos de uso de terceiros: só prova interna da versão lida",
    "catalogo": "Lista de conjuntos de portais de dados abertos (metadados)",
    # o SGS do BC repassa o IGP-M, mas a série é da FGV (termos do IBRE: comercial pede autorização)
    "bcb-sgs-189": "IGP-M da FGV IBRE (repassado pelo BC): uso comercial pede autorização da FGV",
    "ccee": "CC BY 4.0 (dados abertos da CCEE; citar a CCEE)",
    # licitações e contratos (lidos em 22/10/2026): só pessoa jurídica no acervo (LGPD, ADR 0088)
    "seges": "Dados abertos da SEGES (Decreto 8.777/2016; citar a SEGES)",
    "seges-pesquisa-precos": "Painel de Preços da SEGES (dados abertos; citar a SEGES; revenda a confirmar)",
    "comprasgov": "Dados abertos do compras.gov.br (Decreto 8.777/2016; citar a SEGES)",
    "transferegov": "Dados abertos do Transferegov (Decreto 8.777/2016; citar o MGI)",
    "pncp": "PNCP: licença não escrita (a confirmar; citar o PNCP)",
    "tcu": "Lista de inidôneos do TCU: sem licença escrita (a confirmar; citar o TCU)",
    "govmg": "CC BY 4.0 (dados abertos de Minas Gerais; citar o Governo de MG)",
    "govsc": "CC BY (dados abertos de Santa Catarina; citar o Governo de SC)",
    "antt": "CC BY (dados abertos da ANTT; citar a ANTT)",
    "tesouro-br": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-divida": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-direto": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-leiloes": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    # SICONFI (rodada 1 da pesquisa de dados escondidos, lido em 22/10/2026): só estados e capitais,
    # contas públicas sem pessoa física; o id leva "tesouro-br" para não cair na licença dos EUA
    "tesouro-br-siconfi-entes": "ODbL (SICONFI, Tesouro Nacional; citar a fonte)",
    "tesouro-br-siconfi-entregas": "ODbL (SICONFI, Tesouro Nacional; citar a fonte)",
    "tesouro-br-siconfi-rreo": "ODbL (SICONFI, Tesouro Nacional; citar a fonte)",
    "tesouro-br-siconfi-rgf": "ODbL (SICONFI, Tesouro Nacional; citar a fonte)",
    "tesouro-br-siconfi-dca": "ODbL (SICONFI, Tesouro Nacional; citar a fonte)",
    # lote Tesouro (23/10/2026): o id leva "tesouro-br" pelo mesmo motivo
    "tesouro-br-rtn": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-receitas": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-despesas": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-restos-a-pagar": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-fatores-divida": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-paf": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-bspn": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-limites-lrf": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-dividendos-estatais": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-subsidios-bndes": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-garantias": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-transferencias": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-capag-municipios": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-td-vendas": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-td-resgates": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    "tesouro-br-td-estoque": "ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)",
    # prévia do balanço (14/10/2026): licença declarada no conjunto no dados.gov.br (o rodapé CC
    # BY-ND dos sites é do conteúdo das páginas); confirmação por escrito pedida às agências
    "anp": "CC BY (dados abertos da ANP no dados.gov.br; citar a ANP)",
    "anac": "CC BY (dados abertos da ANAC no dados.gov.br; citar a ANAC)",
    "ans": "CC BY (dados abertos da ANS no dados.gov.br; citar a ANS)",
    "ons": "CC BY 4.0 (dados abertos do ONS; citar o ONS)",
    "anatel": "CC BY (dados abertos da Anatel no dados.gov.br; citar a Anatel)",
    "aneel": "ODbL (dados abertos da ANEEL; citar). SAMP sem CPF e nome do consumidor",
    # série 4, PR 5b: "SES - Base de dados completa" com CC BY no dados.gov.br (lido em 15/10/2026);
    # só os CSVs sem pessoas (nunca administradores, contatos ou acionistas)
    "susep": "CC BY (SES da SUSEP no dados.gov.br; citar a SUSEP). Só os CSVs sem pessoas",
    # licença aberta sem nome no dados.gov.br; confirmação pedida pelo Fala.BR em 14/10/2026
    "comexstat": "Aberta sem nome ('Other (Open)', dados.gov.br); a confirmar com o MDIC",
    # relatório mensal do Cecafé: robots.txt proíbe PDF e a página de termos veio vazia (18/10/2026)
    "cecafe": "Cecafé: robots.txt veda PDF; coleta com ritmo, uso citando a fonte (ADR 0102)",
    # termos lidos em 18/10/2026: uso pessoal e não comercial, vedam robô; coleta pela ADR 0102
    "fnc": "FNC: só uso pessoal, veda robô; coleta com ritmo, cita a fonte (ADR 0102)",
    # COTAHIST, arquivos públicos e carteiras dos índices: no produto com a fonte citada desde
    # 22/10/2026 (ADR 0008, Emenda 6; risco assumido pelo Tiago); a marca segue "não comercial"
    "b3": "Sem licença da B3; uso com a fonte citada, risco assumido (ADR 0008, Emenda 6)",
    # middle market de M&A: robots.txt e termos lidos antes; parecer jurídico depois (ADR 0060)
    "assessoria": "Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)",
    # termos lidos em 16/10/2026 (archive.org/about/terms); só a data das cópias entra na base
    "wayback": "Internet Archive: 'for scholarship and research purposes only'; só datas",
    # regras de utilização dos dados abertos do TCE-PR (lidas em 16/10/2026): "livre para qualquer
    # finalidade ou atividade, no limite das restrições legais"; sem pessoas (ADR 0075)
    "tce-pr": "Livre para qualquer finalidade (regras do TCE-PR; citar). Sem nomes nem CPF",
    "tce-pr-pit": "Livre para qualquer finalidade (regras do TCE-PR; citar). Sem nomes nem CPF",
    "tce-pr-despesa": "Livre para qualquer finalidade (regras do TCE-PR; citar). Sem nomes nem CPF",
    "tce-rs-empenhos": "CC BY (empenhos do TCE-RS; citar o TCE-RS)",
    "tce-rs": "LicitaCon do TCE-RS: licença a confirmar com a Ouvidoria (ADR 0085)",
    # site da CONAB lido em 18/10/2026 (rodapé: Creative Commons Atribuição-SemDerivações 3.0): mostrar
    # "como publicado" com citação é permitido; recorte, soma ou gráfico derivado pode ser obra derivada
    "conab": "CC BY-ND 3.0 (CONAB): uso citando a CONAB e a data do levantamento (ADR 0102)",
    # balanço mundial do café (termos lidos em 18/10/2026, licencas-por-fonte.md)
    "usda": "Domínio público do USDA (citar o USDA FAS, PSD Online); no data.gov consta CC BY",
    "faostat": "CC BY 4.0 (FAO; crédito no formato da FAO e sem sugerir aval da FAO)",
    "ico": "ICO: relatório mensal sem termos achados; uso citando a fonte (ADR 0102)",
    # páginas dos fatos da ficha das contrapartes do café (termos lidos em 18-19/10/2026)
    "contrapartes": "Página guardada só como prova; na ficha, fato e link (ADR 0102)",
    # lote organismos (termos lidos em 22/10/2026, licencas-por-fonte.md, rodadas 1 e 4)
    "bce": "Reuso livre citando 'Source: ECB statistics' (aviso do Data Portal do BCE)",
    "ocde": "Termos da OCDE: uso livre, inclusive comercial, citando a OCDE e a data",
    "eurostat": "CC BY 4.0 (Eurostat); coleta só dos países da UE",
    "worldbank": "CC BY 4.0 por padrão (Banco Mundial, WDI); conferir a licença de cada conjunto",
    "bis": "Termos do BIS: uso e redistribuição só não comerciais, citando o BIS",
    "nasa": "CC BY 4.0 (NASA POWER; citar NASA POWER)",
    "noaa": "Obra do governo dos EUA (domínio público); citar a NOAA CPC",
    # lote clima e fogo (termos lidos em 23/10/2026, licencas-por-fonte.md, rodada 4)
    "inpe": "INPE Queimadas: sem licença escrita; uso citando o INPE (ADR 0102)",
    "firms": "Dados abertos da NASA (FIRMS); citar NASA FIRMS, chave só no ambiente",
    "terrabrasilis": "CC BY-SA 4.0 (INPE, TerraBrasilis); citar e compartilhar igual",
    "ecmwf": "CC BY 4.0 (ECMWF open data); citar o ECMWF",
    "climatetrace": "CC BY 4.0 (Climate TRACE); citar o Climate TRACE",
    "edgar": "CC BY 4.0 (EDGAR, JRC); sem o IEA-EDGAR CO2, que é CC BY-NC-ND",
    "carbonmonitor": "CC BY 4.0 (Carbon Monitor); citar o Carbon Monitor",
    # lote EUA (termos lidos em 22/10/2026): obra do governo federal dos EUA é domínio público; citar
    # a agência. O Fed e o NY Fed avisam que há séries de terceiros dentro de alguns conjuntos
    "treasury": "Domínio público (Fiscal Data e curvas, Tesouro dos EUA; citar o Tesouro)",
    "fed": "Domínio público (Federal Reserve Board, Data Download Program; citar o Fed)",
    "bls": "Domínio público (Bureau of Labor Statistics; citar a BLS)",
    "eia": "Domínio público (Energy Information Administration; citar a EIA)",
    "ofr": "Domínio público (Office of Financial Research, Tesouro dos EUA; citar a OFR)",
    "nyfed": "Federal Reserve Bank of New York: dados públicos de mercado (citar o NY Fed)",
    "tic": "Domínio público (Treasury International Capital, Tesouro dos EUA; citar)",
    "census": "Domínio público (U.S. Census Bureau; citar o Census Bureau)",
    # lote cadastros globais (termos lidos em 22/10/2026, licencas-por-fonte.md, rodada 4): só pessoa
    # jurídica; o `gleif` e o `sec` já existiam (a lista de tickers da SEC é obra da agência)
    "sec-company-tickers": "Domínio público (lista de tickers da SEC; citar a SEC)",
    "wikidata": "CC0 (Wikidata; citar Wikidata)",
    "ofac": "Obra do governo dos EUA (domínio público); citar a OFAC, só entidades",
    "eufsf": "Reuso da Comissão Europeia (Decisão 2011/833/UE); citar a UE, só empresas",
    "ofsi": "OGL v3 (OFSI, Reino Unido; citar a fonte), só entidades",
    # lote setoriais Brasil (termos lidos em 22/10/2026, licencas-por-fonte.md): EPE é CC BY 4.0;
    # INEP, Senatran e INPI só têm o rodapé CC BY-ND 3.0 do site gov.br, que vale para o conteúdo do
    # site e não para o conjunto: mostrar "como publicado" com a fonte citada (precedente da CONAB)
    "epe": "CC BY 4.0 (dados abertos da EPE; citar a EPE)",
    # lote atenção e texto (termos lidos em 22/10/2026, licencas-por-fonte.md, rodada 4): o `wiki` e o
    # `gdelt` já existiam (cripto); as fontes novas têm id próprio e a marca da rodada 4
    "wiki-pageviews-empresas": "CC0 (acessos por artigo, Wikimedia; citar a Wikimedia)",
    "gdelt-gkg": "GDELT: uso livre citando e linkando o GDELT; só empresa, tema e tom",
    "querido": "CC BY 4.0 (Querido Diário, Open Knowledge Brasil; citar)",
    "crossref": "Metadados sem direitos de autor (Crossref); só contagens por afiliação",
    "openalex": "CC0 (OpenAlex); só afiliações e contagens, sem autores",
    "ebc": "Texto de terceiros (EBC): só índice (data, título, link) do RSS",
    "senado": "Texto de terceiros (Agência Senado): só índice (data, título, link) do RSS",
    "camara": "Texto de terceiros (Agência Câmara): só índice (data, título, link)",
    "inep": "CC BY-ND 3.0 (rodapé do site do INEP); usar como publicado, citando o INEP",
    "senatran": "CC BY-ND 3.0 (rodapé do site da Senatran); como publicado, citando a Senatran",
    "inpi": "Sem licença do conjunto (rodapé CC BY-ND 3.0); como publicado, citando o INPI",
    "epo": "CC BY 4.0 (EPO Linked open EP data); citar o EPO; um pedido por vez",
    "wipo": "WIPO Statistics Database: não republicar nem revender; só uso interno, citando",
    "ipea": "IPEADATA sem termos publicados; série de terceiros herda a fonte; citar o Ipea",
    # as demonstrações contábeis da ANS não declaram licença (os conjuntos de beneficiários dizem CC BY)
    "ans-demonstracoes": "Demonstrações da ANS: sem licença declarada; citar a ANS (ADR 0102)",
}
SEM_LICENCA_CONHECIDA = "Desconhecida: conferir antes de guardar"

# A resposta sobre revenda de cada fonte (ADR 0055, exigência 11; ADR 0008, Emenda 1: as quatro
# marcas, com a resposta por escrito no `licencas-por-fonte.md`). Desde a ADR 0102 (18/10/2026) a
# marca é **informação**, gravada por fonte no contrato, no catálogo e na página Dados: ela não barra
# coleta, modelo, tela nem exportação (`pode_usar`); a B3 entrou em 22/10/2026 (ADR 0008, Emenda 6) e
# `FONTES_FORA_DOS_USOS` ficou vazia. Não é
# parecer jurídico: antes de vender qualquer coisa, parecer e decisão nova.
VENDAVEL_ODBL = (
    "vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor "
    "está na curadoria, nas versões e na qualidade)"
)
VENDAVEL_COM_ATRIBUICAO = "vendável com atribuição à fonte"
SO_USO_INTERNO = "só uso interno (entra em modelo; nunca vender nem exportar o dado)"
A_CONFIRMAR = (
    "a confirmar (sem resposta escrita sobre uso comercial ou treino de ML: vale como não "
    "comercial até a resposta)"
)
NAO_COMERCIAL = (
    "não comercial (uso pessoal, só pesquisa ou conta de estudante: só gabarito e pesquisa no PC; "
    "nunca em modelo, rótulo ou exportação)"
)
REVENDA = {
    "cvm": VENDAVEL_ODBL,
    "bcb": VENDAVEL_ODBL,
    "ibge": VENDAVEL_COM_ATRIBUICAO,
    "inmet": VENDAVEL_COM_ATRIBUICAO,  # sem licença escrita: confirmar por escrito antes de vender
    "chirps": VENDAVEL_COM_ATRIBUICAO,  # domínio público
    # v3 pela cópia do Hugging Face: a licença do dado é a do CHC (domínio público + CC BY 4.0, lida em
    # 28/10/2026); o termo de uso do Hugging Face não foi lido (notas de pesquisa, parte 4)
    "chirps3": VENDAVEL_COM_ATRIBUICAO,
    "mapbiomas": A_CONFIRMAR,  # CC BY-SA (termos do site, 21/10/2026): revenda a confirmar até a P-52
    "bm": SO_USO_INTERNO,  # CC BY 4.0, mas o Pink Sheet repassa preços de terceiros
    "fmi": SO_USO_INTERNO,  # uso comercial pede permissão por escrito do FMI; preços de referência não se distribuem (ADR 0008)
    "tesouro": VENDAVEL_COM_ATRIBUICAO,
    # treino de ML permitido por escrito (licencas-por-fonte.md, 13/10/2026); revenda ainda sem resposta
    "sec": SO_USO_INTERNO,  # os arquivos são escritos pelas empresas
    "iex": SO_USO_INTERNO,  # com a atribuição "Data provided for free by IEX"
    "cftc": VENDAVEL_COM_ATRIBUICAO,  # obra do governo dos EUA (17 U.S.C. §105), Emenda 5
    "wiki": SO_USO_INTERNO,  # CC0
    "btc": SO_USO_INTERNO,  # blockchain pública lida por nó próprio
    "rfb": A_CONFIRMAR,  # planilha de cripto da Receita: perguntar a licença
    "gdelt": VENDAVEL_COM_ATRIBUICAO,  # uso livre citando e linkando o GDELT, Emenda 5
    "yahoo": NAO_COMERCIAL,  # termos do Yahoo: uso pessoal
    # sem termo de dados: não comercial (a exceção da ADR 0045 ao clima de risco do Bitcoin perdeu
    # o sentido com a ADR 0102: a marca não barra mais)
    "kraken": NAO_COMERCIAL,  # termo de 19/10/2026: só uso próprio; a coleta segue (Emenda 5)
    "mb": NAO_COMERCIAL,
    # a ficha do conjunto no dados.gov.br declara CC BY (o CC BY-ND é do rodapé do site gov.br
    # inteiro); Tiago, "Pode", 20/10/2026 (ADR 0106, item 2). Sócio pessoa física segue fora do app.
    "rfb-cnpj": VENDAVEL_COM_ATRIBUICAO,
    "pgfn": A_CONFIRMAR,
    # dado pessoal (autuados, empregadores pessoa física): só interno
    "cgu": SO_USO_INTERNO,
    "transparencia": VENDAVEL_COM_ATRIBUICAO,
    "bndes": VENDAVEL_ODBL,
    "inss": VENDAVEL_COM_ATRIBUICAO,
    "ibama": SO_USO_INTERNO,
    "mte": SO_USO_INTERNO,
    "gleif": VENDAVEL_COM_ATRIBUICAO,
    "termos": SO_USO_INTERNO,
    "catalogo": SO_USO_INTERNO,
    "bcb-sgs-189": NAO_COMERCIAL,  # IGP-M da FGV: uso comercial pede autorização da FGV
    "ccee": VENDAVEL_COM_ATRIBUICAO,
    "seges": VENDAVEL_COM_ATRIBUICAO,
    "seges-pesquisa-precos": A_CONFIRMAR,  # preço de referência (ADR 0008)
    "comprasgov": VENDAVEL_COM_ATRIBUICAO,
    "transferegov": VENDAVEL_COM_ATRIBUICAO,
    "pncp": A_CONFIRMAR,
    "tcu": A_CONFIRMAR,
    "govmg": VENDAVEL_COM_ATRIBUICAO,
    "govsc": VENDAVEL_COM_ATRIBUICAO,
    "antt": VENDAVEL_COM_ATRIBUICAO,
    "tesouro-br": VENDAVEL_ODBL,
    "tesouro-br-divida": VENDAVEL_ODBL,
    "tesouro-br-direto": VENDAVEL_ODBL,
    "tesouro-br-leiloes": VENDAVEL_ODBL,
    "tesouro-br-siconfi-entes": VENDAVEL_ODBL,
    "tesouro-br-siconfi-entregas": VENDAVEL_ODBL,
    "tesouro-br-siconfi-rreo": VENDAVEL_ODBL,
    "tesouro-br-siconfi-rgf": VENDAVEL_ODBL,
    "tesouro-br-siconfi-dca": VENDAVEL_ODBL,
    "tesouro-br-rtn": VENDAVEL_ODBL,
    "tesouro-br-receitas": VENDAVEL_ODBL,
    "tesouro-br-despesas": VENDAVEL_ODBL,
    "tesouro-br-restos-a-pagar": VENDAVEL_ODBL,
    "tesouro-br-fatores-divida": VENDAVEL_ODBL,
    "tesouro-br-paf": VENDAVEL_ODBL,
    "tesouro-br-bspn": VENDAVEL_ODBL,
    "tesouro-br-limites-lrf": VENDAVEL_ODBL,
    "tesouro-br-dividendos-estatais": VENDAVEL_ODBL,
    "tesouro-br-subsidios-bndes": VENDAVEL_ODBL,
    "tesouro-br-garantias": VENDAVEL_ODBL,
    "tesouro-br-transferencias": VENDAVEL_ODBL,
    "tesouro-br-capag-municipios": VENDAVEL_ODBL,
    "tesouro-br-td-vendas": VENDAVEL_ODBL,
    "tesouro-br-td-resgates": VENDAVEL_ODBL,
    "tesouro-br-td-estoque": VENDAVEL_ODBL,
    "anp": VENDAVEL_COM_ATRIBUICAO,
    "anac": VENDAVEL_COM_ATRIBUICAO,
    "ans": VENDAVEL_COM_ATRIBUICAO,
    "ons": VENDAVEL_COM_ATRIBUICAO,
    "anatel": VENDAVEL_COM_ATRIBUICAO,
    "aneel": VENDAVEL_ODBL,
    "susep": VENDAVEL_COM_ATRIBUICAO,
    "comexstat": A_CONFIRMAR,
    "cecafe": NAO_COMERCIAL,  # o robots.txt veda PDF; coleta com ritmo e uso com a fonte citada (ADR 0102)
    "fnc": NAO_COMERCIAL,  # termos só para uso pessoal; coleta com ritmo e uso com a fonte citada (ADR 0102)
    "b3": NAO_COMERCIAL,  # informação, não trava: sem licença, uso com a fonte citada (ADR 0008, Emenda 6)
    "assessoria": A_CONFIRMAR,  # vender, mostrar ou treinar só com o parecer (ADRs 0063 e 0082)
    "wayback": NAO_COMERCIAL,  # "for scholarship and research purposes only"
    # a família vem do endereço ("tce-pr") e a fonte do arquivista tem o próprio id ("tce-pr-pit"):
    # o "tce" sozinho não diz qual tribunal
    "tce-pr": VENDAVEL_COM_ATRIBUICAO,
    "tce-pr-pit": VENDAVEL_COM_ATRIBUICAO,
    "tce-pr-despesa": VENDAVEL_COM_ATRIBUICAO,
    "tce-rs-empenhos": VENDAVEL_COM_ATRIBUICAO,  # CC BY
    "tce-rs": A_CONFIRMAR,  # LicitaCon: esperando a Ouvidoria
    "conab": A_CONFIRMAR,  # CC BY-ND 3.0; sem pedido à CONAB (ADR 0102): uso citando a CONAB e a data
    "usda": VENDAVEL_COM_ATRIBUICAO,  # domínio público ou CC BY: as duas permitem
    "faostat": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0
    "ico": NAO_COMERCIAL,  # PDF sem termos lidos; coleta e uso com a fonte citada (ADR 0102)
    "contrapartes": A_CONFIRMAR,  # cópia é prova interna; na ficha, fato nas nossas palavras e link (ADR 0102)
    "bce": VENDAVEL_COM_ATRIBUICAO,  # "Source: ECB statistics"
    "ocde": VENDAVEL_COM_ATRIBUICAO,  # uso comercial livre com a citação da OCDE
    "eurostat": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0; a coleta já filtra só os países da UE
    "worldbank": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0 (WDI); outros conjuntos podem ter licença própria
    "bis": NAO_COMERCIAL,  # só uso não comercial sem permissão; sem pedir (Tiago, 22/10/2026)
    "nasa": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0
    "noaa": VENDAVEL_COM_ATRIBUICAO,  # obra do governo dos EUA
    "inpe": A_CONFIRMAR,  # sem licença escrita no INPE Queimadas
    "firms": VENDAVEL_COM_ATRIBUICAO,  # dados abertos da NASA
    "terrabrasilis": SO_USO_INTERNO,  # CC BY-SA 4.0 (compartilhar igual): revenda a confirmar
    "ecmwf": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0
    "climatetrace": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0
    "edgar": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0 (JRC)
    "carbonmonitor": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0
    # lote EUA: obra do governo dos EUA, domínio público; o dado do NY Fed leva a atribuição
    "treasury": VENDAVEL_COM_ATRIBUICAO,
    "fed": VENDAVEL_COM_ATRIBUICAO,
    "bls": VENDAVEL_COM_ATRIBUICAO,
    "eia": VENDAVEL_COM_ATRIBUICAO,
    "ofr": VENDAVEL_COM_ATRIBUICAO,
    "nyfed": VENDAVEL_COM_ATRIBUICAO,
    "tic": VENDAVEL_COM_ATRIBUICAO,
    "census": VENDAVEL_COM_ATRIBUICAO,
    # lote cadastros globais: CC0, domínio público, reuso da UE e OGL v3 (rodada 4); só pessoa jurídica
    "sec-company-tickers": VENDAVEL_COM_ATRIBUICAO,
    "wikidata": VENDAVEL_COM_ATRIBUICAO,
    "ofac": VENDAVEL_COM_ATRIBUICAO,
    "eufsf": VENDAVEL_COM_ATRIBUICAO,
    "ofsi": VENDAVEL_COM_ATRIBUICAO,
    # lote setoriais Brasil: CC BY 4.0 (EPE); rodapé CC BY-ND do site gov.br e licença do conjunto
    # não achada (INEP, Senatran, INPI, demonstrações da ANS): a confirmar, coleta e uso com a fonte citada
    "epe": VENDAVEL_COM_ATRIBUICAO,
    # lote atenção e texto: CC0, CC BY 4.0 e uso livre citando o GDELT (Emenda 5 da ADR 0008); o índice
    # do RSS é texto de terceiros e fica a confirmar. `wiki` e `gdelt` (cripto) mantêm a marca antiga
    "wiki-pageviews-empresas": VENDAVEL_COM_ATRIBUICAO,
    "gdelt-gkg": VENDAVEL_COM_ATRIBUICAO,
    "querido": VENDAVEL_COM_ATRIBUICAO,
    "crossref": VENDAVEL_COM_ATRIBUICAO,
    "openalex": VENDAVEL_COM_ATRIBUICAO,
    "ebc": A_CONFIRMAR,
    "senado": A_CONFIRMAR,
    "camara": A_CONFIRMAR,
    "inep": A_CONFIRMAR,
    "senatran": A_CONFIRMAR,
    "inpi": A_CONFIRMAR,
    "epo": VENDAVEL_COM_ATRIBUICAO,  # CC BY 4.0; "not designed to provide a backend database service"
    "ipea": A_CONFIRMAR,  # sem termos; cada série herda a fonte de origem (BM&FBovespa, Bacen, IBGE)
    "wipo": SO_USO_INTERNO,  # "not republish or commercially re-sell"; citar "WIPO Statistics Database"
    "ans-demonstracoes": A_CONFIRMAR,
}


class Marca(StrEnum):
    """As quatro marcas da Emenda 1 da ADR 0008, da menos para a mais restrita."""

    VENDAVEL = "vendavel"
    USO_INTERNO = "uso_interno"
    A_CONFIRMAR = "a_confirmar"  # vale como não comercial até a resposta escrita
    NAO_COMERCIAL = "nao_comercial"


MARCA_DA_REVENDA = {
    VENDAVEL_ODBL: Marca.VENDAVEL,
    VENDAVEL_COM_ATRIBUICAO: Marca.VENDAVEL,
    SO_USO_INTERNO: Marca.USO_INTERNO,
    A_CONFIRMAR: Marca.A_CONFIRMAR,
    NAO_COMERCIAL: Marca.NAO_COMERCIAL,
}


class Coleta(StrEnum):
    """Podemos baixar, e como? (ADR 0108, D3)."""

    ABERTA = "aberta"  # o termo e o robots.txt permitem, ou não dizem nada
    # API com chave ou conta, pelo caminho que o dono oferece
    COM_CADASTRO = "com_cadastro"
    # a licença do dado permite reuso, mas o robots.txt fecha o servidor ou o caminho que usamos
    ROBOTS_FECHA = "robots_fecha"
    TERMO_VEDA = "termo_veda"  # o termo veda robô, raspagem ou cópia
    NAO_LIDA = "nao_lida"


class Guarda(StrEnum):
    """Podemos guardar, e por quanto tempo? (ADR 0108, D3)."""

    SEM_PRAZO = "sem_prazo"
    COM_PRAZO = "com_prazo"  # com o número de dias em `dias_de_guarda`
    # cópia como prova interna, nunca mostrada (ADR 0102, ponto 3)
    SO_PROVA = "so_prova"
    NAO_GUARDAR = "nao_guardar"
    NAO_DIZ = "nao_diz"


class ColetaEGuarda(NamedTuple):
    """As duas perguntas da ADR 0108 (D3) ao lado da revenda, por família do `LICENCAS`.

    A data da leitura dos termos é a de `TERMOS_LIDOS_EM` (`base/arquivo/registro.py`), sem cópia
    aqui; `revisar_em` vazio vale a leitura mais o prazo padrão do portão externo.
    """

    coleta: Coleta
    guarda: Guarda
    termo: str = ""  # endereço e hash da cópia guardada do termo
    revisar_em: date | None = None
    dias_de_guarda: int | None = None  # só com `Guarda.COM_PRAZO`
    # as condições (a) e (b) do D5.3 da ADR 0108, que deixam `ROBOTS_FECHA` sair pela API externa:
    # (a) licença escrita pelo próprio órgão permite reuso comercial (CC BY, ODbL, domínio público);
    # (b) a coleta respeita o Crawl-delay e se identifica com o User-Agent do TickerLab
    licenca_permite_reuso_comercial: bool = False
    respeita_ritmo_e_se_identifica: bool = False


# Coleta e guarda de cada família do `LICENCAS` (linha 159 da fila; ADR 0108, D3 e D5.3). As respostas
# são as da auditoria N0 de 21/10/2026 (`auditoria-licitude-da-coleta-2026-10-21.md`, na pasta privada),
# copiadas sem decidir de novo: "sim" é `aberta` e `sem_prazo`; "não" é `termo_veda` e `nao_guardar`;
# "não diz" e "não lido" são `nao_lida` e `nao_diz`, que seguem negadas pelo portão externo (`src/
# portao_externo.py`). Família que a N0 não cobriu (lotes de 22 e 23/10) também fica sem resposta.
# `ROBOTS_FECHA` leva as duas condições do D5.3 pelo que a N0 e o código dizem: (a) a licença escrita
# do órgão permite reuso comercial; (b) o arquivista lê o `Crawl-delay` e manda o `User-Agent` do
# TickerLab (`base/arquivo/ritmo.py` e `agente.py`, PR 600). A data da leitura dos termos está em
# `TERMOS_LIDOS_EM`; o app não lê esta tabela (ADR 0102).
_NAO_RESPONDIDA = ColetaEGuarda(Coleta.NAO_LIDA, Guarda.NAO_DIZ)
_ABERTA_SEM_PRAZO = ColetaEGuarda(Coleta.ABERTA, Guarda.SEM_PRAZO)
_ABERTA_GUARDA_NAO_DIZ = ColetaEGuarda(Coleta.ABERTA, Guarda.NAO_DIZ)
_TERMO_VEDA_NAO_GUARDAR = ColetaEGuarda(Coleta.TERMO_VEDA, Guarda.NAO_GUARDAR)
# o robots.txt fecha o portal (`Disallow: /api/` ou `/`), a licença escrita do órgão permite reuso
# comercial e o arquivista respeita o ritmo e se identifica
_ROBOTS_FECHA_COM_LICENCA = ColetaEGuarda(
    Coleta.ROBOTS_FECHA,
    Guarda.SEM_PRAZO,
    licenca_permite_reuso_comercial=True,
    respeita_ritmo_e_se_identifica=True,
)

COLETA_E_GUARDA: dict[str, ColetaEGuarda] = {
    # a N0 diz: coleta sim, retenção sim
    **dict.fromkeys(
        (
            "bm",
            "tesouro",
            "cftc",
            "gdelt",
            "btc",
            "cgu",
            "ibama",
            "gleif",
            "anp",
            "anac",
            "ans",
            "anatel",
            "susep",
            "assessoria",
            "conab",
            "usda",
            "faostat",
            "tce-pr",
            "tce-pr-pit",
            "tce-pr-despesa",
            "tesouro-br",
            "tesouro-br-divida",
            "tesouro-br-direto",
            "tesouro-br-leiloes",
        ),
        _ABERTA_SEM_PRAZO,
    ),
    # robots.txt fecha o portal; licença ODbL, CC BY ou domínio público (D5.3)
    **dict.fromkeys(
        (
            "cvm",
            "bcb",
            "ccee",
            "antt",
            "aneel",
            "tce-rs-empenhos",
            "chirps",  # Disallow: / ; domínio público
            "rfb-cnpj",  # Disallow: / ; CC BY na ficha do dados.gov.br
        ),
        _ROBOTS_FECHA_COM_LICENCA,
    ),
    # a N0 diz coleta sim e retenção "não diz"
    **dict.fromkeys(("sec", "bcb-sgs-189", "iex"), _ABERTA_GUARDA_NAO_DIZ),
    # o termo veda a coleta e a cópia
    **dict.fromkeys(("yahoo", "kraken", "fnc"), _TERMO_VEDA_NAO_GUARDAR),
    "fmi": ColetaEGuarda(
        Coleta.TERMO_VEDA, Guarda.NAO_DIZ
    ),  # veda coleta em massa sem permissão
    "b3": ColetaEGuarda(
        Coleta.TERMO_VEDA, Guarda.NAO_DIZ
    ),  # BDI veda; VPS 90 dias, casa sem prazo
    "contrapartes": ColetaEGuarda(Coleta.TERMO_VEDA, Guarda.SO_PROVA),
    # robots.txt fecha o portal e a N0 não achou licença escrita que dê reuso comercial (ONS: "reuso e
    # redistribuição" sem nome de licença; catálogo: só metadados; Cecafé: `Disallow: /*.pdf$`)
    "ons": ColetaEGuarda(Coleta.ROBOTS_FECHA, Guarda.SEM_PRAZO),
    "catalogo": ColetaEGuarda(Coleta.ROBOTS_FECHA, Guarda.SEM_PRAZO),
    "cecafe": ColetaEGuarda(Coleta.ROBOTS_FECHA, Guarda.NAO_DIZ),
    # a N0 diz retenção sim, coleta "não diz" ou não lida
    "chirps3": _ABERTA_SEM_PRAZO,  # robots.txt do Hugging Face: Allow: /
    "mapbiomas": ColetaEGuarda(
        Coleta.NAO_LIDA, Guarda.SEM_PRAZO
    ),  # CC BY-SA (termos do site, 21/10/2026)
    "termos": ColetaEGuarda(
        Coleta.NAO_LIDA, Guarda.SO_PROVA
    ),  # cópias de termos; três são da B3
    # a N0 não respondeu a coleta nem a guarda
    **dict.fromkeys(
        (
            "ibge",
            "inmet",
            "rfb",
            "wiki",
            "mb",
            "pgfn",
            "mte",
            "comexstat",
            "wayback",
            "tce-rs",
            "ico",
            # famílias que a N0 não cobriu (lotes de 22 e 23/10)
            "transparencia",
            "bndes",
            "inss",
            "seges",
            "seges-pesquisa-precos",
            "comprasgov",
            "transferegov",
            "pncp",
            "tcu",
            "govmg",
            "govsc",
            "tesouro-br-siconfi-entes",
            "tesouro-br-siconfi-entregas",
            "tesouro-br-siconfi-rreo",
            "tesouro-br-siconfi-rgf",
            "tesouro-br-siconfi-dca",
            "tesouro-br-rtn",
            "tesouro-br-receitas",
            "tesouro-br-despesas",
            "tesouro-br-restos-a-pagar",
            "tesouro-br-fatores-divida",
            "tesouro-br-paf",
            "tesouro-br-bspn",
            "tesouro-br-limites-lrf",
            "tesouro-br-dividendos-estatais",
            "tesouro-br-subsidios-bndes",
            "tesouro-br-garantias",
            "tesouro-br-transferencias",
            "tesouro-br-capag-municipios",
            "tesouro-br-td-vendas",
            "tesouro-br-td-resgates",
            "tesouro-br-td-estoque",
            "bce",
            "ocde",
            "eurostat",
            "worldbank",
            "bis",
            "nasa",
            "noaa",
            "inpe",
            "firms",
            "terrabrasilis",
            "ecmwf",
            "climatetrace",
            "edgar",
            "carbonmonitor",
            "treasury",
            "fed",
            "bls",
            "eia",
            "ofr",
            "nyfed",
            "tic",
            "census",
            "sec-company-tickers",
            "wikidata",
            "ofac",
            "eufsf",
            "ofsi",
            "epe",
            "wiki-pageviews-empresas",
            "gdelt-gkg",
            "querido",
            "crossref",
            "openalex",
            "ebc",
            "senado",
            "camara",
            "inep",
            "senatran",
            "inpi",
            "epo",
            "wipo",
            "ipea",
            "ans-demonstracoes",
        ),
        _NAO_RESPONDIDA,
    ),
}
MOSTRAR = "mostrar"  # em tela, relatório, PDF, API ou newsletter
USOS = ("treinar", "rotular", "exportar", MOSTRAR)
# As famílias fora dos quatro usos. Vazia desde 22/10/2026: a B3, a única que havia (ADR 0102; dado de
# mercado pede contrato, ADRs 0019 e 0056), entrou com a fonte e a data citadas por decisão do Tiago
# (ADR 0008, Emenda 6, risco assumido por ele). O mecanismo fica: pôr uma família aqui volta a barrá-la
# em `pode_usar` e `exigir_licenca` (é o "como desfazer" da Emenda 6: pôr "b3" de volta).
FONTES_FORA_DOS_USOS: frozenset[str] = frozenset()


class UsoSemCobranca(NamedTuple):
    """Um uso de fonte restrita em tela, com a frase de citação (ADR 0008, Emenda 3, item 4)."""

    fonte: str  # a fonte ou a família em `REVENDA` ("yahoo" vale para "yahoo-bvsp")
    onde: str  # onde aparece no app ou no relatório
    substituto: str  # o que entraria no lugar se a fonte um dia tiver de sair
    citacao: str  # a frase que a tela, o relatório e o PDF escrevem como fonte


class CaminhoDoYahoo(NamedTuple):
    """Módulos que leem o preço do Yahoo, com o que entra no lugar quando ele sair (linha 413, Y2)."""

    modulos: tuple[str, ...]  # caminho do arquivo a partir da raiz do repositório
    onde: str
    substituto: str


_BASE_PROPRIA = (
    "base própria de preços pelo COTAHIST da B3 (ações, FIIs e ETFs); EUA, índices e cripto "
    "ficam sem preço ou com outra fonte"
)
# Emenda 3 da ADR 0008, item 4, completa ("pode" do Tiago em 25/10/2026, linha 413, Y2): todo módulo
# que chega ao Yahoo, para o dia de trocar ou desligar a fonte (antes da 1ª cobrança, Y4 b). O teste
# `tests/test_caminhos_do_yahoo.py` lê o código e falha se um módulo novo chegar ao Yahoo fora daqui.
CAMINHOS_DO_YAHOO: tuple[CaminhoDoYahoo, ...] = (
    CaminhoDoYahoo(
        ("src/dados.py", "telas/comum.py", "src/api_v1/contexto.py"),
        "a porta do preço: baixa do Yahoo, guarda no cache em SQLite (7 dias sem consulta e sai) e "
        "serve as telas e a API",
        _BASE_PROPRIA,
    ),
    CaminhoDoYahoo(
        (
            "telas/analise.py",
            "telas/carteira_b3.py",
            "telas/momentum.py",
            "telas/estrategias/aprendizado.py",
            "telas/estrategias/backtest.py",
            "telas/estrategias/carteira.py",
            "telas/estrategias/experimentos.py",
            "telas/estrategias/pares.py",
            "telas/estrategias/ranking.py",
            "telas/estrategias/regimes.py",
            "telas/relatorios/estudio.py",
            "telas/relatorios/pagina.py",
            "telas/research/alertas.py",
            "telas/research/donos.py",
            "telas/research/fundamentos.py",
            "telas/research/linha_do_tempo.py",
            "telas/research/parametros.py",
            "telas/research/por_dentro.py",
            "telas/research/pulse.py",
        ),
        "telas do app: a série do ticker do topo nos gráficos, no risco, no backtest, na carteira, "
        "no momentum, no Research e no PDF do Estúdio",
        _BASE_PROPRIA,
    ),
    CaminhoDoYahoo(
        ("telas/research/relatorio_empresa.py",),
        "ficha da empresa: DY, valor de mercado e múltiplos (atrás da trava "
        "TICKERLAB_PRECO_NO_RELATORIO, que com =0 nem carrega a série)",
        _BASE_PROPRIA,
    ),
    CaminhoDoYahoo(
        ("src/api_v1/rotas.py",),
        "API do app: /visao-geral, /risco, /retorno-mensal, /comparacao, /backtest e "
        "/relatorio-empresa (este atrás da trava)",
        _BASE_PROPRIA,
    ),
    CaminhoDoYahoo(
        ("src/ferramentas/ponte_dados.py",),
        "site: 'Quanto daria? Foi sorte?' com ^BVSP e BTC-USD; só o resultado sai (ADR 0070)",
        "Ibovespa pelo arquivo de índices da B3; bitcoin pelas corretoras da ADR 0045",
    ),
    CaminhoDoYahoo(
        ("scripts/atualizar_series_macro.py",),
        "séries macro yahoo-bvsp e yahoo-gspc no banco, só de uso interno (nunca exportadas)",
        "Ibovespa pelo arquivo de índices da B3; S&P 500 desligado",
    ),
    CaminhoDoYahoo(
        ("scripts/atualizar_padroes.py",),
        "P/L e P/VP nos padrões setoriais (só com --com-precos; a trava tira da ficha)",
        _BASE_PROPRIA,
    ),
)


# Emenda 3 da ADR 0008 (18/10/2026): os usos em tela das fontes "a confirmar" e "não comercial", cada
# um com a frase de citação. Desde a ADR 0102 a lista **não decide** mais o que pode aparecer (tudo
# pode): ela registra onde cada fonte restrita aparece, a frase que a tela, o relatório
# e o PDF escrevem (`citacoes_das_fontes`) e o substituto, para o dia em que uma fonte tiver de sair.
USOS_SEM_COBRANCA: tuple[UsoSemCobranca, ...] = (
    UsoSemCobranca(
        "yahoo",
        "todo preço do app: ficha da empresa (DY e múltiplos), padrões setoriais, gráficos, "
        "backtest, comparação, carteira, Estúdio de PDF, API e 'Quanto daria?' (ADR 0070); "
        "caminho a caminho em CAMINHOS_DO_YAHOO",
        "base própria de preços pelo COTAHIST da B3 (ADR 0008, Emenda 6); preços dos EUA "
        "desligados na 1ª cobrança (Emenda 4)",
        "Preço da ação: Yahoo Finance (uso pessoal; mostrado com a fonte citada enquanto o "
        "TickerLab não cobra, ADR 0008 Emenda 3)",
    ),
    UsoSemCobranca(
        "pgfn",
        "dívida ativa da União na ficha da empresa",
        "resposta escrita da PGFN sobre a licença (pedido LAI da ADR 0086); sem ela, desligar",
        "Dívida ativa: dados abertos da PGFN (licença a confirmar; mostrado com a fonte citada "
        "enquanto o TickerLab não cobra)",
    ),
    UsoSemCobranca(
        "comexstat",
        "comércio exterior por capítulo do NCM na B13 (empresa ↔ série) e na rede de entidades",
        "confirmação do MDIC pelo Fala.BR (pedido de 14/10/2026); sem ela, desligar a série",
        "Comércio exterior: Comex Stat, MDIC (licença aberta sem nome, a confirmar; mostrado com "
        "a fonte citada enquanto o TickerLab não cobra)",
    ),
    UsoSemCobranca(
        "assessoria",
        "negócios de M&A do middle market (só fatos: partes, tipo e data; ADR 0082)",
        "parecer jurídico sobre os posts das assessorias (ADR 0060); sem ele, desligar",
        "Negócios de M&A: posts públicos das assessorias, só os fatos (ADR 0082; mostrado com a "
        "fonte citada enquanto o TickerLab não cobra)",
    ),
    UsoSemCobranca(
        "bcb-sgs-189",
        "IGP-M nas séries macro e nos deflatores",
        "autorização da FGV IBRE para uso comercial; sem ela, IPCA (IBGE, domínio público)",
        "IGP-M: FGV IBRE, repassado pelo SGS do Banco Central (uso comercial pede autorização "
        "da FGV; mostrado com a fonte citada enquanto o TickerLab não cobra)",
    ),
    UsoSemCobranca(
        "wayback",
        "data das cópias dos posts de M&A (`ma_datas`) e das páginas guardadas",
        "data do próprio coletor (a primeira coleta nossa) ou a data declarada no post",
        "Datas: cópias do Internet Archive (Wayback Machine; só pesquisa; mostrado com a fonte "
        "citada enquanto o TickerLab não cobra)",
    ),
    UsoSemCobranca(
        "conab",
        "safra de café (levantamentos da CONAB como publicados, termômetro e bienalidade) na área "
        "de commodities, na API e nos PDFs",
        "nenhum oficial: a CONAB é a única fonte da safra brasileira; sem ela, só o balanço do "
        "USDA PSD (`usda_psd_cafe`)",
        "Safra de café: CONAB, Acompanhamento da Safra Brasileira de Café, com a data do "
        "levantamento em cada número (CC BY-ND 3.0; mostrado com a fonte citada, ADR 0102)",
    ),
    UsoSemCobranca(
        "b3",
        "preço de fim de dia (COTAHIST), arquivos públicos e carteiras dos índices da B3, onde a "
        "base os mostrar (dossiê, ficha, DY e múltiplos de mercado, PDFs)",
        "licença da B3 (contrato, nível 1); sem ela ou se a B3 reclamar, voltar `FONTES_FORA_DOS_USOS` "
        "ao estado da Emenda 4 e tirar o dado da B3 das telas",
        "Fonte: B3, com a data de cada número (sem licença da B3; mostrado com a fonte citada, "
        "risco assumido, ADR 0008 Emenda 6)",
    ),
)
# Emenda 2 da ADR 0008, item 6: em toda tela ou PDF com dado da IEX
FRASE_DA_IEX = (
    "Data provided for free by IEX. By accessing or using IEX Historical Data, "
    "you agree to the IEX Historical Data Terms of Use."
)
# crédito no formato que a FAO pede (CC BY 4.0), em toda tela, API ou PDF com dado do FAOSTAT
FRASE_DA_FAO = (
    "FAO, FAOSTAT: Crops and livestock products (CC BY 4.0; acessado na data de cada número; "
    "a FAO não endossa o TickerLab)"
)
# crédito que a Receita pede (CC BY), em toda tela, API ou PDF com dado do CNPJ aberto
FRASE_DA_RECEITA = "Fonte: Receita Federal, dados abertos do CNPJ (CC BY)"
FRASES_DAS_FONTES = {
    "iex": FRASE_DA_IEX,
    "faostat": FRASE_DA_FAO,
    "rfb-cnpj": FRASE_DA_RECEITA,
}


class LicencaNaoPermiteError(Exception):
    """Treinar, rotular, exportar ou mostrar com fonte fora dos usos (`FONTES_FORA_DOS_USOS`, hoje vazia)."""


LIMITE_DO_DETALHE = 300
LIMITE_DA_URL = 1000
HTTP_NAO_ENCONTRADO = 404


def licenca_da_fonte(fonte: str) -> str:
    """A licença da fonte ("rfb-cnpj") ou da sua família ("cvm-ipe" → a da CVM)."""
    return LICENCAS.get(fonte) or LICENCAS.get(
        fonte.split("-", 1)[0], SEM_LICENCA_CONHECIDA
    )


def revenda_da_fonte(fonte: str) -> str:
    """Se o dado da fonte pode ser revendido ("cvm-ipe" → o da CVM); fonte desconhecida, a confirmar
    (fonte nova sem resposta escrita: ADR 0008, Emenda 1)."""
    return REVENDA.get(fonte) or REVENDA.get(fonte.split("-", 1)[0], A_CONFIRMAR)


def marca_da_fonte(fonte: str) -> Marca:
    """A marca da fonte ("yahoo-bvsp" → não comercial; "cvm-ipe" → vendável)."""
    return MARCA_DA_REVENDA[revenda_da_fonte(fonte)]


def marca_mais_restrita(marcas: Iterable[Marca]) -> Marca:
    """A marca de uma tabela feita de várias fontes; sem nenhuma fonte conhecida, a confirmar."""
    ordem = list(Marca)
    return max(marcas, key=ordem.index, default=Marca.A_CONFIRMAR)


def _familia(fonte: str) -> str:
    return fonte.split("-", 1)[0]


def uso_sem_cobranca(fonte: str) -> UsoSemCobranca | None:
    """A entrada de `USOS_SEM_COBRANCA` da fonte ("yahoo-bvsp" → a do Yahoo), se houver."""
    por_fonte = {uso.fonte: uso for uso in USOS_SEM_COBRANCA}
    return por_fonte.get(fonte) or por_fonte.get(_familia(fonte))


def fora_dos_usos(fonte: str) -> bool:
    """A fonte ("b3-negocios") ou a família dela está fora dos quatro usos? Hoje nenhuma (a B3 saiu em 22/10/2026)."""
    return _familia(fonte) in FONTES_FORA_DOS_USOS


def _conferir_uso(uso: str) -> None:
    if uso not in USOS:
        raise ValueError(f"uso {uso!r} não existe; use um de {USOS}")


def pode_usar(uso: str, fonte: str) -> bool:
    """A fonte pode `uso` ("treinar", "rotular", "exportar" ou "mostrar")? `exigir_licenca` sem o erro.

    Pela ADR 0102 a marca não decide: toda fonte entra em qualquer uso, com a fonte e a data citadas
    (`citacoes_das_fontes`); só entra em `FONTES_FORA_DOS_USOS` o que uma decisão nova barrar. Vale para o app
    (tela, PDF, newsletter e a v1 interna); a API externa tem outra regra, que nega por padrão:
    `src/portao_externo.py` (ADR 0108).
    """
    _conferir_uso(uso)
    return not fora_dos_usos(fonte)


def exigir_licenca(uso: str, fontes: Iterable[str], onde: str = "") -> None:
    """Erro (não aviso) se alguma fonte está fora de `uso` ("treinar", "rotular", "exportar" ou "mostrar").

    Só barra o que está em `FONTES_FORA_DOS_USOS` (hoje nada); a marca é informação (ADR 0102). `onde`
    (a tabela, o script, o relatório) entra na mensagem.
    """
    _conferir_uso(uso)
    barradas = sorted({f for f in fontes if fora_dos_usos(f)})
    if barradas:
        lista = ", ".join(f"{f} ({marca_da_fonte(f)})" for f in barradas)
        alvo = f" ({onde})" if onde else ""
        raise LicencaNaoPermiteError(
            f"{uso}{alvo} com fonte fora dos usos: {lista} (lista `FONTES_FORA_DOS_USOS` da "
            "ADR 0008; Emenda 6 liberou a B3 em 22/10/2026)"
        )


def citacoes_das_fontes(fontes: Iterable[str]) -> list[str]:
    """As frases que a tela, o relatório e o PDF escrevem pelas fontes restritas que usam, sem
    repetir: a citação de cada uso sem cobrança (Emenda 3) e a frase da IEX (Emenda 2, item 6)."""
    citacoes: dict[str, None] = {}
    for fonte in fontes:
        frase = FRASES_DAS_FONTES.get(fonte) or FRASES_DAS_FONTES.get(_familia(fonte))
        uso = uso_sem_cobranca(fonte)
        if frase:
            citacoes[frase] = None
        elif uso is not None and marca_da_fonte(fonte) != Marca.VENDAVEL:
            citacoes[uso.citacao] = None
    return list(citacoes)


def registrar(
    conexao: sa.Connection,
    fonte: str,
    url: str,
    conteudo: bytes | None,
    situacao: str,
    detalhe: str | None = None,
    agora: datetime | None = None,
    caminho_do_original: str | None = None,
) -> None:
    """Grava uma linha do registro. `conteudo` None = nada foi baixado (404 ou falha)."""
    registrar_arquivo(
        conexao,
        fonte,
        url,
        None if conteudo is None else hashlib.sha256(conteudo).hexdigest(),
        None if conteudo is None else len(conteudo),
        situacao,
        detalhe,
        agora,
        caminho_do_original,
    )


def registrar_arquivo(
    conexao: sa.Connection,
    fonte: str,
    url: str,
    sha256: str | None,
    tamanho: int | None,
    situacao: str,
    detalhe: str | None = None,
    agora: datetime | None = None,
    caminho_do_original: str | None = None,
) -> None:
    """Como `registrar`, para arquivos grandes: o SHA-256 e o tamanho já vêm calculados (em partes)."""
    conexao.execute(
        sa.insert(coletas).values(
            id=uuid.uuid4(),
            fonte=fonte,
            url=url[:LIMITE_DA_URL],
            situacao=situacao,
            bytes=tamanho,
            sha256=sha256,
            licenca=licenca_da_fonte(fonte),
            detalhe=None if detalhe is None else detalhe[:LIMITE_DO_DETALHE],
            caminho_do_original=caminho_do_original,
            baixado_em=agora or datetime.now(UTC),
            versao_do_codigo=versao_do_codigo(),
        )
    )


def ultima_coleta_ok(conexao: sa.Connection, url: str) -> sa.Row | None:
    """A coleta "ok" mais recente de `url` (para saber se o arquivo mudou), ou None."""
    return conexao.execute(
        sa.select(coletas)
        .where(coletas.c.url == url[:LIMITE_DA_URL], coletas.c.situacao == "ok")
        .order_by(coletas.c.baixado_em.desc())
        .limit(1)
    ).first()


def original_mais_recente(conexao: sa.Connection, url: str) -> bytes | None:
    """A cópia mais recente de `url` guardada no acervo (None se nenhuma coleta guardou).

    Serve para reler um arquivo sem baixar de novo (regras de qualidade, base "como era na data").
    """
    caminho = conexao.execute(
        sa.select(coletas.c.caminho_do_original)
        .where(
            coletas.c.url == url[:LIMITE_DA_URL],
            coletas.c.situacao == "ok",
            coletas.c.caminho_do_original.is_not(None),
        )
        .order_by(coletas.c.baixado_em.desc())
        .limit(1)
    ).scalar()
    return acervo.ler_original(caminho) if caminho else None


class Versao(NamedTuple):
    baixado_em: datetime  # a primeira vez que este conteúdo foi baixado
    sha256: str
    caminho: str  # no acervo (`acervo.ler_original`)


def versoes_guardadas(conexao: sa.Connection, url: str) -> list[Versao]:
    """Cada conteúdo diferente de `url` guardado no acervo, do mais antigo ao mais novo, sem ler os
    arquivos (o CDA tem ~25 MB por versão: quem usa lê um de cada vez)."""
    linhas = conexao.execute(
        sa.select(coletas.c.baixado_em, coletas.c.sha256, coletas.c.caminho_do_original)
        .where(
            coletas.c.url == url[:LIMITE_DA_URL],
            coletas.c.situacao == "ok",
            coletas.c.caminho_do_original.is_not(None),
        )
        .order_by(coletas.c.baixado_em)
    ).all()
    vistos: set[str] = set()
    versoes = []
    for baixado_em, sha256, caminho in linhas:
        if sha256 not in vistos:
            vistos.add(sha256)
            versoes.append(Versao(baixado_em, sha256, caminho))
    return versoes


def ausente_antes(conexao: sa.Connection, url: str, quando: datetime) -> bool:
    """Alguma coleta antes de `quando` achou `url` sem arquivo ("nao_encontrado", o 404 da fonte)?"""
    return (
        conexao.execute(
            sa.select(coletas.c.id)
            .where(
                coletas.c.url == url[:LIMITE_DA_URL],
                coletas.c.situacao == "nao_encontrado",
                coletas.c.baixado_em < quando,
            )
            .limit(1)
        ).first()
        is not None
    )


def coletas_guardadas(
    conexao: sa.Connection, url: str
) -> list[tuple[datetime, str, bytes]]:
    """Cada conteúdo diferente de `url` guardado no acervo (quando foi baixado pela primeira vez, o
    SHA-256 e o conteúdo), do mais antigo ao mais novo (revisões das fontes setoriais, série 4, PR 5)."""
    guardadas = []
    for baixado_em, sha256, caminho in versoes_guardadas(conexao, url):
        conteudo = acervo.ler_original(caminho)
        if conteudo is not None:
            guardadas.append((baixado_em, sha256, conteudo))
    return guardadas


def originais_guardados(conexao: sa.Connection, url: str) -> list[bytes]:
    """Cada conteúdo diferente de `url` guardado no acervo, do mais antigo ao mais novo.

    A fonte que regrava o arquivo no mesmo endereço (o FCA da CVM só publica a versão mais nova de cada
    formulário) deixa no acervo as baixadas anteriores, que continuam valendo como versões.
    """
    return [conteudo for _, _, conteudo in coletas_guardadas(conexao, url)]


def ultimas(
    conexao: sa.Connection, fonte: str | None = None, quantas: int = 50
) -> list[sa.Row]:
    """As coletas mais recentes (de uma fonte, ou de todas), da mais nova para a mais velha."""
    consulta = sa.select(coletas).order_by(coletas.c.baixado_em.desc()).limit(quantas)
    if fonte is not None:
        consulta = consulta.where(coletas.c.fonte == fonte)
    return list(conexao.execute(consulta))


def _guardar_sem_atrapalhar(
    fonte: str, url: str, conteudo: bytes, agora: datetime
) -> str | None:
    try:
        return acervo.guardar_original(fonte, url, conteudo, agora)
    except OSError:
        # disco cheio ou sem permissão: a coleta segue; o registro fica sem o caminho
        log.exception("Falha ao guardar o original da coleta de %s", fonte)
        return None


def _registrar_sem_atrapalhar(
    fonte: str, url: str, conteudo: bytes | None, situacao: str, detalhe: str | None
) -> None:
    agora = datetime.now(UTC)
    caminho = None
    if conteudo is not None:
        caminho = _guardar_sem_atrapalhar(fonte, url, conteudo, agora)
    try:
        with obter_engine().begin() as conexao:
            registrar(conexao, fonte, url, conteudo, situacao, detalhe, agora, caminho)
    except Exception:
        # o registro é para auditoria; a coleta segue mesmo sem ele
        log.exception("Falha ao registrar a coleta de %s", fonte)


def com_registro[Conteudo: (bytes, bytes | None)](
    fonte: str, baixar: Callable[..., Conteudo]
) -> Callable[..., Conteudo]:
    """Embrulha a função `baixar(url, ...)` de uma coleta para registrar cada arquivo.

    Arquivo baixado → guardado no acervo e "ok" com tamanho e SHA-256; `None` (a fonte respondeu 404) →
    "nao_encontrado"; erro → "falhou" e o erro segue para a coleta, como antes.
    """

    def baixar_e_registrar(url: str, *args: object, **kwargs: object) -> Conteudo:
        try:
            conteudo = baixar(url, *args, **kwargs)
        except Exception as erro:
            _registrar_sem_atrapalhar(fonte, url, None, "falhou", type(erro).__name__)
            raise
        situacao = "nao_encontrado" if conteudo is None else "ok"
        _registrar_sem_atrapalhar(fonte, url, conteudo, situacao, None)
        return conteudo

    return baixar_e_registrar


def buscar_com_registro(
    fonte: str, buscar: Callable[..., requests.Response] = rede.get_com_agente
) -> Callable[..., requests.Response]:
    """Como `com_registro`, para os leitores que recebem um `buscar` no lugar do `requests.get`
    (Banco Central, Tesouro dos EUA): registra o endereço completo (com a consulta) e a resposta."""

    def buscar_e_registrar(
        url: str, *args: object, **kwargs: object
    ) -> requests.Response:
        try:
            resposta = buscar(url, *args, **kwargs)
        except Exception as erro:
            _registrar_sem_atrapalhar(fonte, url, None, "falhou", type(erro).__name__)
            raise
        endereco = getattr(resposta, "url", None) or url
        if resposta.ok:
            _registrar_sem_atrapalhar(fonte, endereco, resposta.content, "ok", None)
        else:
            situacao = (
                "nao_encontrado"
                if resposta.status_code == HTTP_NAO_ENCONTRADO
                else "falhou"
            )
            detalhe = f"HTTP {resposta.status_code}"
            _registrar_sem_atrapalhar(fonte, endereco, None, situacao, detalhe)
        return resposta

    return buscar_e_registrar


def originais_mais_recentes(conexao: sa.Connection, fonte: str) -> list[sa.Row]:
    """A coleta mais recente de cada endereço da fonte que tem o original guardado."""
    linhas = conexao.execute(
        sa.select(
            coletas.c.url,
            coletas.c.sha256,
            coletas.c.caminho_do_original,
            coletas.c.baixado_em,
        )
        .where(
            coletas.c.fonte == fonte,
            coletas.c.situacao == "ok",
            coletas.c.caminho_do_original.is_not(None),
        )
        .order_by(coletas.c.url, coletas.c.baixado_em)
    ).all()
    mais_recente: dict[str, sa.Row] = {}
    for linha in linhas:
        mais_recente[linha.url] = linha  # a ordem por data deixa a última
    return list(mais_recente.values())
