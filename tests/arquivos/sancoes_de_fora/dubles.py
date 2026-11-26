"""XML inventado das listas de sanção de fora, no formato conferido em 26/11/2026 (só a estrutura).

Nomes, pessoas, documentos e endereços são todos inventados. Cada lista mistura entidade, pessoa física,
navio, aeronave, registro sem tipo e registro que a fonte chama de entidade mas tem sinal de pessoa.
"""

PESSOAS = (
    "FULANA INVENTADA",
    "BELTRANO INVENTADO",
    "CICRANA SEM TIPO",
    "SICRANO COM NASCIMENTO",
    "SOLE PROPRIETOR INVENTADO",
)
NAO_SAI = (
    *PESSOAS,
    "NAVIO INVENTADO",
    "AERONAVE INVENTADA",
    "DOC-INVENTADO-123",
    "RUA INVENTADA 10",
    "OBSERVACAO COM NOME",
    "parente@exemplo.invalid",
    "1970",
)


def _ofac_entidade(
    id_: str,
    tipo: str | None,
    nome: str,
    listas: tuple[str, ...] = ("SDN List",),
    extra: str = "",
    apelidos: tuple[tuple[str, str], ...] = (),
) -> str:
    tipo_ = f"<entityType refId='1'>{tipo}</entityType>" if tipo else ""
    listas_ = "".join(
        f"<sanctionsList id='{n}' refId='2' datePublished='2022-03-0{n}'>{lista}</sanctionsList>"
        for n, lista in enumerate(listas, start=1)
    )
    nomes = "".join(
        f"""<name id='{n}'><isPrimary>{"true" if n == 0 else "false"}</isPrimary>
          <isLowQuality>{fraco}</isLowQuality><translations>
          <translation><isPrimary>true</isPrimary><formattedFullName>{texto}</formattedFullName></translation>
          <translation><isPrimary>false</isPrimary><formattedFullName>{texto} (outra escrita)</formattedFullName>
          </translation></translations></name>"""
        for n, (texto, fraco) in enumerate(((nome, "false"), *apelidos))
    )
    return f"""<entity id='{id_}'>
      <generalInfo><identityId>9</identityId>{tipo_}<remarks>OBSERVACAO COM NOME</remarks></generalInfo>
      <sanctionsLists>{listas_}</sanctionsLists>
      <sanctionsPrograms><sanctionsProgram id='1' refId='3'>PROGRAMA-A</sanctionsProgram></sanctionsPrograms>
      <names>{nomes}</names>
      <addresses><address id='1'><country refId='4'>Pais Inventado</country>
        <translations><translation><addressParts><addressPart><value>RUA INVENTADA 10</value></addressPart>
        </addressParts></translation></translations></address></addresses>
      <identityDocuments><identityDocument><documentNumber>DOC-INVENTADO-123</documentNumber>
      </identityDocument></identityDocuments>
      <relationships><relationship><relatedEntity entityId='7'>FULANA INVENTADA</relatedEntity></relationship>
      </relationships>{extra}</entity>"""


