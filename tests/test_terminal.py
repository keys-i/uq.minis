from types import SimpleNamespace

import pytest
from prompt_toolkit.completion import Completion
from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.menus import CompletionsMenuControl
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.styles import merge_styles
from prompt_toolkit.styles.defaults import default_ui_style
from rich.cells import cell_len
from rich.text import Text

from uq_minis.core import art, terminal
from uq_minis.core.terminal import application, ask, confirm, number


@pytest.mark.parametrize(
    "prompt,options,input,expected",
    [
        (ask, {"required": True}, "\nvalue\n", "value"),
        (ask, {"choices": ("chosen",)}, "wrong\nchosen\n", "chosen"),
        (ask, {}, "\n", ""),
        (confirm, {"default": True}, "n\n", False),
        (number, {"default": 1.0}, "bad\n1.5\n", 1.5),
    ],
    ids=["required", "choice", "optional", "confirmation", "number"],
)
def test_prompts(prompt, options, input, expected, runner):
    app = application()
    answers = []

    @app.command()
    def run():
        answers.append(prompt("Prompt", **options))

    result = runner.invoke(app, [], input=input)
    assert result.exit_code == 0, result.output
    assert answers == [expected]


@pytest.mark.parametrize(
    "keys_,default,expected",
    [
        (("\x1b[B", "\n"), "", "first"),
        (("\x1b[B", "\x1b[B", "\n"), "", "second"),
        (("\x1b[A", "\n"), "", "second"),
        (("sec", "\t", "\n"), "", "second"),
        (("\n",), "first", "first"),
    ],
    ids=["down", "next", "up", "filter", "default"],
)
def test_choices(pipe, keys, keys_, default, expected):
    keys(*keys_)
    assert (
        ask(
            "Pick one",
            choices={"first": "First choice", "second": "Second choice"},
            default=default,
        )
        == expected
    )


def test_cancel(pipe, keys):
    keys("\x03")
    with pytest.raises(KeyboardInterrupt):
        ask("Pick one", choices=("first", "second"))


@pytest.mark.parametrize("key", ["\x1b", "\x1b[1;3D"], ids=["escape", "alt-left"])
def test_back(canvas, keys, key):
    frames = canvas()
    keys(key)
    with terminal.habitat("quoll"), pytest.raises(terminal.Back):
        ask("Video", required=True)
    assert any("← menu" in row for frame in frames for row in frame)
    assert terminal._RECENT.get() == ()


@pytest.mark.parametrize("width", [40, 80], ids=["compact", "wide"])
def test_shortcuts(canvas, keys, width):
    frames = canvas(width=width)
    keys("?", "?", "done\n")
    assert ask("Name") == "done"
    assert any(terminal._key("Ctrl+U") in row for frame in frames for row in frame)
    assert any("keys" in row for frame in frames for row in frame)


@pytest.mark.parametrize(
    "os,ctrl,alt", [("darwin", "⌃", "⌥"), ("win32", "Ctrl+", "Alt+"), ("linux", "Ctrl+", "Alt+")]
)
def test_os(canvas, keys, monkeypatch, os, ctrl, alt):
    monkeypatch.setattr(terminal, "sys", SimpleNamespace(platform=os))
    frames = canvas()
    keys("?", "?", "done\n")
    assert ask("Name") == "done"
    view = "\n".join(row for frame in frames for row in frame)
    assert ctrl + "U" in view
    assert alt + "M" in view


@pytest.mark.parametrize("moving", [False, True])
def test_marquee(pipe, entry, cursor, monkeypatch, moving):
    monkeypatch.setenv("MINI_MOTION", "1" if moving else "0")
    monkeypatch.setattr(terminal.CONSOLE, "no_color", False)
    buffer, clock, app = cursor
    first = "first · " + "a long description " * 4
    buffer.complete_state.completions = [
        Completion("first", display=first),
        Completion("second", display="second · another long description"),
    ]
    buffer.complete_state.current_completion = buffer.complete_state.completions[0]
    app.layout = Layout(Window(CompletionsMenuControl()))
    ask("Name", choices={"first": first, "second": "Second"})
    entry.call_args.kwargs["pre_run"]()
    panel = app.layout.container.content.children[0].children[1]
    menu = panel.children[2].content

    def line(width):
        return "".join(part[1] for part in menu.create_content(width, 2).get_line(0))

    before = line(24)
    clock.return_value = 2
    assert (line(24) != before) is moving
    assert buffer.complete_state.current_completion.text == "first"
    assert cell_len(line(18)) == 18
    footer = panel.children[-1].content.text
    assert "a long description" not in "".join(part[1] for part in footer())
    buffer.complete_state.complete_index = 1
    buffer.complete_state.current_completion = buffer.complete_state.completions[1]
    assert "second" in "".join(part[1] for part in menu.create_content(24, 2).get_line(1))


