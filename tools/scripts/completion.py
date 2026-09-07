"""Generate shell completion from uv and Typer"""

from pathlib import Path

import typer


def zsh_script() -> str:
    """Generate uv completion that delegates external commands to Typer"""
    import shlex
    import shutil
    import subprocess  # nosec B404
    from importlib.metadata import distribution

    from typer.completion import get_completion_script

    uv = shutil.which("uv")
    if uv is None:
        raise typer.BadParameter("uv must be installed to generate completion")
    script = subprocess.run(  # nosec B603
        [uv, "generate-shell-completion", "zsh"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # Delegate uv run's external arguments through zsh's command completer
    script = script.replace("external_command:_default", "external_command:_normal")
    scripts = ["autoload -Uz compinit; (( $+functions[compdef] )) || compinit -D", script]
    for entry in distribution("uq-minis").entry_points:
        if entry.group != "console_scripts":
            continue
        name = entry.name
        # The shell argument selects a template; it does not execute a shell
        native = get_completion_script(  # nosec B604
            prog_name=name, complete_var=f"_{name.upper().replace('-', '_')}_COMPLETE", shell="zsh"
        )
        native = native.replace(
            '"${words[1,$CURRENT]}"', '"${(j: :)${(@q)words[1,CURRENT]}}"'
        ).replace(f"complete_zsh {name})", f"complete_zsh uv run --no-sync {shlex.quote(name)})")
        scripts.append(native)
    return "\n".join(scripts)


def completion_callback(ctx, param, value):
    """Show or install generated completion for the current shell"""
    from typer.completion import _get_shell_name, install_callback, show_callback

    if not value or ctx.resilient_parsing:
        return value
    shell = value if isinstance(value, str) else _get_shell_name()
    if shell != "zsh":
        callback = install_callback if param.name == "install_completion" else show_callback
        return callback(ctx, param, value)
    script = zsh_script()
    if param.name == "show_completion":
        typer.echo(script)
    else:
        import shlex

        target = Path.home() / ".zfunc/uq-minis.zsh"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script + "\n", encoding="utf-8")
        rc = Path.home() / ".zshrc"
        content = rc.read_text(encoding="utf-8") if rc.exists() else ""
        line = f"source {shlex.quote(str(target))}"
        if line not in content.splitlines():
            with rc.open("a", encoding="utf-8") as handle:
                handle.write(f"\n{line}\n")
        typer.echo("Generated completion installed; restart your terminal to enable it")
    raise typer.Exit()
