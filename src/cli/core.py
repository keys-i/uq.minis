"""Core mini-management commands"""

from uq_minis.core import mini
from uq_minis.core.terminal import application

app = application()
app.command()(mini.add)
app.command("rm")(mini.remove)
app.command("list")(mini.list_minis)
