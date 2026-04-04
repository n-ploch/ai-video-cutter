from __future__ import annotations

from pydantic import BaseModel


class TimelineEntry(BaseModel):
    index: int
    start_time: float
    end_time: float
    source_video: str = ""


class EditDecision(BaseModel):
    entry_index: int
    keep: bool = True
    note: str = ""


class Timeline(BaseModel):
    entries: list[TimelineEntry] = []
    decisions: list[EditDecision] = []
