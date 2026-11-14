"""Explicit single opt-in loopback endpoint; no broadened network access."""

from __future__ import annotations

import os
import urllib.parse
import urllib.request


def install() -> None:
    import local_transport
    import text_transport

    endpoint = os.environ["T7_LATENCY_MODEL_URL"].rstrip("/")
    parsed = urllib.parse.urlparse(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 18687
        or parsed.path != "/v1"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Expected the explicitly configured private T7 pool")
    for module in (local_transport, text_transport):
        previous = module.connection

        def connection(role, previous=previous):
            config, secret = previous(role)
            return dict(config, chat_url=endpoint + "/chat/completions"), secret

        setattr(module, "connection", connection)

    def guard() -> None:
        previous = urllib.request.OpenerDirector.open
        allowed = {
            ("127.0.0.1", 18084),
            ("127.0.0.1", 18687),
            ("127.0.0.1", 19865),
            ("127.0.0.1", 19866),
            ("localhost", 19865),
            ("localhost", 19866),
        }

        def open_request(opener, request, *args, **kwargs):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            target = urllib.parse.urlparse(url)
            if target.scheme in ("http", "https") and (
                target.scheme != "http" or (target.hostname, target.port) not in allowed
            ):
                raise RuntimeError("API endpoint outside explicit local allowlist")
            return previous(opener, request, *args, **kwargs)

        setattr(urllib.request.OpenerDirector, "open", open_request)

    text_transport.install_network_guard = guard
