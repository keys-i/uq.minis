import pytest
from rich.cells import cell_len
from rich.text import Text

from uq_minis.core import terminal
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
