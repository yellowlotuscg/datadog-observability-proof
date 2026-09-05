"""Datadog offline observability proof: local consistency validation.

A bounded, offline, public reference project. Everything in this package
runs against explicitly synthetic fixture data that mirrors the JSON shapes
documented in Datadog's public API and product documentation. No Datadog
account, API endpoint, agent, or SDK is contacted, and nothing here sends
metrics, logs, or monitor definitions anywhere.

The validator is a local consistency check only. It is NOT a substitute for
Datadog's own server-side monitor validation endpoint or dashboard
acceptance checks against a live org.
"""

__version__ = "1.0.0"
