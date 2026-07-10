"""pypamc204 – PAMC-204 / PAMC-204-RJ ピエゾアシストモーターコントローラ用Pythonライブラリ"""

from .controller import PAMC204, CHANNEL_MAP, VOLTAGE_TABLE, find_port
from .exceptions import (
    PAMC204Error,
    BusyError,
    CommandError,
    ConnectionError,
    TimeoutError,
    ValueRangeError,
)

__version__ = "0.4.0"

__all__ = [
    "PAMC204",
    "find_port",
    "CHANNEL_MAP",
    "VOLTAGE_TABLE",
    "PAMC204Error",
    "BusyError",
    "CommandError",
    "ConnectionError",
    "TimeoutError",
    "ValueRangeError",
]
