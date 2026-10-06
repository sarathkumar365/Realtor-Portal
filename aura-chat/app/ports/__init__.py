"""Protocols only. No implementations, no I/O, no vendor imports.

The shared seams. Each capability declares its own ports beside its code
(app/capabilities/<name>/ports/); every port still needs a stated reason. A port
that will never gain a second adapter is cost with no return, so the HTTP
framework and the database driver are not ports.
"""

from .auth import AuthVerifier
from .projects import ProjectRepo

__all__ = ["AuthVerifier", "ProjectRepo"]
