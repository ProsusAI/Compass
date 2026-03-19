"""Base agent interface."""

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Base class for all pipeline agents."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent identifier."""

    @abstractmethod
    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent's task.

        Args:
            context: Pipeline context with inputs and prior agent outputs.

        Returns:
            Dict of outputs to merge into the pipeline context.
        """
