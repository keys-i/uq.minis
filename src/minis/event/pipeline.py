"""Event output pipeline."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)

from uq_minis.helper.common import (
    FORM_ACTIONS,
    OUTPUT_MODES,
    RISK_LAYOUTS,
    FormAction,
    MiniError,
    OutputMode,
    RiskLayout,
    atomic_docx,
    atomic_json,
    choose,
    discover_events,
    ensure_outputs,
    output_directory,
    read_toml,
    table,
    text,
)
from uq_minis.helper.prompt import ask

if TYPE_CHECKING:
    from uq_minis.helper.forms import FormProfile
    from uq_minis.helper.risk_docx import EventConfig

CONSOLE = Console()


@dataclass(frozen=True, slots=True)
class Plan:
    """Validated inputs and output paths for one event"""

    source: Path
    config: EventConfig
    mode: OutputMode
    risk_outputs: tuple[tuple[RiskLayout, Path], ...]
    form_output: Path | None
    form_payload: dict[str, Any] | None
    form_profile: FormProfile | None
    form_action: FormAction | None


@dataclass(frozen=True, slots=True)
class RunResult:
    """Written files and HTTP statuses from completed submissions"""

    outputs: tuple[tuple[str, Path], ...]
    submissions: tuple[tuple[Path, int], ...]


def _configured(
    raw: dict[str, Any], section: str, key: str, allowed: tuple[Any, ...]
) -> Any | None:
    """Read and validate an optional TOML choice"""
    return choose(table(raw, section).get(key), field=f"[{section}].{key}", allowed=allowed)


def _resolve_values(
    sources: list[Path],
    raws: list[dict[str, Any]],
    explicit: str | None,
    *,
    section: str,
    key: str,
    allowed: tuple[Any, ...],
    interactive: bool,
    prompt: str,
) -> list[str]:
    """Use CLI overrides, then TOML values, then a prompt for missing choices"""
    if explicit:
        return [explicit] * len(sources)
    configured = [_configured(raw, section, key, allowed) for raw in raws]
    if all(value is not None for value in configured):
        return [cast(str, value) for value in configured]
    if not interactive:
        missing = ", ".join(
            str(path) for path, value in zip(sources, configured, strict=True) if value is None
        )
        option = f"--{key.replace('_', '-')}"
        raise MiniError(f"Set [{section}].{key} or pass {option} for: {missing}")
    selected = ask(prompt, choices=allowed, default=allowed[0])
    return [cast(str, value or selected) for value in configured]


def resolve_modes(
    sources: list[Path],
    raws: list[dict[str, Any]],
    explicit: OutputMode | None,
    *,
    interactive: bool,
) -> list[OutputMode]:
    """Choose which outputs to generate for each event"""
    return cast(
        list[OutputMode],
        _resolve_values(
            sources,
            raws,
            explicit,
            section="output",
            key="mode",
            allowed=OUTPUT_MODES,
            interactive=interactive,
            prompt="Generate",
        ),
    )


def resolve_risk_layouts(
    sources: list[Path],
    raws: list[dict[str, Any]],
    modes: list[OutputMode],
    explicit: RiskLayout | None,
    *,
    interactive: bool,
) -> list[RiskLayout | None]:
    """Choose document layouts for events that need a risk assessment"""
    indexes = [index for index, mode in enumerate(modes) if mode in {"risk", "both"}]
    if not indexes:
        return [None] * len(sources)
    selected = _resolve_values(
        [sources[index] for index in indexes],
        [raws[index] for index in indexes],
        explicit,
        section="output",
        key="risk_layout",
        allowed=RISK_LAYOUTS,
        interactive=interactive,
        prompt="Risk document",
    )
    result: list[RiskLayout | None] = [None] * len(sources)
    for index, value in zip(indexes, selected, strict=True):
        result[index] = cast(RiskLayout, value)
    return result


def resolve_form_actions(
    sources: list[Path],
    raws: list[dict[str, Any]],
    modes: list[OutputMode],
    explicit: FormAction | None,
) -> list[FormAction | None]:
    """Choose preview or submission for each event with form output"""
    result: list[FormAction | None] = []
    for source, raw, mode in zip(sources, raws, modes, strict=True):
        if mode not in {"form", "both"}:
            result.append(None)
            continue
        configured = _configured(raw, "form", "action", FORM_ACTIONS)
        action = explicit or configured or "preview"
        if action not in FORM_ACTIONS:
            raise MiniError(f"Invalid form action for {source}: {action}")
        result.append(cast(FormAction, action))
    return result


def risk_paths(
    config: EventConfig, destination: Path, layout: RiskLayout
) -> tuple[tuple[RiskLayout, Path], ...]:
    """Return document paths for the requested risk layout"""
    form = (cast(RiskLayout, "form"), destination / f"{config.output_name}.docx")
    pack = (cast(RiskLayout, "pack"), destination / f"{config.output_name}-pack.docx")
    return {"form": (form,), "pack": (pack,), "both": (form, pack)}[layout]


def _profile_path(source: Path, raw: dict[str, Any], explicit: Path | None) -> Path | None:
    """Resolve the CLI profile or a profile relative to the event file"""
    if explicit is not None:
        return explicit.expanduser().resolve(strict=False)
    configured = text(table(raw, "form").get("profile"), field="[form].profile")
    if not configured:
        return None
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else source.parent / path).resolve(strict=False)


def make_plans(
    input_path: Path,
    *,
    mode: OutputMode | None,
    risk_layout: RiskLayout | None,
    destination: Path | None,
    logo: Path | None,
    form_profile: Path | None,
    form_action: FormAction | None,
    interactive: bool,
) -> list[Plan]:
    """Validate event data and collect outputs before writing files"""
    from uq_minis.helper.risk_docx import load_event_config

    sources = discover_events(input_path)
    raws = [read_toml(source) for source in sources]
    modes = resolve_modes(sources, raws, mode, interactive=interactive)
    layouts = resolve_risk_layouts(sources, raws, modes, risk_layout, interactive=interactive)
    actions = resolve_form_actions(sources, raws, modes, form_action)
    target = output_directory(input_path, destination)
    profiles: dict[Path | None, FormProfile] = {}
    plans: list[Plan] = []

    for source, raw, selected_mode, layout, action in zip(
        sources, raws, modes, layouts, actions, strict=True
    ):
        config = load_event_config(source, logo)
        risk_outputs = () if layout is None else risk_paths(config, target, layout)
        payload = None
        profile = None
        form_output = None
        if selected_mode in {"form", "both"}:
            from uq_minis.helper.forms import create_payload, load_form_profile

            profile_key = _profile_path(source, raw, form_profile)
            profile = profiles.get(profile_key)
            if profile is None:
                profile = load_form_profile(profile_key)
                profiles[profile_key] = profile
            payload = create_payload(raw, config, profile)
            form_output = target / f"{config.output_name}.form.json"
        plans.append(
            Plan(
                source,
                config,
                selected_mode,
                risk_outputs,
                form_output,
                payload,
                profile,
                action,
            )
        )
    return plans


def _write_risk(config: EventConfig, layout: RiskLayout, output: Path) -> Path:
    """Build and atomically save one risk document"""
    from uq_minis.helper.risk_docx import build_form_document, build_pack_document

    document = build_pack_document(config) if layout == "pack" else build_form_document(config)
    atomic_docx(output, document)
    return output


def _workers(requested: int, count: int) -> int:
    """Limit the worker count to the number of documents"""
    if requested < 0:
        raise MiniError("--jobs must be zero or positive")
    if count < 2:
        return count
    return min(count, requested or min(4, os.cpu_count() or 1))


def generate(
    input_path: Path,
    *,
    mode: OutputMode | None = None,
    risk_layout: RiskLayout | None = None,
    destination: Path | None = None,
    logo: Path | None = None,
    form_profile: Path | None = None,
    form_action: FormAction | None = None,
    force: bool = False,
    jobs: int = 0,
    interactive: bool = False,
    show_progress: bool = False,
) -> RunResult:
    """Write event outputs and submit forms when requested"""
    if jobs < 0:
        raise MiniError("--jobs must be zero or positive")
    plans = make_plans(
        input_path,
        mode=mode,
        risk_layout=risk_layout,
        destination=destination,
        logo=logo,
        form_profile=form_profile,
        form_action=form_action,
        interactive=interactive,
    )
    outputs = [
        path
        for plan in plans
        for path in (
            *((plan.form_output,) if plan.form_output else ()),
            *(output for _, output in plan.risk_outputs),
        )
    ]
    ensure_outputs(outputs, force=force)

    completed: list[tuple[str, Path]] = []
    risk_jobs = [
        (plan.config, layout, output) for plan in plans for layout, output in plan.risk_outputs
    ]
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=CONSOLE,
        transient=CONSOLE.is_terminal,
        disable=not show_progress,
    ) as progress:
        task = progress.add_task("Generating", total=len(outputs))
        for plan in plans:
            if plan.form_output is not None and plan.form_payload is not None:
                atomic_json(plan.form_output, plan.form_payload, private=True)
                completed.append(("form", plan.form_output))
                progress.advance(task)

        worker_count = _workers(jobs, len(risk_jobs))
        if worker_count == 1:
            for config, layout, output in risk_jobs:
                _write_risk(config, layout, output)
                completed.append((f"risk-{layout}", output))
                progress.advance(task)
        elif worker_count > 1:
            with ProcessPoolExecutor(max_workers=worker_count) as pool:
                futures = {
                    pool.submit(_write_risk, config, layout, output): (layout, output)
                    for config, layout, output in risk_jobs
                }
                for future in as_completed(futures):
                    layout, output = futures[future]
                    future.result()
                    completed.append((f"risk-{layout}", output))
                    progress.advance(task)

    submissions: list[tuple[Path, int]] = []
    submit_plans = [plan for plan in plans if plan.form_action == "submit"]
    if submit_plans:
        from uq_minis.helper.forms import submit_payload

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold magenta]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=CONSOLE,
            transient=CONSOLE.is_terminal,
            disable=not show_progress,
        ) as progress:
            task = progress.add_task("Submitting", total=len(submit_plans))
            for plan in submit_plans:
                status = submit_payload(
                    cast("FormProfile", plan.form_profile),
                    cast(dict[str, Any], plan.form_payload),
                )
                submissions.append((plan.source, status))
                progress.advance(task)

    return RunResult(tuple(sorted(completed, key=lambda item: str(item[1]))), tuple(submissions))
