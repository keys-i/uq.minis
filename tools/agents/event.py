"""Event tools with separate preview and submission entry points."""

from pathlib import Path
from typing import Literal

from uq_minis.helper.common import MiniError


def _result(result) -> dict[str, object]:
    return {
        "outputs": [{"kind": kind, "path": str(path.resolve())} for kind, path in result.outputs],
        "submissions": [
            {"source": str(path.resolve()), "status": status} for path, status in result.submissions
        ],
    }


def event_generate(
    source: Path,
    form: bool = True,
    risk: bool = True,
    layout: Literal["form", "pack", "both"] = "form",
    output: Path | None = None,
    force: bool = False,
    jobs: int = 0,
    form_profile: Path | None = None,
    logo: Path | None = None,
) -> dict[str, object]:
    """Generate form JSON and/or risk DOCX. Never submit, even if TOML requests submission.

    Source is an event TOML or directory. Return file paths; force permits overwrites.
    """
    from uq_minis.minis.event import generate

    if not form and not risk:
        raise MiniError("Select form, risk, or both")
    return _result(
        generate(
            source,
            mode="both" if form and risk else "form" if form else "risk",
            risk_layout=layout,
            destination=output,
            form_action="preview",
            force=force,
            jobs=jobs,
            form_profile=form_profile,
            logo=logo,
        )
    )


def event_submit(
    source: Path,
    output: Path | None = None,
    force: bool = False,
    form_profile: Path | None = None,
) -> dict[str, object]:
    """Submit an event TOML to Microsoft Forms using saved credentials.

    Only call when the user authorizes submission. Never retry an uncertain result:
    submission is not idempotent. Force permits replacing existing generated JSON.
    """
    from uq_minis.minis.event import generate

    return _result(
        generate(
            source,
            mode="form",
            destination=output,
            form_action="submit",
            form_profile=form_profile,
            force=force,
        )
    )
