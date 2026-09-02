from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from xiami_core.models import XiamiMessage
from xiami_core.plugins.events import PluginEvent


MessageHandler = Callable[[XiamiMessage], None]
PluginEventHandler = Callable[[PluginEvent], None]


@dataclass
class EventBus:
    _message_handlers: list[MessageHandler]
    _plugin_event_handlers: list[PluginEventHandler]

    def __init__(self) -> None:
        self._message_handlers = []
        self._plugin_event_handlers = []

    def subscribe_message(self, handler: MessageHandler) -> None:
        if handler not in self._message_handlers:
            self._message_handlers.append(handler)

    def publish_message(self, message: XiamiMessage) -> None:
        for handler in list(self._message_handlers):
            handler(message)

    def subscribe_plugin_event(self, handler: PluginEventHandler) -> None:
        if handler not in self._plugin_event_handlers:
            self._plugin_event_handlers.append(handler)

    def publish_plugin_event(self, event: PluginEvent) -> None:
        for handler in list(self._plugin_event_handlers):
            handler(event)
