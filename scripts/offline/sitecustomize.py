"""Process-wide outbound-network block, injected via ``PYTHONPATH``.

Python imports ``sitecustomize`` automatically at interpreter start, so putting this
directory on ``PYTHONPATH`` disables outbound connections for *everything* the
process does -- the server, the eval harness, the CLI -- without the application
knowing it is being tested.

That distinction is the point. ``tests/offline/test_no_network.py`` proves the code
paths it exercises are offline; this proves the **shipped binary** is, including any
path a test forgot. NFR-09 says the demo must work with networking disabled, and a
guarantee that depends on remembering to test it is not a guarantee.

Loopback stays open: the release check drives the real HTTP server over 127.0.0.1,
and asyncio needs its self-pipe. Blocking *connections* rather than socket creation
is deliberate for the same reason.

Usage (see ``scripts/release-check.sh``)::

    PYTHONPATH=scripts/offline uv run python -m app.eval.run
"""

from __future__ import annotations

import socket
import sys

_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_create_connection = socket.create_connection


def _host_of(address: object) -> str:
    if isinstance(address, tuple):
        return str(address[0])
    return str(address)


def _refuse(host: str) -> OSError:
    return OSError(
        f"outbound network is disabled for this run [NFR-09]: {host}. "
        "Nothing on a MUST path may reach the network."
    )


def _guarded_connect(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
    host = _host_of(address)
    if host in _LOOPBACK:
        return _real_connect(self, address, *args, **kwargs)
    raise _refuse(host)


def _guarded_connect_ex(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
    host = _host_of(address)
    if host in _LOOPBACK:
        return _real_connect_ex(self, address, *args, **kwargs)
    raise _refuse(host)


def _refuse_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
    host = _host_of(address)
    if host in _LOOPBACK:
        return _real_create_connection(address, *args, **kwargs)
    raise _refuse(host)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
socket.create_connection = _refuse_create_connection  # type: ignore[assignment]
# ``getaddrinfo`` is left alone: resolution without connection reaches nothing, and
# patching it breaks loopback binding on some stacks. The connect gate is the one
# that matters.

sys.stderr.write("  [offline-guard] outbound connections blocked (loopback allowed)\n")
