# Sintegra estadual: cadastro restrito por estabelecimento

A coleta operacional nesta entrega é somente a do Paraná. RS e MG têm leitores
testados com dados sintéticos, mas são recusados antes de qualquer acesso à rede.
Não houve carga real, agendamento ou alteração de API, conector, tela ou site.

```powershell
python -m scripts.carga_sintegra_estadual --uf PR
# Destino opcional: diretório base do acervo, que também contém cnpj/vigente/simples
python -m scripts.carga_sintegra_estadual --uf PR --pasta D:/acervo/base
```

O comando aceita `--uf PR --uf RS --uf MG`, mas valida todas as UFs antes de
iniciar: se alguma estiver bloqueada, retorna código 1 sem baixar nenhuma.
Não há argumento para substituir URL, ignorar robots ou liberar UF bloqueada.

## Fontes, termos e decisão

Levantamento de referência: nota do Gemini
`2026-11-27-fonte-cadesp-sintegra-1120.md`, lida integralmente na pasta privada
em 27/11/2026. Os termos abaixo são os relatados nessa nota; as conferências
HTTP desta implementação estão separadas na seção seguinte.

| Fonte | O que foi publicado e leitura dos termos em 27/11/2026 |
|---|---|
| [SEFA-PR: Cadastro Resumido](https://www.fazenda.pr.gov.br/Pagina/CAD/ICMS) | Dois arquivos, `ativos` e `cancelados`, com seis campos; sem regime. A página não declara licença aberta. A advertência contra programas automáticos é da consulta unitária com captcha; este coletor usa somente os arquivos em lote. Cancelados não inclui baixados a pedido. |
| [SEFAZ-RS: Cadastro ICS](https://www.sefaz.rs.gov.br/ASP/SEF_root/DWN/SEF-CadastroICS.asp) | `ICS_Ativo.zip` semanal: único lote do levantamento com categoria GERAL/EPP/MICRO/S NAC. Finalidade descrita como validação comercial local. [Termos](https://atendimento.receita.rs.gov.br/termos-de-uso) tratam de requisitos de navegador; a [política](https://www.sefaz.rs.gov.br/w3c/PoliticaPrivacidade.aspx) trata de privacidade. Nenhuma licença aberta declarada. Download bloqueado por robots. |
| [SEF-MG: Cadastro Resumido](https://www.fazenda.mg.gov.br/empresas/sistemas/sintegra/cadastro_simplificado.html) | Cinco campos, sem regime. [Aspectos legais](https://www.fazenda.mg.gov.br/export/utilidades/aspectos_legais.html) tratam de gestão do sítio e marcas; não concedem licença aberta para a base. O nome do contribuinte é descartado. Link de download indisponível. |
| Receita Federal: `cnpj_simples` já no acervo | Opção pelo Simples/MEI, com datas, pela raiz do CNPJ. Licença CC BY conforme o registro existente do projeto; citar a Receita. Não comprova regime ou sublimite estadual de ICMS. Nenhuma nova coleta federal. |

Decisão expressa do Tiago em **27/11/2026, item 23**: **“Colete sem pedir
autorização”**, para arquivos públicos sem licença escrita, sem pedido a terceiro.
A licença registrada no dicionário e no contrato é **“não declarada pela fonte;
uso interno”**. Não se atribui CC BY aos lotes estaduais. A marca de revenda é
`SO_USO_INTERNO`, e a família `sintegra` está em `FONTES_SO_INTERNAS` (inclusive
para ids como `sintegra-estadual`). As listas do empacotador e dos três scripts
de backup/restauração excluem a família. O registro de órgãos é interno: a fonte
também está em `FONTES_NAO_PUBLICADAS`, sem anúncio na lista do site.

A Diretoria confirmou nesta tarefa o escopo ajustado: PR operacional; RS/MG
recusados até existir URL direta permitida e conferida. A decisão de uso da fonte
não autoriza cruzar robots, captcha, WAF ou login.

## Conferência de acesso sem baixar lotes — 27/11/2026

| Pedido | Resposta observada |
|---|---|
| GET `http://processos.fazenda.pr.gov.br/robots.txt` | 404, sem regras publicadas nesse endereço. O cliente confere novamente a cada execução. |
| HEAD `http://processos.fazenda.pr.gov.br/arquivos/ativos` | 200, `Content-Type: Application/zip`; sem Content-Length, Content-MD5 ou Last-Modified. |
| HEAD `http://processos.fazenda.pr.gov.br/arquivos/cancelados` | 200, `Content-Type: Application/zip`; sem Content-Length, Content-MD5 ou Last-Modified. |
| GET do arquivo ativos com `Range: bytes=0-3` | 200, sem Content-Range; anuncia `Content-Disposition: attachment; filename="ativos.zip"`. O servidor ignorou Range: o corpo não foi lido, e a conexão foi fechada. |
| GET `https://www.sefaz.rs.gov.br/robots.txt` | 200; trecho literal abaixo cobre o endpoint `SEF-Download-ICS-Ativo.asp`. |
| HEAD `https://www.fazenda.mg.gov.br/export/utilidades/download.html` | 404, HTML, 842 bytes (página de erro, não o cadastro). |
| HEAD `https://processos.fazenda.pr.gov.br/robots.txt` | Conexão recusada na porta HTTPS. Não se desativou verificação TLS nem se procurou espelho. |

Trecho literal do robots do RS, conferido em 27/11/2026:

```text
User-agent: *
Disallow: /*.asp
```

Não se obteve MD5 nem tamanho dos lotes do PR: os cabeçalhos não os informaram
e o servidor não aceitou Range. O ZIP e seus nomes internos não foram inspecionados.
O leitor aceita TXT simples ou ZIP contendo um único TXT, sem extrair no disco;
arquivos inesperados ou ambíguos falham. Essa compatibilidade foi testada somente
com fixtures sintéticas. Não é prova de uma carga real bem-sucedida.

**Primeira carga real é uma prova isolada**, a ser comandada pela Diretoria em
uma pasta de base de teste, sem substituir o acervo. Conferir contagens, cobertura
e layout antes de promover uma edição. O teto de tolerância a layout divergente
continua zero: mês `000000`, IE inesperada, quebra de linha dentro de campo ou
outra divergência recusam a edição inteira. O próximo passo, se ocorrer, é
registrar apenas motivo e contagem, ajustar a regra com fixture sintética e novo
PR, e repetir a prova. Não relaxar o parser nem guardar células para depurar.

## Colunas e restrição

`base/sintegra_estadual.py::COLUNAS` é a lista fechada do recorte estadual:

| Coluna | Origem e significado |
|---|---|
| `ie`, `cnpj`, `uf`, `arquivo` | Identificação e UF do cadastro; tipo de arquivo ativos/cancelados. |
| `situacao` | Código original de oito dígitos no PR; H/N em MG; ativo pelo lote do RS. |
| `categoria` | Somente RS: GERAL, EPP, MICRO ou S NAC. Ausente no PR/MG, nunca preenchida pelo Simples federal. |
| `cnae` | Sete dígitos publicados, preservados como texto. |
| `codigo_municipio` | Cinco dígitos da SEFA-PR; não se presume código IBGE. |
| `habilitado_desde_mes` | AAAAMM do PR, sem inventar dia. |
| `data_abertura`, `uf_estabelecimento` | Campos do RS; a UF do estabelecimento pode diferir da UF do cadastro. |

PR: seis campos separados por ponto e vírgula. MG: cinco; a terceira posição,
nome do contribuinte, nunca é guardada. RS: sete campos; o CAE é descartado;
o leitor aceita ponto e vírgula, tabulação ou barra vertical, com contagem exata.
Sem amostra real, o separador e nome do membro do RS seguem sujeitos a conferência
quando existir acesso permitido (`ICS_Ativo.txt` é o membro esperado pelo leitor).

Documento precisa de 14 caracteres ASCII e DV válido: as primeiras 12 posições
aceitam números ou letras maiúsculas, os dois DVs são numéricos, conforme
`base/cnpj.py`. Não se completa zero, não se
remove pontuação e não se aceita número decimal. Documento pessoal completado
com três zeros é recusado mesmo quando também passa no DV do CNPJ. Linha com
documento inválido sai; cada origem no manifesto conta `linhas_lidas` e
`documentos_recusados` (numerais em texto, sem os valores recusados). Lote sem
nenhuma linha válida falha. Chave duplicada,
layout divergente, campo inesperado, data inválida ou HTML também falham.
Não se guardam nome, endereço, telefone, e-mail ou coordenada.

CNPJ válido pode pertencer a EI/MEI. Por isso `pessoa=true`, `FORA_DA_PORTA`,
`FORA_DA_CONSULTA_SEM_A_MARCA` e `TABELAS_SO_INTERNAS` mantêm toda a tabela
restrita. Não há view nem anúncio no catálogo público, mesmo após uma carga.

## Ligação federal local

A carga lê apenas as partições necessárias de `base/cnpj/vigente/simples`,
selecionando explicitamente raiz, `optante_simples`, `optante_mei` e as quatro
datas de opção/exclusão. Liga por `cnpj[:8]`, sem busca por nome e sem rede.
Raiz ou partição ausente deixa nulo; não significa “não optante”. Raiz duplicada
falha, sem multiplicar estabelecimentos. `simples_observado_em` registra o dia
em que o vigente foi lido. Datas de opção não são datas de disponibilidade.

Esses campos federais ficam separados da categoria estadual. A ligação não
classifica natureza jurídica e não libera a tabela para consulta externa.

## Edições, disco e manifesto

Destino: `base/sintegra_estadual/<UF>/<edicao>.parquet`. A edição usa a maior
data de Last-Modified dos dois arquivos; se faltar alguma, usa o dia da coleta.
`data_arquivo` fica nula quando a fonte não publica essa informação. O manifesto
registra URL, SHA-256 calculado, data do arquivo e origens federais locais com
hash. Não se inventa MD5 publicado. O SHA-256 identifica os bytes recebidos;
não é autenticação independente da fonte, e os links oficiais do PR usam HTTP.

`publico_em = disponivel_em` é sempre o dia da coleta do conteúdo, nunca a data
de habilitação, abertura, opção ou Last-Modified. `historico_desde` fica vazio
até a primeira carga real. Há também fonte estadual, data/hora da coleta,
commit e data/hora da montagem. A carga compara o SHA-256 do conteúdo normalizado
e as contagens de descarte com a **última edição observada**, escolhida pelo
`coletado_em` das origens do manifesto, independentemente do nome do arquivo.
Conteúdo e contagens idênticos preservam o arquivo e a primeira disponibilidade,
mesmo sem Last-Modified e em outro dia. Conteúdo novo usa a data de edição
definida acima; se esse nome já existe, preserva a anterior em `.vN`, inclusive quando só
acrescenta linhas. A versão nova recebe a disponibilidade da nova coleta;
o `.vN` mantém a disponibilidade antiga.

Quem lê o retrato atual escolhe o manifesto com maior `coletado_em` entre os
Parquets vigentes (sem `.vN`). Para uma data histórica, considera também `.vN`,
filtra `disponivel_em <= data` e escolhe a observação mais recente que já existia.
Nunca concatenar edições como se fossem estabelecimentos diferentes.

O cliente manda o User-Agent oficial do TickerLab, respeita Disallow e Crawl-delay,
faz um GET por arquivo e não segue redirecionamentos nem repete respostas de erro.
Robots inacessível (exceto 404), desafio, HTML, erro HTTP ou tamanho excessivo
impede a carga. O prazo de rede do cliente é 300 segundos, verificado antes/depois
de cada leitura; conexão/leitura tem timeout de até 15 segundos (ou o restante
do prazo). `read1` devolve os bytes disponíveis sem esperar encher o bloco. O
Crawl-delay acima de 60 segundos recusa a coleta, sem reduzir a pausa pedida.
Não se aceita compressão HTTP; os arquivos ZIP seguem permitidos. O freio de
disco roda antes e durante o download. Limites:
256 MiB por arquivo/TXT descompactado, 256 KiB de robots e 32 KiB por linha.
Os dois arquivos são validados antes da publicação. Temporários são removidos
inclusive em erro; logs trazem só UF, resultado e classe do erro, nunca células.

## Fora do escopo

CADESP/SP, CCC/SVRS, consultas unitárias, captcha, login, ABRAS/APAS, nomes,
endereços e fontes novas. RS/MG ficam sem download operacional pelos motivos
acima. Não há contorno, URL alternativa presumida, carga real ou auto-merge.

## Verificação

Fixtures minúsculas geram CNPJs sintéticos na hora. Testes de leitores das três
UFs, TXT/ZIP, bloqueios, tipos, documento pessoal com zeros, versões, limpeza,
freio, HTTP e ligação federal ficam em `tests/test_sintegra_estadual.py` e
`tests/test_sintegra_http.py`. As suítes inteiras `tests/test_porta_sem_pessoa.py`
e `tests/test_montar_recorte_da_api.py` conferem a exclusão da porta e do envio.
