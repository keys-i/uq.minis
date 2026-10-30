import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
import uvicorn

from uq_minis import app, web
from uq_minis.core.common import MiniError


def test_activation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "a" * 64
    (tmp_path / "identity").write_text(
        json.dumps({"account": "person@uq.edu.au", "secret": secret})
    )
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setenv("MINIS_ORIGIN", "")
    create, run = Mock(return_value="application"), Mock()
    monkeypatch.setattr(app, "create", create)
    monkeypatch.setattr(uvicorn, "run", run)
    web.run()
    assert create.call_args.kwargs["delegate"] == ("person@uq.edu.au", secret)
    assert run.call_args.args == ("application",)
    assert run.call_args.kwargs["fd"] == 3
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    with pytest.raises(MiniError, match="port"):
        web.run(80)
    assert run.call_count == 1
