"""Unified calendar commands using the shared private student plan

Expose calendar views and exports over the same validated private plan
used by the browser, keeping official deadlines and personal targets distinct
"""

from uq_minis.cli.planny import calendar, show
from uq_minis.core.art import RESIDENTS
from uq_minis.core.terminal import application

app = application(theme=RESIDENTS["buzzy"], no_args_is_help=True)
app.command("calendar")(calendar)
app.command("show")(show)
