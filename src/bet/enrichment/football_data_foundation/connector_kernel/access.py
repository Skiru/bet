from __future__ import annotations

import importlib.util
from collections.abc import Mapping


class AccessRequirement:
    def __init__(self, key_name: str, required: bool = True, description: str = ""):
        self.key_name = key_name
        self.required = required
        self.description = description

    def verify(self, environment_vars: Mapping[str, str]) -> bool:
        if self.required:
            return self.key_name in environment_vars and bool(
                environment_vars[self.key_name]
            )
        return True


def has_dependency(package_name: str) -> bool:
    return importlib.util.find_spec(package_name) is not None
