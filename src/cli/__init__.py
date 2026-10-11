"""Run a tool with --tool NAME, or manage minis with add, rm and list"""

import ast
import importlib
import random
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.text import Text
from typer._click.exceptions import ClickException
from typer.core import TyperCommand
from typer.main import get_command
from typer.models import CompletionItem, TyperPath

from uq_minis.cli.core import app as manage
from uq_minis.core.art import _habitats
from uq_minis.core.common import MiniError
from uq_minis.core.terminal import (
    CONSOLE,
    Back,
    application,
    ask,
    complete_path,
    habitat,
    intro,
    problem,
    recover,
    table,
)

app = application(add_completion=True)


def get_app(name: str) -> typer.Typer:
    """Load a mini's registered commands or wrap its plain run function"""
    module_name = name.replace("-", "_")
    if (
        module_name not in {"core", "completion", "__init__", "__main__"}
        and Path(__file__).with_name(f"{module_name}.py").is_file()
    ):
        return importlib.import_module(f"uq_minis.cli.{module_name}").app
    module = importlib.import_module(f"uq_minis.minis.{module_name}")
    run = getattr(module, "run", None)
    if not callable(run):
        raise MiniError(f"{name} must export a run function")
    target = application()
    target.command()(run)
    return target


def tool_names(incomplete: str = "") -> list[str]:
    """List source minis whose names match the given prefix"""
    return [
        path.parent.name.replace("_", "-")
        for path in sorted((Path(__file__).resolve().parents[1] / "minis").glob("*/__init__.py"))
        if path.parent.name.isidentifier()
        and not path.parent.name.startswith("_")
        and path.parent.name.replace("_", "-").startswith(incomplete)
    ]


def command_names(incomplete: str = "") -> list[str]:
    """Complete management commands and direct mini names"""
    names = [*get_command(manage).commands, *tool_names()]
    return [name for name in names if name.startswith(incomplete)]


class MiniCommand(TyperCommand):
    """Typer dispatcher with completion for the selected mini"""

    def get_params(self, ctx):
        """Use generated shell setup for the built-in completion options"""
        from uq_minis.cli.completion import completion_callback

        params = super().get_params(ctx)
        for param in params:
            if param.name in {"show_completion", "install_completion"}:
                param.callback = completion_callback
        return params

    def make_context(self, info_name, args, parent=None, **extra):
        """Parse normally and expose the selected app during shell completion"""
        ctx = super().make_context(info_name, args, parent=parent, **extra)
        if ctx.resilient_parsing:
            names = tool_names()
            tool = ctx.params.get("tool")
            forwarded = list(ctx.params.get("arguments") or [])
            if tool in names:
                target = get_app(tool)
            elif tool is None and forwarded and forwarded[0] in get_command(manage).commands:
                target = manage
            elif tool is None and forwarded and forwarded[0] in names:
                target = get_app(forwarded.pop(0))
            else:
                return ctx
            # Let Typer complete the selected command without executing its callback
            command = get_command(target)
            for param in command.params:
                if isinstance(param.type, TyperPath) and param._custom_shell_complete is None:
                    param._custom_shell_complete = lambda ctx, param, value: [
                        CompletionItem(path) for path in complete_path(value)
                    ]
            return command.make_context(info_name, forwarded, parent=parent, **extra)
        return ctx


@app.command(
    cls=MiniCommand,
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
        "help_option_names": [],
    },
)
def dispatch(
    ctx: typer.Context,
    tool: Annotated[
        str | None,
        typer.Option(
            "--tool",
            help="Tool to run; use mini list to see all.",
            autocompletion=tool_names,
        ),
    ] = None,
    arguments: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="[COMMAND/ARGS]...",
            help="MINI [ARGS], add NAME, rm NAME, list, or arguments for --tool.",
            autocompletion=command_names,
        ),
    ] = None,
    help_: Annotated[
        bool,
        typer.Option("--help", "-h", help="Show help for mini or the selected tool."),
    ] = False,
) -> None:
    """Run MINI [ARGS], or manage minis with add, rm and list"""
    arguments = arguments or []
    names = tool_names()
    if tool is None and arguments:
        command, *forwarded = arguments
        if command in get_command(manage).commands or command not in names:
            manage(args=arguments, prog_name="mini")
            return
        tool, arguments = command, forwarded
    if help_ and tool is None:
        typer.echo(ctx.get_help())
        return
    while True:
        if tool is not None:
            if tool not in names:
                raise typer.BadParameter(f"unknown tool: {tool}", param_hint="--tool")
            try:
                target = get_app(tool)
                with habitat(getattr(target, "habitat", "numbat")):
                    while True:
                        try:
                            code = target(
                                args=[*arguments, *(["--help"] if help_ else [])],
                                prog_name=f"mini {tool}",
                                standalone_mode=False,
                            )
                            if isinstance(code, int) and code:
                                raise typer.Exit(code)
                            break
                        except (MiniError, OSError, ClickException) as exc:
                            if not sys.stdin.isatty() or "--no-input" in arguments:
                                problem(exc)
                                raise typer.Exit(2) from exc
                            arguments = recover(exc, arguments)
                return
            except Back:
                tool, arguments, help_ = None, [], False
            except (MiniError, OSError) as exc:
                problem(exc)
                raise typer.Exit(2) from exc
        intro("UQ minis", "Choose a tool")
        choices = {}
        for name in names:
            source = Path(__file__).resolve().parents[1] / "minis" / name.replace("-", "_")
            about = ast.get_docstring(ast.parse((source / "__init__.py").read_text()))
            choices[name] = (about or "Open this mini").splitlines()[0]
        if not names or not sys.stdin.isatty():
            view = table("Mini", "What it does")
            for name, about in choices.items():
                view.add_row(Text(name), Text(about))
            CONSOLE.print(view)
            CONSOLE.print("mini NAME --help for options", style="muted")
            return
        try:
            animals = list(_habitats().values())
            weights = [
                6 if pet.status == "extinct" else 4 if pet.status.startswith("critically") else 2
                for pet in animals
            ]
            visitor = random.choices(animals, weights=weights)[0]
            with habitat(visitor.animal, menu=False):
                tool = ask("Pick a mini", choices=choices, show_choices=False)
        except EOFError, KeyboardInterrupt:
            return


def main(argv: list[str] | None = None) -> None:
    """Run the mini CLI"""
    app(args=argv, prog_name="mini")


if __name__ == "__main__":
    main()
