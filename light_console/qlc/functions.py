from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QlcFunction:
    function_id: int
    name: str
    type: str = "Scene"
    running: bool = False
