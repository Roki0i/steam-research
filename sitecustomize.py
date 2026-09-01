"""Runtime defaults for Colab/local Python execution."""

try:
    # Registers IPAexGothic with matplotlib before analysis scripts set font.family.
    import japanize_matplotlib  # noqa: F401
except Exception:
    # Analysis can still run even if the optional font package is unavailable.
    pass