def ofac(*entidades: str) -> bytes:
    corpo = "".join(entidades)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sanctionsData xmlns="https://exemplo.invalid/ofac">
  <publicationInfo><dataAsOf>2026-11-26T00:00:00</dataAsOf></publicationInfo>
  <entities>{corpo}</entities></sanctionsData>""".encode()


EMPRESA_OFAC = _ofac_entidade(
    "100",
    "Entity",
    "EXEMPLO TRADING LLC",
    apelidos=(("EXEMPLO TRADE", "false"), ("APELIDO FRACO", "true")),
)
DUAS_LISTAS_OFAC = _ofac_entidade(
    "101",
    "Entity",
    "EXEMPLO BANK",
    listas=("SDN List", "Consolidated List", "Sectoral Sanctions Identifications List"),
)
PESSOAS_OFAC = (
    _ofac_entidade("200", "Individual", "FULANA INVENTADA"),
    _ofac_entidade("201", "Vessel", "NAVIO INVENTADO"),
    _ofac_entidade("202", "Aircraft", "AERONAVE INVENTADA"),
    _ofac_entidade("203", None, "CICRANA SEM TIPO"),
    _ofac_entidade(
        "204",
        "Entity",
        "SICRANO COM NASCIMENTO",
        extra="<features><feature><type featureTypeId='8'>Birthdate</type><value>1970</value></feature></features>",
    ),
    _ofac_entidade("205", "Entity", "SOLE PROPRIETOR INVENTADO"),
)


def sdn(*extras: str) -> bytes:
    return ofac(EMPRESA_OFAC, DUAS_LISTAS_OFAC, *extras, *PESSOAS_OFAC)


def consolidada() -> bytes:
    return ofac(
        _ofac_entidade(
            "101",
            "Entity",
            "EXEMPLO BANK",
            listas=(
                "SDN List",
                "Consolidated List",
                "Sectoral Sanctions Identifications List",
            ),
        ),
        _ofac_entidade(
            "300",
            "Entity",
            "EXEMPLO MINING",
            listas=("Consolidated List", "Non-SDN CMIC List"),
        ),
        *PESSOAS_OFAC,
    )


def _uk(
    id_: str, tipo: str | None, nomes: tuple[tuple[str, str], ...], extra: str = ""
) -> str:
    tipo_ = f"<IndividualEntityShip>{tipo}</IndividualEntityShip>" if tipo else ""
    nomes_ = "".join(
        f"<Name><Name6>{texto}</Name6><NameType>{papel}</NameType></Name>"
        for papel, texto in nomes
    )
    return f"""<Designation><LastUpdated>01/02/2026</LastUpdated><DateDesignated>15/03/2022</DateDesignated>
      <UniqueID>{id_}</UniqueID><Names>{nomes_}</Names><RegimeName>Regime Inventado</RegimeName>{tipo_}
      <OtherInformation>OBSERVACAO COM NOME</OtherInformation>
      <UKStatementofReasons>OBSERVACAO COM NOME</UKStatementofReasons>
      <Addresses><Address><AddressLine1>RUA INVENTADA 10</AddressLine1>
        <AddressCountry>Pais Inventado</AddressCountry></Address></Addresses>
      <EmailAddresses><EmailAddress>parente@exemplo.invalid</EmailAddress></EmailAddresses>{extra}</Designation>"""


EMPRESA_UK = _uk(
    "INV0001",
    "Entity",
    (("Alias", "EXEMPLO ENERGY"), ("Primary name", "EXEMPLO ENERGIA SA")),
)


def reino_unido(*extras: str) -> bytes:
    corpo = "".join(
        (
            EMPRESA_UK,
            *extras,
            _uk("INV0100", "Individual", (("Primary Name", "BELTRANO INVENTADO"),)),
            _uk("INV0101", "Ship", (("Primary Name", "NAVIO INVENTADO"),)),
            _uk("INV0102", None, (("Primary Name", "CICRANA SEM TIPO"),)),
            _uk(
                "INV0103",
                "Entity",
                (("Primary Name", "SICRANO COM NASCIMENTO"),),
                extra="<IndividualDetails><Individual><DOBs><DOB>1970</DOB></DOBs></Individual></IndividualDetails>",
            ),
            _uk("INV0104", "Entity", (("Primary Name", "SOLE PROPRIETOR INVENTADO"),)),
        )
    )
    return f"<?xml version='1.0' encoding='utf-8'?><Designations><DateGenerated>x</DateGenerated>{corpo}</Designations>".encode()


def uk_entidade(id_: str, nome: str) -> str:
    return _uk(id_, "Entity", (("Primary Name", nome),))


def _ue(
    id_: str,
    codigo: str | None,
    nomes: tuple[str, ...],
    extra: str = "",
    atributos: str = "",
    designado: str = "2022-04-08",
) -> str:
    tipo = f"<subjectType code='x' classificationCode='{codigo}'/>" if codigo else ""
    apelidos = "".join(
        f"<nameAlias wholeName='{n}' strong='true' logicalId='{i}' {atributos}/>"
        for i, n in enumerate(nomes)
    )
    return f"""<sanctionEntity logicalId='{id_}' designationDate='{designado}'>
      <remark>OBSERVACAO COM NOME</remark>
      <regulation programme='PRG' publicationDate='2022-04-09'/>{tipo}{apelidos}
      <nameAlias wholeName='APELIDO FRACO' strong='false'/>
      <address countryDescription='PAIS INVENTADO' street='RUA INVENTADA 10'/>
      <address countryDescription='UNKNOWN'/>
      <identification number='DOC-INVENTADO-123'/>{extra}</sanctionEntity>"""


def uniao_europeia() -> bytes:
    corpo = "".join(
        (
            _ue("1", "E", ("EXEMPLO CHEMICAL JSC", "EXEMPLO QUIMICA")),
            _ue("2", "E", ("EXEMPLO SEM DATA",), designado=""),
            _ue("100", "P", ("FULANA INVENTADA",)),
            _ue("101", None, ("CICRANA SEM TIPO",)),
            _ue(
                "102",
                "E",
                ("SICRANO COM NASCIMENTO",),
                extra="<birthdate year='1970'/>",
            ),
            _ue("103", "E", ("BELTRANO INVENTADO",), atributos="gender='M'"),
            _ue("104", "E", ("SOLE PROPRIETOR INVENTADO",)),
        )
    )
    return f"<?xml version='1.0' encoding='utf-8'?><export xmlns='https://exemplo.invalid/ue' generationDate='x'>{corpo}</export>".encode()
