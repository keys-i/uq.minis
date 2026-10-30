"""Sign in through your browser and save Forms access for event submissions

The public capture and private-file writer support Forms submission access
The in-site UQ portal check is separate and does not retain those credentials
or establish an Outlook connection
"""

from .browser import capture as capture
from .credentials import write_env as write_env

__all__ = ("capture", "write_env")
