"""Privacy Mirror — the cloud-boundary PII gate (CRS §13.2.2).

`mirror.py` is V1's backend/privacy_mirror.py, ported rather than rewritten:
the redaction rules (regex patterns, the city gazetteer, the confidence gates
per label) came from measured leaks against a real model, not from reading the
spec, and rewriting them from scratch would silently drop that measurement.
"""
