from __future__ import annotations

from enum import StrEnum


class PaginationModel(StrEnum):
    NO_PAGINATION = "NO_PAGINATION"
    PAGE_NUMBER = "PAGE_NUMBER"
    CURSOR = "CURSOR"
    DATE_WINDOW = "DATE_WINDOW"
    SEASON_SCOPE = "SEASON_SCOPE"
    FILE_TREE = "FILE_TREE"
    UNKNOWN = "UNKNOWN"


class PaginationState:
    def __init__(
        self,
        model: PaginationModel = PaginationModel.NO_PAGINATION,
        current_page: int = 1,
        cursor_value: str | None = None,
    ):
        self.model = model
        self.current_page = current_page
        self.cursor_value = cursor_value
