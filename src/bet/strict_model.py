"""The project's strict Pydantic base, owned by no single pipeline.

``StrictBaseModel`` used to live in ``bet.pipeline.contracts.base``. Every
provider client reaches it through ``bet.models``, so importing a provider
pulled in ``bet/pipeline/__init__.py`` -- and with it the S0-S10 manifest
validator, which raises when the manifest's script paths move. A stale legacy
manifest could therefore stop the live pipeline from starting, which is exactly
backwards.

The class lives here so both stacks can depend on it without depending on each
other. ``bet.pipeline.contracts.base`` re-exports it, so existing imports keep
working.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    """Strict validation, frozen instances, no unknown fields."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )
