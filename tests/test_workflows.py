import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["checks", "security", "release"])
def test_runtime(name: str) -> None:
    version = (ROOT / ".python-version").read_text().strip()
    workflow = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text())
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("astral-sh/setup-uv@"):
                assert step["with"]["python-version"] == version


@pytest.mark.parametrize("case", ["valid", "wrong-tag", "missing-notes"])
def test_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    project = (ROOT / "pyproject.toml").read_text()
    version = tomllib.loads(project)["project"]["version"]
    tag = f"v{version}"
    (tmp_path / "pyproject.toml").write_text(project)
    heading = tag if case != "missing-notes" else "v0.0.0"
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {heading}\n\nCurrent changes\n\n## v0.0.1\n\nOlder changes\n"
    )
    monkeypatch.setenv("RELEASE_TAG", tag if case != "wrong-tag" else "v999.0.0")
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    step = next(
        step
        for step in workflow["jobs"]["release"]["steps"]
        if "RELEASE_TAG" in step.get("env", {})
    )
    source = step["run"].split("\n", 1)[1].rsplit("\nPY", 1)[0]
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if case == "valid" else 1), result.stderr
    notes = tmp_path / ".cache/release.md"
    if case == "valid":
        assert notes.read_text() == "Current changes\n"
    else:
        assert not notes.exists()


def test_actions() -> None:
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
