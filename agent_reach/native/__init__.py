# -*- coding: utf-8 -*-
"""In-repo backends for sites whose third-party CLIs are only fallback legs.

Modules here own the request logic and leave credentials, throttling and
error-code mapping inside Agent Reach. Importing this package has no side
effects; each backend is imported lazily by its channel.
"""