@pytest.mark.parametrize(
    "text",
    ["a long caption to scroll", "很長的標題需要捲動顯示更多文字", "Café déjà vu · a long caption"],
)
def test_caption(text):
    frames = [terminal._marquee(text, 8, elapsed) for elapsed in (0, 0.5, 1, 2, 3)]
    assert all(cell_len(frame) == 8 for frame in frames)
    assert frames[0] == frames[1]
    assert len(set(frames)) > 1


@pytest.mark.parametrize("width", [40, 80])
def test_scroll(canvas, keys, width):
    frames = canvas(width=width)
    keys("\x1b[B", "\n", interval=3.2)
    label = "ABCDEFGHIJKLMNOPQRSTUVWXYZ · " + "Long description " * 6
    assert ask("Name", choices={"first": label, "second": "Short label"}) == "first"
    selected = {row[row.index("ABC") :] for frame in frames for row in frame if "ABC" in row}
    assert len(selected) > 1
    assert any(
        "FGHIJKLMNOPQRSTUVWXYZ" in row and "ABC" not in row for frame in frames for row in frame
    )


@pytest.mark.parametrize("name", list(art._habitats()))
@pytest.mark.parametrize("moving", [False, True])
def test_pokes(pipe, entry, cursor, monkeypatch, name, moving):
    monkeypatch.setattr(terminal.CONSOLE, "no_color", False)
    monkeypatch.setenv("MINI_MOTION", "1" if moving else "0")
    with terminal.habitat(name):
        look = terminal._look()
        ask("Name")
        entry.call_args.kwargs["pre_run"]()
        _, clock, app = cursor
        control = app.layout.container.content.children[0].children[0].content
        x, y = next(
            (x + 2, y)
            for y, row in enumerate(look.hit.splitlines())
            for x, region in enumerate(row)
            if region == "2"
        )
        click = MouseEvent(Point(x, y), MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset())
        for count in range(4):
            control.mouse_handler(click)
            view = "".join(text for _, text in control.text())
            assert any(" ".join(line.split()[:4]) in view for line in look.quip.split("|")) is (
                count > 2
            )
        clock.return_value = 5
        view = "".join(text for _, text in control.text())
        assert not any(" ".join(line.split()[:4]) in view for line in look.quip.split("|"))
        assert app.refresh_interval == (1 / 16 if moving else 0)


