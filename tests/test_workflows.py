import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_workflows_pin_actions_and_isolate_dependabot_permissions():
    workflows = ROOT / ".github/workflows"
    for path in workflows.glob("*.yml"):
        text = path.read_text()
        data = yaml.safe_load(text)
        assert "permissions" in data and "concurrency" in data
        for job in data["jobs"].values():
            assert job["timeout-minutes"] <= 15
            for step in job.get("steps", []):
                if action := step.get("uses"):
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action
                    assert f"# SHA: {action.split('@')[1]}" in text.split("name:")[0]
                    if action.startswith("actions/checkout@"):
                        assert step["with"]["persist-credentials"] is False
    merge = yaml.safe_load((workflows / "dependabot.yml").read_text())
    assert merge["permissions"] == {}
    assert all(
        not step.get("uses", "").startswith("actions/checkout")
        for job in merge["jobs"].values()
        for step in job["steps"]
    )
    assert "> 80" in merge["jobs"]["auto-merge"]["if"]
    assert "--match-head-commit" in merge["jobs"]["auto-merge"]["steps"][0]["run"]
    assert {
        update["package-ecosystem"]
        for update in yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())["updates"]
    } == {"pip"}
