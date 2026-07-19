import logging
from typing import List


class HandOverlay:
    def __init__(self):
        self.logger = logging.getLogger("Aether.HandOverlay")
        self._landmarks = None
        self._gesture = None
        self._menu_items = []

    def update(self, hand_results, gesture=None):
        self._gesture = gesture
        if hand_results and hand_results.hands:
            self._landmarks = hand_results.hands[0].landmarks
        else:
            self._landmarks = None

    def get_landmarks(self):
        return self._landmarks

    def get_gesture(self):
        return self._gesture

    def set_menu_items(self, items: list):
        self._menu_items = items

    def get_menu_items(self):
        return self._menu_items
