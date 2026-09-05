"""Synthetic catalog loading and fixture hygiene checks.

Two catalogs describe the fictional "storefront" workload that this proof
monitors:

- metric_catalog.json: the metric names, types, and units that dashboard
  widget queries and metric monitor queries may reference. Includes one
  documented system metric (system.cpu.user) so the fixtures demonstrate
  the exact query shapes shown in Datadog's documentation examples.
- log_catalog.json: synthetic log events with Datadog-style facets
  (service, status, env, host, @http.status_code) plus free-text messages.

Every entry is synthetic. No entry was captured from a real Datadog org.
"""

import json

METRIC_TYPES = ("gauge", "count", "rate", "distribution", "histogram")


class MetricCatalog:
    def __init__(self, metrics):
        self.metrics = metrics
        self.names = {m["name"] for m in metrics}

    @classmethod
    def from_path(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        issues = []
        if not payload.get("synthetic"):
            issues.append("metric catalog does not declare synthetic=true")
        metrics = payload.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            issues.append("metric catalog has no metrics list")
            return cls([]), issues
        for idx, entry in enumerate(metrics):
            name = entry.get("name")
            mtype = entry.get("type")
            if not isinstance(name, str) or not name:
                issues.append("metrics[%d] missing name" % idx)
            if mtype not in METRIC_TYPES:
                issues.append(
                    "metrics[%d] type %r not in %s" % (idx, mtype, METRIC_TYPES)
                )
        return cls(metrics), issues


class LogCatalog:
    def __init__(self, logs):
        self.logs = logs
        # Facet key -> set of observed string values, derived from events.
        self.facet_values = {}
        for event in logs:
            for key, value in event.items():
                if key in ("message", "timestamp", "schema_note"):
                    continue
                norm = key.lstrip("@")
                if isinstance(value, (list, dict)):
                    continue
                self.facet_values.setdefault(norm, set()).add(str(value))

    @classmethod
    def from_path(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        issues = []
        if not payload.get("synthetic"):
            issues.append("log catalog does not declare synthetic=true")
        logs = payload.get("logs")
        if not isinstance(logs, list) or not logs:
            issues.append("log catalog has no logs list")
            return cls([]), issues
        for idx, event in enumerate(logs):
            if "message" not in event or not isinstance(event["message"], str):
                issues.append("logs[%d] missing string message" % idx)
            for key in ("service", "status", "env", "host"):
                if key not in event:
                    issues.append("logs[%d] missing %s facet" % (idx, key))
        return cls(logs), issues

    def message_contains(self, term):
        term_l = term.casefold()
        return [e for e in self.logs if term_l in e["message"].casefold()]

    def events_for_facet(self, key, value):
        norm = key.lstrip("@")
        return [
            e
            for e in self.logs
            if norm in (k.lstrip("@") for k in e)
            and str(e.get(norm, e.get("@" + norm, ""))) == str(value)
        ]

    def facet_observed_values(self, key):
        return self.facet_values.get(key.lstrip("@"), set())
