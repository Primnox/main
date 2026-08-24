"""Runtime settings — the things you should not have to edit a file to change.

Everything here is stored in primnox.db EXCEPT secrets, which stay in the
keyring or `v2/.env`. That split is the whole design; see `service.py`.
"""
from . import service  # noqa: F401
