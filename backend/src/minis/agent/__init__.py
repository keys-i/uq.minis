"""Watch Outlook for booking replies and follow your event's registration progress

Expose the persistent worker’s public mailbox operations without duplicating
their implementation. CLI options belong in cli.agent; importing this
package does not connect to a mailbox or start a watcher
"""

lazy from uq_minis.worker.event import DEFAULT_STATE, login, poll, retry_send, status, stop, watch

__all__ = ("DEFAULT_STATE", "login", "poll", "retry_send", "status", "stop", "watch")
