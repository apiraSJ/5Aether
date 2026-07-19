from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CommandResult:
    success: bool
    message: str
    data: Any = None


class Command(ABC):
    @abstractmethod
    def execute(self, **kwargs) -> CommandResult:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    def description(self) -> str:
        return ""
