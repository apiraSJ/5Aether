"""Echo provider — thin re-export of the canonical EchoProvider.

Keeps the ``aether.ai.providers`` layout uniform (one module per backend) while
preserving the historical import path ``aether.ai.provider.EchoProvider``.
"""

from aether.ai.provider import EchoProvider  # noqa: F401
