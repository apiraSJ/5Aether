import logging


class CameraView:
    def __init__(self, dashboard=None):
        self.logger = logging.getLogger("Aether.CameraView")
        self.dashboard = dashboard

    def update(self, frame):
        if self.dashboard:
            self.dashboard.update_frame(frame)

    def render(self):
        if self.dashboard:
            self.dashboard.render_frame()
