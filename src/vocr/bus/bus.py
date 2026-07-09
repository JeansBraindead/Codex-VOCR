from __future__ import annotations

from vocr.memory.ledger import MemoryLedger
from vocr.models import BusMessage, LedgerEventType


class MessageBus:
    def __init__(self, ledger: MemoryLedger) -> None:
        self.ledger = ledger

    def publish(self, channel: str, sender: str, body: str) -> BusMessage:
        message = BusMessage(channel=channel, sender=sender, body=body)
        self.ledger.append(LedgerEventType.message, message)
        return message

    def messages(self, channel: str | None = None) -> list[BusMessage]:
        messages: list[BusMessage] = []
        for event in self.ledger.events():
            if event.type == LedgerEventType.message:
                message = BusMessage.model_validate(event.payload)
                if channel is None or message.channel == channel:
                    messages.append(message)
        return messages
