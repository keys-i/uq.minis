"""Run the central mini command line

Delegate module execution to the shared dispatcher so python -m uq_minis.cli
and the installed mini command use identical argument and error handling
"""

from uq_minis.cli import main

main()
