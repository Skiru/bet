"""Canonical bet package."""

__version__ = "1.0.0"
__all__ = ["builder", "models", "pipeline"]


def __getattr__(name: str):
    if name in __all__:
        import importlib
        return importlib.import_module(f"bet.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
