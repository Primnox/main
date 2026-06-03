# extensions/base.py

from abc import ABC, abstractmethod

class BaseExtension(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, *args, **kwargs):
        """Execute the extension's main function."""
        pass
