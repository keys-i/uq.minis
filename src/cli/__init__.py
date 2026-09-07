"""Run a tool with --tool NAME, or manage minis with add, rm and list"""

import importlib
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from typer.core import TyperCommand
from typer.main import get_command
from typer.models import CompletionItem, TyperPath

from uq_minis.helper.prompt import ask, complete_path

CONSOLE = Console()
app = typer.Typer(rich_markup_mode="rich", pretty_exceptions_show_locals=False)


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
    """Complete mini management command names"""
    from uq_minis_tools.scripts.mini import app as manage

    return [name for name in get_command(manage).commands if name.startswith(incomplete)]


class MiniCommand(TyperCommand):
    """Typer dispatcher with completion for the selected mini"""

    def get_params(self, ctx):
        """Use generated shell setup for the built-in completion options"""
        from uq_minis_tools.scripts.completion import completion_callback

        params = super().get_params(ctx)
        for param in params:
            if param.name in {"show_completion", "install_completion"}:
                param.callback = completion_callback
        return params

    def make_context(self, info_name, args, parent=None, **extra):
        """Parse normally and expose the selected app during shell completion"""
        ctx = super().make_context(info_name, args, parent=parent, **extra)
        if ctx.resilient_parsing:
            tool = ctx.params.get("tool")
            forwarded = list(ctx.params.get("arguments") or [])
            if tool in tool_names():
                target = importlib.import_module(f"uq_minis.minis.{tool.replace('-', '_')}").app
            elif tool is None and forwarded and forwarded[0] in command_names():
                from uq_minis_tools.scripts.mini import app as target
            else:
                return ctx
            # Let Typer complete the selected command without executing its callback.
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
            "--tool", help="Tool to run; use mini list to see all.", autocompletion=tool_names
        ),
    ] = None,
    arguments: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="[COMMAND/ARGS]...",
            help="add NAME, rm NAME, list, or arguments for --tool.",
            autocompletion=command_names,
        ),
    ] = None,
    help_: Annotated[
        bool, typer.Option("--help", "-h", help="Show help for mini or the selected tool.")
    ] = False,
) -> None:
    """Run a mini or manage its source module"""
    arguments = arguments or []
    if help_ and tool is None:
        typer.echo(ctx.get_help())
        return
    if tool is None and arguments:
        from uq_minis_tools.scripts.mini import main as manage

        manage(arguments)
        return
    names = tool_names()
    if tool is None:
        view = Table(
            "Tool",
            "Run",
            title="UQ minis",
            header_style="bold magenta",
            border_style="bright_black",
        )
        for name in names:
            view.add_row(name, f"uv run mini --tool {name} --help", style="cyan")
        CONSOLE.print(view)
        if not names or not sys.stdin.isatty():
            return
        tool = ask("Choose a tool", choices=names)
    if tool not in names:
        raise typer.BadParameter(f"unknown tool: {tool}", param_hint="--tool")
    # Forward help to the selected tool instead of consuming it in this dispatcher.
    module = importlib.import_module(f"uq_minis.minis.{tool.replace('-', '_')}")
    module.main([*arguments, *(["--help"] if help_ else [])])


def main(argv: list[str] | None = None) -> None:
    """Run the mini CLI"""
    app(args=argv, prog_name="mini")


if __name__ == "__main__":
    main()
