"""Tab completion for terminal prompts and CLI paths"""

import os
from collections.abc import Sequence
from pathlib import Path


def complete_path(incomplete: str) -> list[str]:
    """Complete path prefixes and append a separator to directories"""
    # Typer's zsh backend uses native file completion when no values are returned
    if os.getenv("_MINI_COMPLETE") == "complete_zsh":
        return []
    directory, prefix = os.path.split(incomplete)
    try:
        return [
            os.path.join(directory, path.name) + (os.sep if path.is_dir() else "")
            for path in sorted(Path(directory or ".").expanduser().iterdir())
            if path.name.startswith(prefix)
            and (prefix.startswith(".") or not path.name.startswith("."))
        ]
    except OSError:
        return []


def ask(message: str, *, choices: Sequence[str] = (), default: str = "") -> str:
    """Prompt with Tab completion and validate choices before returning"""
    from prompt_toolkit import prompt
    from prompt_toolkit.completion import PathCompleter, WordCompleter
    from prompt_toolkit.validation import Validator

    label = f"{message} ({'/'.join(choices)})" if choices else message
    value = prompt(
        [("ansicyan bold", f"{label}: ")],
        placeholder=default,
        completer=WordCompleter(choices, WORD=True) if choices else PathCompleter(expanduser=True),
        complete_while_typing=True,
        validator=Validator.from_callable(
            lambda value: (value or default) in choices if choices else bool(value or default),
            error_message="Choose one of the listed values." if choices else "Enter a path.",
        ),
    )
    return value or default
