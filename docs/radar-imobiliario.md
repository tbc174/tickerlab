# Radar imobiliário (piloto)

A página `/radar-imobiliario`, em Acompanhar, consome `/api/v1/radar-imobiliario` com a sessão já usada pelo app. Filtra município (SP/RIO) e uso (todos/residencial); o mês é escolhido na tela. Não consulta as prefeituras durante a navegação.

O pacote de dados é externo ao repositório público. Para instalar uma versão agregada previamente preparada:

```text
python -m scripts.importar_radar_imobiliario caminho/do/pacote.json
```

O destino padrão é `dados_locais/radar_imobiliario.json`; `TICKERLAB_RADAR_IMOBILIARIO` permite um caminho montado no contêiner. A origem deve conter `versao: 1`, `apurado_em`, `mensais` e `regioes`, conforme `src/radar_imobiliario.py`. O instalador valida o pacote inteiro e substitui o anterior atomicamente. Pacote ausente, incompatível ou maior que 5 MB devolve 503, sem números de exemplo. Não embarcar microdados, SQL fiscal, matrícula ou endereço de imóvel.

## Interpretação

- SP: DTIs pagas de compra e venda por mês de pagamento, não imóveis únicos nem data de registro. Exclui rurais e ITBI pago pelo PPI, conforme a fonte.
- Rio: tabela 5 de ITBI, com operações agregadas de compra e promessa de compra e venda por competência da fonte, de imóveis residenciais e não residenciais. Imóveis territoriais da tabela 6 ficam fora deste piloto. Médias ponderadas pelo número de operações, não média simples dos grupos.
- Valores declarados nominais incluem transmissões parciais e mudanças de composição. Não são preços de anúncio, índice de valorização, mediana nem preço por m².
- SP usa **distrito oficial**: cruzar setor/quadra do cadastro fiscal com a geometria completa de todas as partes da quadra no GeoSampa; aceitar somente cobertura integral por um único distrito. Quadra ausente ou atravessando um limite permanece sem localização. A malha consultada é atual, sem inferir limites históricos.
- Rio usa **bairro** da fonte. Os dois níveis não são equivalentes. A tela mostra quantas operações receberam localização; a lista regional não substitui o total municipal.
- O campo livre de bairro em SP não é completado por aproximação de nome, CEP ou setor. No piloto, uma recuperação auxiliar por SQL exato resolveu poucos vazios; ela não foi usada para produzir um ranking incompleto de bairros.
- As séries são uma apuração retrospectiva, sujeita a revisão; não servem como dados disponíveis em cada data de um backtest.

## Fontes e atualização

- [Fazenda de São Paulo — ITBI](https://prefeitura.sp.gov.br/fazenda/w/acesso_a_informacao/31501).
- [Fazenda/IPP do Rio — tabela 5](https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Fazenda/ITBI/MapServer/5).
- [GeoSampa — serviços e referência cartográfica](https://geoinfo-smdu.github.io/tutorial-GeoSampa/).

A apuração inicial cobre janeiro/2025 a agosto/2026. Atualização é uma nova extração, reconciliação de totais e instalação do agregado; não foi criado agendamento nesta entrega. Antes de distribuir um novo pacote em produção, registrar as condições de uso das fontes no inventário de dados. Acesso público não é um registro de licença por si só.
