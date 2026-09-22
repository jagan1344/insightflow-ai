"""Short conversational memory."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List


@dataclass
class Turn:
    question: str
    action: str
    confidence: float


class Memory:
    def __init__(self, maxlen: int = 10):
        self._turns: Deque[Turn] = deque(maxlen=maxlen)

    def add(self, question: str, action: str, confidence: float) -> None:
        self._turns.append(Turn(question, action, confidence))

    def recent(self) -> List[Turn]:
        return list(self._turns)

    def clear(self) -> None:
        self._turns.clear()
