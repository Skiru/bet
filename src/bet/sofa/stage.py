"""Which pipeline stage the current request belongs to.

The stage label used to be a literal inside each client method — ``entity_events``
always said "RESOLVE", every Superbet call always said "BOARD". That is a
property of the *caller*, not of the method: ``entity_events`` is called by
RESOLVE and by SAMPLES both, so 8.2% of SAMPLES' cost was filed under RESOLVE
and the question "what did this stage cost" had no answer (F22, F20).

It is a context variable rather than a parameter on every method because a
parameter is forgettable: the next method added with a hardcoded literal would
reintroduce the defect silently. The stage is set once, at the top of each
``run_*.py``, and every request underneath inherits it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# "CLIENT" means nobody declared a stage — a direct client call from a script
# or a REPL. It is deliberately not one of the pipeline stage names, so an
# unlabelled request is visible in the log rather than misfiled under a real one.
_CURRENT_STAGE: ContextVar[str] = ContextVar("sofa_stage", default="CLIENT")


def current_stage() -> str:
    """The stage the calling code declared, or "CLIENT" if it declared none."""
    return _CURRENT_STAGE.get()


def set_stage(name: str) -> None:
    """Declare the stage for the rest of this context. Used by ``run_*.py``."""
    _CURRENT_STAGE.set(name)


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Declare the stage for the duration of a block, then restore it."""
    token = _CURRENT_STAGE.set(name)
    try:
        yield
    finally:
        _CURRENT_STAGE.reset(token)
