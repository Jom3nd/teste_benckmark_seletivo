from .model import Notification
class NotificationValidator:
    def validate(self,x:Notification):
        if x.id < 0 or not x.name.strip(): raise ValueError("invalid notification")
        return x