@pytest.mark.parametrize("name", list(art._habitats()))
def test_regions(name):
    look = art._habitats()[name]
    for pose, frames in art._poses(name).items():
        for index in (0, len(frames) // 2):
            rows = frames[index]["hit"].splitlines()
            assert len(rows) == 16
            assert {len(row) for row in rows} == {40}
            targets = {
                look.region(index, pose, x + 2, y)
                for y, row in enumerate(rows)
                for x in range(len(row))
            }
            assert targets == {None, "ears", "pet", "object"}
    assert look.region(0, "idle", -1, 0) is None
    assert look.region(0, "idle", 0, -1) is None
    assert look.region(0, "idle", 44, 16) is None


def test_pause(canvas, keys, monkeypatch):
    frames = canvas()
    monkeypatch.setattr(terminal, "_STILL", False)
    keys("\x1bm", "first\n")
    assert ask("Name") == "first"
    assert terminal._STILL
    assert any("play" in row for frame in frames for row in frame)
    keys("\x1bm", "second\n")
    assert ask("Name") == "second"
    assert not terminal._STILL


def test_complete(canvas, keys):
    frames = canvas()
    keys("\x00", "\x1b[B", "\n")
    assert ask("Name", suggestions=("first", "second")) == "first"
    assert any("second" in row for frame in frames for row in frame)


@pytest.mark.parametrize("no_color", [False, True], ids=["colour", "monochrome"])
def test_focus(pipe, entry, monkeypatch, no_color):
    monkeypatch.setattr(terminal.CONSOLE, "no_color", no_color)
    assert ask("Pick one", choices=("first",)) == "first"
    styles = merge_styles([default_ui_style(), entry.call_args.kwargs["style"]])
    focus = styles.get_attrs_for_style_str("class:completion-menu.completion.current")
    assert focus.reverse is no_color
    if not no_color:
        assert focus.bgcolor == terminal._look().primary.lstrip("#")
        assert focus.color == terminal.COLOURS["ink"].lstrip("#")


@pytest.mark.parametrize("name", list(art._habitats()))
@pytest.mark.parametrize("moving", [False, True])
def test_palette(pipe, entry, cursor, monkeypatch, name, moving):
    monkeypatch.setattr(terminal.CONSOLE, "no_color", False)
    monkeypatch.setenv("MINI_MOTION", "1" if moving else "0")
    buffer, clock, app = cursor
    buffer.complete_state.completions = [
        Completion(value) for value in ("first", "second", "third")
    ]
    app.layout = Layout(Window(CompletionsMenuControl()))
    with terminal.habitat(name):
        ask("Name", choices=("first", "second", "third"))
        entry.call_args.kwargs["pre_run"]()
        styles = entry.call_args.kwargs["style"]
        colours = {
            styles.get_attrs_for_style_str(f"class:{field}").color
            for field in ("animal", "status", "country", "place")
        }
        assert len(colours) == 4
        assert (
            styles.get_attrs_for_style_str("class:row0").bgcolor
            != styles.get_attrs_for_style_str("class:row1").bgcolor
        )
        layout = app.layout.container.content.children[0]
        portrait = "".join(text for _, text in layout.children[0].content.text())
        assert all(
            value in portrait
            for value in (
                terminal._look().name,
                terminal._look().status,
                terminal._look().country,
                terminal._look().place,
            )
        )
        menu = layout.children[1].children[2].content.create_content(30, 3)
        assert "class:row1" in menu.get_line(1)[0][0]
        assert "class:row0" in menu.get_line(2)[0][0]
        assert "class:row" not in menu.get_line(0)[0][0]
        labels = [
            part for part in layout.children[0].content.text() if part[0].startswith("class:")
        ]
        clock.return_value = 4
        changed = [
            part for part in layout.children[0].content.text() if part[0].startswith("class:")
        ]
        assert (labels != changed) is moving


@pytest.mark.parametrize("moving", [False, True], ids=["still", "animated"])
def test_motion(pipe, entry, cursor, monkeypatch, moving):
    monkeypatch.setenv("MINI_MOTION", "1" if moving else "0")
    monkeypatch.setattr(terminal.CONSOLE, "no_color", False)
    ask("Pick one", choices=("first",))
    options = entry.call_args.kwargs
    assert options["refresh_interval"] == (1 / 16 if moving else 0)
    options["pre_run"]()
    buffer, clock, app = cursor
    layout = app.layout.container.content.children[0]
    message = layout.children[0].content.text
    before = message()
    footer = layout.children[1].children[-1].content.text
    clock.return_value = 0.25
    assert (before != message()) is moving
    buffer.text = "first"
    assert "enter" in footer()[0][1]
    buffer.complete_state.current_completion = SimpleNamespace(text="first")
    assert "enter to choose" in footer()[0][1]
    assert footer()[0][0] == "class:chosen"
    assert app.erase_when_done
    if moving:
        message()
        clock.return_value = 0.75
        assert "".join(text for _, text in message()) != terminal._look().picture().plain
        buffer.text = ""
        buffer.complete_state.current_completion = None
        clock.return_value = 3
        first = message()
        clock.return_value = 3.5
        second = message()
        assert first != second
        clock.return_value = 5
        assert len("".join(text for _, text in message()).splitlines()) == 20


@pytest.mark.parametrize("name", list(art._habitats()))
def test_routines(name):
    look = art._habitats()[name]
    other = set().union(
        *(set(pet.idle.split()[:4]) for pet in art._habitats().values() if pet != look)
    )
    for routine in look.idle.split()[:4]:
        assert routine not in other
        frames = art._poses(name)[routine]
        assert look.seconds(routine) >= 2
        assert len({frame["art"] for frame in frames}) > 8
        assert look.picture(0, routine).plain == look.picture().plain
        assert look.picture(len(frames) - 1, routine).plain == look.picture().plain


def test_interrupt(pipe, entry, cursor, monkeypatch):
    monkeypatch.setattr(terminal.CONSOLE, "no_color", False)
    monkeypatch.setattr(terminal.random, "choice", lambda values: "wander")
    ask("Name")
    entry.call_args.kwargs["pre_run"]()
    buffer, clock, app = cursor
    control = app.layout.container.content.children[0].children[0].content
    clock.return_value = 3
    control.text()
    clock.return_value = 5
    assert "".join(text for _, text in control.text()).startswith(
        terminal._look().picture(16, "wander").plain
    )
    buffer.text = "hello"
    control.text()
    clock.return_value = 5.5
    assert "".join(text for _, text in control.text()).startswith(
        terminal._look().picture(4, "listen").plain
    )


def test_button(pipe, entry, cursor):
    with terminal.habitat("quoll"):
        ask("Name")
        entry.call_args.kwargs["pre_run"]()
        _, _, app = cursor
        footer = app.layout.container.content.children[0].children[1].children[1].content.text
        fragment = next(part for part in footer() if "← menu" in part[1])
        for event, style in (
            (MouseEventType.MOUSE_MOVE, "hot"),
            (MouseEventType.MOUSE_DOWN, "pressed"),
        ):
            fragment[2](MouseEvent(Point(0, 0), event, MouseButton.LEFT, frozenset()))
            assert next(part for part in footer() if "← menu" in part[1])[0] == f"class:{style}"
        fragment[2](MouseEvent(Point(0, 0), MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset()))
        assert isinstance(app.exit.call_args.kwargs["exception"], terminal.Back)


@pytest.mark.parametrize("name", list(art._habitats()))
def test_habitat(screen, name):
    original = terminal._look()
    option = terminal.rich_utils.STYLE_OPTION
    for width in (28, 80):
        console, output = screen(width=width, live=True)
        accent = console.get_style("accent")
        with pytest.raises(KeyboardInterrupt), terminal.habitat(name):
            look = terminal._look()
            terminal.intro("A mini", "Something useful to make")
            assert console.get_style("accent").color.get_truecolor().hex == look.primary
            frames = [look.picture(frame) for frame in range(24)]
            assert len({frame.plain for frame in frames}) == 1
            assert {cell_len(row) for row in frames[0].plain.splitlines()} == {42}
            for pose in art._poses(name):
                picture = look.picture(4, pose)
                assert len(picture.plain.splitlines()) == 16
                assert {cell_len(row) for row in picture.plain.splitlines()} == {42}
                assert picture != frames[0]
            raise KeyboardInterrupt
        assert terminal._look() is original
        assert terminal.rich_utils.STYLE_OPTION == option
        assert console.get_style("accent") == accent
        rendered = Text.from_ansi(output.getvalue()).plain
        assert "A mini" in rendered
        assert all(cell_len(line) <= width for line in rendered.splitlines())


@pytest.mark.parametrize(
    "width,rows,no_color,art",
    [
        (80, 24, False, True),
        (40, 24, False, False),
        (80, 12, False, False),
        (80, 24, True, False),
    ],
    ids=["wide", "narrow", "short", "monochrome"],
)
def test_layout(canvas, keys, width, rows, no_color, art):
    frames = canvas(width, rows, no_color)
    keys("\x1b[B", "\n")
    assert ask("Pick one", choices={"first": "First choice", "second": "Second choice"}) == "first"
    view = "\n".join(row for frame in frames for row in frame)
    assert "First choice" in view
    assert "Window too small" not in view
    assert any("\u2800" <= char <= "\u28ff" for char in view) is art
    if art:
        assert all(not any(row.strip() for row in frame[22:]) for frame in frames)


def test_recent(canvas, keys):
    frames = canvas()
    keys("wrong\n", "first\n")
    assert ask("Pick one", choices=("first",)) == "first"
    keys("2\n")
    assert number("How many", default=1) == 2
    assert any("✓ › Pick one: first" in row for frame in frames for row in frame)
    assert all("wrong" not in answer for answer in terminal._RECENT.get())


@pytest.mark.parametrize("region", ["ears", "pet", "object"])
def test_touch(pipe, entry, cursor, monkeypatch, region):
    monkeypatch.setattr(terminal.CONSOLE, "no_color", False)
    monkeypatch.setenv("MINI_MOTION", "1")
    monkeypatch.setattr(terminal.random, "uniform", lambda *args: 100)
    ask("Pick one", choices=("first",))
    entry.call_args.kwargs["pre_run"]()
    buffer, clock, app = cursor
    control = app.layout.container.content.children[0].children[0].content
    look = terminal._look()
    target = {"ears": "1", "pet": "2", "object": "3"}[region]
    x, y = next(
        (x + 2, y)
        for y, row in enumerate(look.hit.splitlines())
        for x, value in enumerate(row)
        if value == target
    )
    point = Point(x, y)
    control.mouse_handler(
        MouseEvent(point, MouseEventType.MOUSE_MOVE, MouseButton.NONE, frozenset())
    )
    footer = app.layout.container.content.children[0].children[1].children[-1].content.text
    assert "click" in footer()[0][1]
    app.invalidate.reset_mock()
    poses = getattr(
        look, {"ears": "head_moves", "pet": "body_moves", "object": "object_moves"}[region]
    ).split()
    for index, pose in enumerate(poses):
        clock.return_value = index * 10
        control.text()
        # Click the drawn resting frame so the hit target follows the animation
        frame = int(clock.return_value * 8) % 16
        rows = art._poses(look.animal)["breathe"][frame]["hit"].splitlines()
        x, y = next(
            (x + 2, y)
            for y, row in enumerate(rows)
            for x, value in enumerate(row)
            if value == target
        )
        control.mouse_handler(
            MouseEvent(Point(x, y), MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset())
        )
        clock.return_value += 0.5
        assert "".join(text for _, text in control.text()).startswith(look.picture(4, pose).plain)
    buffer.text = "first"
    clock.return_value = 30
    control.text()
    clock.return_value = 31.5
    assert "".join(text for _, text in control.text()).startswith(
        terminal._look().picture(7, "listen").plain
    )


def test_mouse(canvas, keys):
    frames = canvas()
    keys("\x1b[<35;25;13M", "\x1b[<0;25;13m", "\x1b[B", "\n")
    assert ask("Pick one", choices=("first",)) == "first"
    assert any("back · click to scratch" in row for frame in frames for row in frame)


@pytest.mark.parametrize("no_color", [False, True], ids=["picture", "text"])
def test_preview(canvas, keys, screen, no_color):
    frames = canvas(no_color=no_color)
    sample = art.image([[(200, 100, 50)] * 26] * 14, "Forest video · 01:23")
    keys("\x1b[B", "\n")
    assert ask("Video", choices={"link": "Forest video"}, previews={"link": sample}) == "link"
    assert any("▀" in row for frame in frames for row in frame) is not no_color


@pytest.mark.parametrize(
    "rows",
    [[], [[(0, 0, 0)] * 41], [[(0, 0, 0)]] * 34, [[(300, 0, 0)]], [[(0, 0, 0)], []]],
)
def test_pixels(rows):
    with pytest.raises(ValueError, match="40 × 32"):
        art.image(rows, "A picture")


@pytest.mark.parametrize(
    "prompt,options,input,expected",
    [
        (confirm, {"default": True}, "n\n", False),
        (number, {"default": 1}, "1.5\n", 1.5),
    ],
    ids=["confirmation", "number"],
)
def test_input(pipe, keys, prompt, options, input, expected):
    keys(input)
    assert prompt("Choose", **options) == expected


@pytest.mark.parametrize(
    "arguments,input,expected",
    [
        (["--name", "two words"], ("edit\n", "'broken\n", "--name fixed\n"), ["--name", "fixed"]),
        (["--upload", "--yes"], ("edit\n", "\n"), ["--upload"]),
        (["--submit"], ("edit\n", "\n", "n\n"), None),
    ],
    ids=["arguments", "upload-review", "submission-cancel"],
)
def test_recovery(pipe, keys, arguments, input, expected):
    with terminal.habitat("numbat"):
        keys(*input)
        if expected is None:
            with pytest.raises(terminal.Back):
                terminal.recover(ValueError("Check the source"), arguments)
        else:
            assert terminal.recover(ValueError("Check the source"), arguments) == expected


@pytest.mark.parametrize(
    "width,live,no_color",
    [(28, False, False), (80, True, False), (40, True, True), (60, False, True)],
    ids=["narrow", "colour", "monochrome", "plain"],
)
def test_render(screen, width, live, no_color):
    console, output = screen(width=width, live=live, no_color=no_color)
    terminal.intro("[red]A mini[/red]", "Something nice to make")
    view = terminal.table("File", "Saved to")
    assert view.row_styles == [terminal._look().primary, terminal._look().secondary]
    path = "folder[rose]/a-long-file.docx"
    view.add_row(Text("event"), Text(path))
    console.print(view)
    rendered = Text.from_ansi(output.getvalue()).plain
    assert "[red]A mini[/red]" in rendered
    assert "folder[rose]" in rendered
    assert all(cell_len(line) <= width for line in rendered.splitlines())
    if no_color:
        assert "\x1b[38;" not in output.getvalue()


@pytest.mark.parametrize("live", [False, True], ids=["plain", "terminal"])
def test_progress(screen, live):
    _, output = screen(live=live)
    with terminal.activity("Reading the video") as update:
        update(None, "Reading the video · checking metadata")
        update(0.5, "Downloading background · 5 MiB / 10 MiB")
        update(None, "Stitching the background")
    rendered = Text.from_ansi(output.getvalue()).plain
    assert "Stitching" in rendered
    assert "0%" not in rendered.split("50%")[0]
    assert "50%" not in rendered.rsplit("Stitching", 1)[-1]
    if not live:
        assert "50%" in rendered
