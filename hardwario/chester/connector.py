from rttt.connectors import Middleware
from rttt.event import Event, EventType


class ChesterLogMiddleware(Middleware):
    """Route CHESTER's '#'-prefixed terminal lines to the log pane.

    Older CHESTER firmware has no separate RTT logger buffer and prefixes its
    log lines with '#' on the terminal buffer instead. Without this they show
    up as shell output.

    This is the one behaviour rttt's PyLinkRTTConnector does not cover, and it
    is a pure event rewrite, so it composes as a middleware rather than
    needing a connector of its own.
    """

    def _on(self, event: Event):
        if event.type == EventType.OUT and event.data.startswith('#'):
            event = Event(EventType.LOG, event.data)
        super()._on(event)
