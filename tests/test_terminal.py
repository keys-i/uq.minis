from types import SimpleNamespace

import pytest
from prompt_toolkit.data_structures import Point
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


@pytest.mark.parametrize("moving", [False, True], ids=["still", "animated"])
def test_motion(pipe, entry, cursor, monkeypatch, moving):
    monkeypatch.setenv("MINI_MOTION", "1" if moving else "0")
    monkeypatch.setattr(terminal.CONSOLE, "no_color", False)
    ask("Pick one", choices=("first",))
    options = entry.call_args.kwargs
    assert options["refresh_interval"] == (0.125 if moving else 0)
    options["pre_run"]()
    buffer, clock, app = cursor
    layout = app.layout.container.content.children[0]
    message = layout.children[0].content.text
    before = message()
    footer = layout.children[1].children[-1].content.text
    clock.return_value = 0.25
    assert before == message()
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
        assert "".join(text for _, text in first) != "".join(text for _, text in second)
        clock.return_value = 5
        assert "".join(text for _, text in message()) == terminal._look().picture().plain


@pytest.mark.parametrize("name", ["raccoon", "fox", "owl", "otter", "bee", "cat"])
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
            assert {cell_len(row) for row in frames[0].plain.splitlines()} == {26}
            for pose in art._poses(name):
                picture = look.picture(4, pose)
                assert len(picture.plain.splitlines()) == 12
                assert {cell_len(row) for row in picture.plain.splitlines()} == {26}
                assert picture.plain != frames[0].plain
            raise KeyboardInterrupt
        assert terminal._look() is original
        assert terminal.rich_utils.STYLE_OPTION == option
        assert console.get_style("accent") == accent
        rendered = Text.from_ansi(output.getvalue()).plain
        assert "A mini" in rendered
        assert all(cell_len(line) <= width for line in rendered.splitlines())


@pytest.mark.parametrize(
    "width,rows,no_color,art",
    [(80, 24, False, True), (40, 24, False, False), (80, 12, False, False), (80, 24, True, False)],
    ids=["wide", "narrow", "short", "monochrome"],
)
def test_layout(canvas, keys, width, rows, no_color, art):
    frames = canvas(width, rows, no_color)
    keys("\x1b[B", "\n")
    assert ask("Pick one", choices={"first": "First choice", "second": "Second choice"}) == "first"
    view = "\n".join(row for frame in frames for row in frame)
    assert "First choice" in view
    assert any("\u2800" <= char <= "\u28ff" for char in view) is art
    if art:
        assert all(not any(row.strip() for row in frame[12:]) for frame in frames)


def test_recent(canvas, keys):
    frames = canvas()
    keys("wrong\n", "first\n")
    assert ask("Pick one", choices=("first",)) == "first"
    keys("2\n")
    assert number("How many", default=1) == 2
    assert any("✓ › Pick one: first" in row for frame in frames for row in frame)
    assert all("wrong" not in answer for answer in terminal._RECENT.get())


@pytest.mark.parametrize(
    "point,pose", [(Point(8, 2), "ears"), (Point(12, 5), "pet"), (Point(12, 9), "object")]
)
def test_touch(pipe, entry, cursor, monkeypatch, point, pose):
    monkeypatch.setattr(terminal.CONSOLE, "no_color", False)
    monkeypatch.setenv("MINI_MOTION", "1")
    ask("Pick one", choices=("first",))
    entry.call_args.kwargs["pre_run"]()
    buffer, clock, app = cursor
    control = app.layout.container.content.children[0].children[0].content
    control.mouse_handler(
        MouseEvent(point, MouseEventType.MOUSE_MOVE, MouseButton.NONE, frozenset())
    )
    footer = app.layout.container.content.children[0].children[1].children[-1].content.text
    assert "click" in footer()[0][1]
    app.invalidate.reset_mock()
    control.mouse_handler(MouseEvent(point, MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset()))
    clock.return_value = 0.5
    assert "".join(text for _, text in control.text()) == terminal._look().picture(4, pose).plain
    app.invalidate.assert_called_once()
    buffer.text = "first"
    clock.return_value = 2
    control.text()
    control.mouse_handler(MouseEvent(point, MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset()))
    clock.return_value = 2.5
    assert "".join(text for _, text in control.text()) == terminal._look().picture(4, pose).plain
    clock.return_value = 4
    assert (
        "".join(text for _, text in control.text()) == terminal._look().picture(7, "listen").plain
    )


def test_mouse(canvas, keys):
    frames = canvas()
    keys("\x1b[<35;13;6M", "\x1b[<0;13;6m", "\x1b[B", "\n")
    assert ask("Pick one", choices=("first",)) == "first"
    assert any("body · click to pet" in row for frame in frames for row in frame)


@pytest.mark.parametrize("no_color", [False, True], ids=["picture", "text"])
def test_preview(canvas, keys, screen, no_color):
    frames = canvas(no_color=no_color)
    sample = art.image([[(200, 100, 50)] * 26] * 14, "Forest video · 01:23")
    keys("\x1b[B", "\n")
    assert ask("Video", choices={"link": "Forest video"}, previews={"link": sample}) == "link"
    assert any("▀" in row for frame in frames for row in frame) is not no_color


@pytest.mark.parametrize(
    "rows", [[], [[(0, 0, 0)] * 27], [[(0, 0, 0)]] * 20, [[(300, 0, 0)]], [[(0, 0, 0)], []]]
)
def test_pixels(rows):
    with pytest.raises(ValueError, match="26 × 18"):
        art.image(rows, "A picture")


@pytest.mark.parametrize(
    "prompt,options,input,expected",
    [(confirm, {"default": True}, "n\n", False), (number, {"default": 1}, "1.5\n", 1.5)],
    ids=["confirmation", "number"],
)
def test_input(pipe, keys, prompt, options, input, expected):
    keys(input)
    assert prompt("Choose", **options) == expected


@pytest.mark.parametrize(
    "width,live,no_color",
    [(28, False, False), (80, True, False), (40, True, True), (60, False, True)],
    ids=["narrow", "colour", "monochrome", "plain"],
)
def test_render(screen, width, live, no_color):
    console, output = screen(width=width, live=live, no_color=no_color)
    terminal.intro("[red]A mini[/red]", "Something nice to make")
    view = terminal.table("File", "Saved to")
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
