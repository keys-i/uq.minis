import json
from unittest.mock import Mock

import pytest

from uq_minis.core import cache
from uq_minis.core.common import MiniError


class TestCache:
    @pytest.mark.parametrize("state", ["fresh", "stale", "missing", "large", "symlink"])
    def test_snapshot(self, tmp_path, state):
        path = tmp_path / "snapshot.json"
        path.write_bytes(b"valid")
        if state == "stale":
            cache.os.utime(path, (1, 1))
        elif state == "missing":
            path.unlink()
        elif state == "large":
            path.write_bytes(b"x" * (cache.SNAPSHOT + 1))
        elif state == "symlink":
            target = tmp_path / "outside"
            path.replace(target)
            path.symlink_to(target)
            with pytest.raises(MiniError, match="symlink"):
                cache.read(path)
            return
        assert cache.read(path) == (b"valid" if state == "fresh" else None)
        assert cache.read(path, fresh=False) == (b"valid" if state in {"fresh", "stale"} else None)

    @pytest.mark.parametrize("budget", ["entries", "bytes"])
    def test_evict(self, cached, monkeypatch, budget):
        root, source, entry = cached
        if budget == "entries":
            monkeypatch.setattr(cache, "ENTRIES", 2)
        else:
            monkeypatch.setattr(
                cache, "LIMIT", 2 * sum(file.stat().st_size for file in entry.iterdir())
            )
        foreign = root / "extractor"
        foreign.mkdir()
        (foreign / "notes.txt").write_text("preserve")
        for number in range(1, 3):
            cache.save(root, f"{number:016x}-{'a' * 16}", source, {"file": source.name})
        assert len(list(cache.entries(root))) == 2
        assert not entry.exists()
        assert (foreign / "notes.txt").read_text() == "preserve"

    @pytest.mark.parametrize(
        "metadata",
        [
            {"file": "../../outside.bin"},
            {"file": "info.json"},
            {"bytes": True},
            {"bytes": 0},
            {"bytes": 100},
            [],
            "broken",
            "x" * 4097,
        ],
        ids=["traversal", "index", "bool", "empty", "size", "type", "json", "large"],
    )
    def test_metadata(self, cached, metadata):
        root, source, entry = cached
        index = entry / "info.json"
        if isinstance(metadata, dict):
            metadata = {**json.loads(index.read_text()), **metadata}
        index.write_text(metadata if isinstance(metadata, str) else json.dumps(metadata))
        assert not list(cache.entries(root))
        assert source.read_bytes() == b"completed"

    @pytest.mark.parametrize("part", ["root", "entry", "index", "file"])
    def test_symlink(self, cached, tmp_path, part):
        root, source, entry = cached
        if part == "root":
            linked = tmp_path / "linked"
            linked.symlink_to(root, target_is_directory=True)
            with pytest.raises(MiniError, match="symlink"):
                list(cache.entries(linked))
        elif part == "entry":
            linked = root / f"{'1' * 16}-{'a' * 16}"
            linked.symlink_to(entry, target_is_directory=True)
            assert len(list(cache.entries(root))) == 1
        else:
            path = entry / ("info.json" if part == "index" else source.name)
            data = path.read_bytes()
            outside = tmp_path / f"outside-{path.name}"
            outside.write_bytes(data)
            path.unlink()
            path.symlink_to(outside)
            assert not list(cache.entries(root))
            assert outside.read_bytes() == data

    @pytest.mark.parametrize("part", ["key", "file", "root", "entry"])
    def test_publish_refuse(self, cached, tmp_path, part):
        root, source, entry = cached
        key, filename = entry.name, source.name
        if part == "key":
            key = "../outside"
        elif part == "file":
            filename = "info.json"
        elif part == "root":
            linked = tmp_path / "linked"
            linked.symlink_to(root, target_is_directory=True)
            root = linked
        else:
            key = f"{'1' * 16}-{'a' * 16}"
            (root / key).symlink_to(entry, target_is_directory=True)
        before = {path.name: path.read_bytes() for path in entry.iterdir()}
        with pytest.raises(MiniError):
            cache.save(root, key, source, {"file": filename})
        assert {path.name: path.read_bytes() for path in entry.iterdir()} == before
        assert not list(root.glob(".cache-*"))

    @pytest.mark.parametrize("fallback", [False, True], ids=["link", "copy"])
    def test_reuse(self, cached, tmp_path, monkeypatch, fallback):
        root, source, entry = cached
        index = entry / "info.json"
        cache.os.utime(index, (1, 1))
        if fallback:
            monkeypatch.setattr(cache.os, "link", Mock(side_effect=OSError("different filesystem")))
        target = tmp_path / "result.bin"
        cache.reuse(next(cache.entries(root))[1], target)
        assert target.read_bytes() == source.read_bytes()
        assert index.stat().st_mtime > 1
        with pytest.raises(MiniError, match="already exists"):
            cache.copy(source, target)
        assert target.read_bytes() == b"completed"

    @pytest.mark.parametrize("outcome", ["success", "failure", "symlink"])
    def test_atomic(self, tmp_path, outcome):
        original = tmp_path / "original.bin"
        original.write_bytes(b"previous")
        target = tmp_path / "linked.bin" if outcome == "symlink" else original
        if outcome == "symlink":
            target.symlink_to(original)
            with pytest.raises(MiniError, match="symlink"):
                with cache.writing(target):
                    pytest.fail("must not write through a symlink")
        elif outcome == "failure":
            with pytest.raises(ValueError):
                with cache.writing(target) as temporary:
                    temporary.write_bytes(b"invalid")
                    raise ValueError("validation failed")
        else:
            with cache.writing(target) as temporary:
                temporary.write_bytes(b"completed")
        assert original.read_bytes() == (b"completed" if outcome == "success" else b"previous")
        assert not list(tmp_path.glob(".cache-*"))
