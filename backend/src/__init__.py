"""UQ event forms and risk assessments

The installed distribution owns the version number
Feature packages are imported only when their CLI or browser workflow needs them
"""


def __getattr__(name: str) -> str:
    """Read the installed version only when requested, keeping runtime imports light"""
    if name == "__version__":
        from importlib.metadata import version

        value = version("uq-minis")
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
