"""Save event details as an editable TOML before generating documents

Normalise reviewed event fields and validate the resulting configuration
before publishing its source. Document generation consumes that saved source
in a separate step, preserving an editable record of the person’s choices
"""

import json
import tomllib
from pathlib import Path
from typing import Any

from uq_minis.core.common import MiniError, table


def save(path: Path, raw: dict[str, Any]) -> None:
    """Validate event details and create their editable UTF-8 TOML source

    Check the event schema and generated TOML before creating directories
    Preserve nested tables, Unicode text and date/time values as readable input
    An existing destination raises ``FileExistsError`` and is never overwritten
    Schema errors or a non-TOML filename raise ``MiniError`` before writing
    """
    from uq_minis.core.risk_docx import load_event_config

    path = path.expanduser()
    if path.suffix.casefold() != ".toml":
        raise MiniError("Save the event to a .toml file")
    load_event_config(path, data=raw)
    sections = [("", raw)]
    blocks: list[str] = []
    for name, values in sections:
        lines: list[str] = []
        for key, value in values.items():
            if isinstance(value, dict):
                sections.append((
                    f"{name + '.' if name else ''}{json.dumps(key)}",
                    dict(table(values, key)),
                ))
            else:
                lines.append(
                    f"{json.dumps(key)} = {json.dumps(value, ensure_ascii=False, default=str)}"
                )
        if lines:
            blocks.append((f"[{name}]\n" if name else "") + "\n".join(lines))
    content = "\n\n".join(blocks) + "\n"
    tomllib.loads(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)
