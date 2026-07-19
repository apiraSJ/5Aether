import logging


class Sidebar:
    def __init__(self):
        self.logger = logging.getLogger("Aether.Sidebar")
        self._current_section = "dashboard"

    def set_section(self, section: str):
        self._current_section = section

    def get_section(self) -> str:
        return self._current_section
