"""Sign in to Microsoft Forms"""

from .browser import capture
from .credentials import write_env

__all__ = ("capture", "write_env")
