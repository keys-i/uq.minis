"""Core mini-management commands

Register source-management operations and start the loopback browser app
Optional browser dependencies are loaded only when that command is invoked
"""

from pathlib import Path

from uq_minis.core import mini
from uq_minis.core.terminal import application

app = application()
app.command()(mini.add)
app.command("rm")(mini.remove)
app.command("list")(mini.list_minis)


@app.command()
def browser(port: int = 8765, frontend: Path | None = None) -> None:
    """Open the shared browser backend for every mini"""
    from uq_minis.core.common import MiniError
    from uq_minis.core.terminal import CONSOLE

    try:
        from uq_minis.web import run

        if not 1024 <= port <= 65535:
            import typer

            raise typer.BadParameter("Choose a port between 1024 and 65535")
        CONSOLE.print(f"Your minis are ready at http://127.0.0.1:{port}", markup=False)
        run(port, frontend)
    except ImportError as exc:
        raise MiniError("Install browser support with uv sync --extra browser") from exc
