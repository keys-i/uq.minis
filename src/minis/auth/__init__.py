"""Sign in through your browser and save Forms access for event submissions"""

from .browser import capture as capture
from .credentials import write_env as write_env

__all__ = ("capture", "write_env")
