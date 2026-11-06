"""Os arquivos de workflow do GitHub Actions carregam como YAML e têm jobs com passos.

Um dois-pontos solto no nome de um passo ("vulture (código morto: não piorar)") derrubou o CI inteiro em
05/11/2026: o GitHub nem cria os jobs ("workflow file issue"), e nada no repositório conferia isso. O PyYAML
não é pin direto dos requirements (chega por outros pacotes): onde não houver, o teste é pulado.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

RAIZ = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((RAIZ / ".github" / "workflows").glob("*.yml"))


def test_ha_workflows() -> None:
    assert WORKFLOWS, "nenhum workflow em .github/workflows/"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda caminho: caminho.name)
def test_workflow_carrega_como_yaml_e_tem_jobs(workflow: Path) -> None:
    documento = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert isinstance(documento, dict), f"{workflow.name} não é um mapa YAML"
    assert documento.get("jobs"), f"{workflow.name} sem jobs"
    for nome, job in documento["jobs"].items():
        assert job.get("steps") or job.get("uses"), (
            f"job {nome} de {workflow.name} sem passos"
        )
