"""Os textos que a tela da sala mostra (B-20, PR 5): a tela não escreve nem calcula nada.

Tudo aqui vai para a pessoa pela API da sala, que só abre para quem está logado, então nenhuma frase daqui chega ao bundle público do app. Cada conceito da sala é
explicado uma vez, aqui; os rótulos dos estados também, para a tela não repetir a lista.
"""

from datetime import date

from src.sala import retencao

TIPOS_DE_OPERACAO = {
    "ma": "Fusão e aquisição (M&A)",
    "divida": "Dívida",
    "credito": "Crédito",
    "fidc": "FIDC",
}

ESTADOS_DO_DOCUMENTO = {
    "na_fila": "Na fila para leitura",
    "lido": "Lido",
    "sem_texto": "Sem texto (escaneado ou só imagem)",
    "erro_na_leitura": "Não foi possível ler",
}

ESTADOS_DO_ITEM = {
    "pendente": "Pendente",
    "recebido": "Recebido (há um documento ligado)",
    "revisado": "Revisado por você",
    "contestado": "Contestado",
    "nao_se_aplica": "Não se aplica",
}

ESTADOS_DA_CONTRADICAO = {
    "aberta": "Aberta",
    "explicada": "Explicada",
    "descartada": "Descartada",
}

CONCEITOS = {
    "sala": (
        "A sala reúne os documentos de uma operação (M&A, dívida, crédito, FIDC) num lugar só. "
        "Cada arquivo fica cifrado no servidor e só a sua conta o abre; nem outras contas, "
        "administradores incluídos, veem a sua sala."
    ),
    "evidencia": (
        "Uma evidência marca de onde vem um número: o documento, a página e o trecho. O "
        "TickerLab confere por código se o trecho está mesmo na página; se não achar, a "
        'evidência aparece como "não conferida".'
    ),
    "contradicao": (
        "Contradição é quando dois documentos diferentes dizem valores diferentes para a mesma "
        "coisa (mesma métrica, período, unidade e moeda) e a diferença passa de 0,5% ou de 1 "
        "unidade. É uma regra fixa, sem modelo de linguagem: serve para você olhar, não para "
        'decidir por você. Marque como "explicada" ou "descartada" e escreva por quê.'
    ),
    "checklist": (
        'O checklist lista o que um analista costuma pedir nesse tipo de operação. "Recebido" '
        'só quer dizer que há um documento ligado ao item; "revisado" é sempre você quem marca.'
    ),
    "prazo": (
        "Toda operação some sozinha no prazo que você escolheu (90, 180 ou 365 dias; o padrão é "
        "180). No fim do prazo o TickerLab apaga os documentos, o texto lido, as evidências e a "
        "chave da operação, sem lixeira. Depois de apagado, só resta o backup da sala, que dura "
        "no máximo 14 dias. Encerrar a operação deixa 30 dias para baixar a sala."
    ),
    "baixar": (
        '"Baixar a sala" entrega um arquivo ZIP com todos os documentos, decifrados na hora. '
        "Guarde-o você mesmo: é a sua cópia antes do prazo acabar."
    ),
    "dados_de_terceiros": (
        "Os documentos podem ter dados de outras pessoas (sócios, devedores). Você decide o que "
        "sobe e responde por isso; o TickerLab só guarda e apaga no prazo, como dizem os termos de uso."
    ),
}


def aviso_de_prazo(situacao: str, retencao_ate: date, hoje: date) -> str | None:
    """A frase de aviso quando faltam 14 dias ou menos para a operação sumir; senão, nada."""
    dias = retencao.dias_ate_sumir(retencao_ate, hoje)
    if dias > retencao.DIAS_DO_AVISO_DE_PRAZO:
        return None
    quando = "hoje" if dias == 0 else "amanhã" if dias == 1 else f"em {dias} dias"
    complemento = " Baixe a sala antes disso ou prorrogue o prazo."
    if situacao == "encerrada":
        return f"Esta operação encerrada some {quando}.{complemento}"
    return f"Esta operação some {quando}.{complemento}"
