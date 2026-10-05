"""Protocols only. No implementations, no I/O, no vendor imports.

Five seams, deliberately. A port that will never gain a second adapter is cost
with no return, so the HTTP framework and the database driver are not ports.
"""

from .auth import AuthVerifier
from .projects import ProjectRepo
from .conversations import ConversationStore
from .documents import DocumentIndex
from .runtime import AgentRuntime

__all__ = [
    "AuthVerifier",
    "ProjectRepo",
    "ConversationStore",
    "DocumentIndex",
    "AgentRuntime",
]
