from abc import ABC, abstractmethod


class BaseParser(ABC):
    @abstractmethod
    async def parse(self, file_path: str) -> list[dict]:
        """Return [{"text": str, "section": str}, ...]"""
        ...
