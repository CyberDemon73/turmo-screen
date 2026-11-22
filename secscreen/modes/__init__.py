from .clock import ClockMode
from .gif import GifMode
from .message import MessageMode
from .photo import PhotoMode
from .system import SystemMode
from .tasks import TasksMode
from .timer import StopwatchMode, TimerMode
from .tokens import TokensMode

MODE_CLASSES = [TokensMode, ClockMode, TasksMode, PhotoMode, GifMode, TimerMode, StopwatchMode, SystemMode,
                MessageMode]


def create_modes(settings):
    """Ordered {id: mode instance}."""
    return {cls.id: cls(settings) for cls in MODE_CLASSES}
