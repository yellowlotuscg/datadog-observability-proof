"""Query grammar parsing for synthetic Datadog metric and log queries.

The grammar rules encoded here come from Datadog's public API reference
("Create a monitor" page) and the dashboard querying documentation:

- Metric alert query:
  time_aggr(time_window):space_aggr:metric{tags} [by {key}] operator #
- Metric dashboard query (widget): space_aggr:metric{tags} [by {key}]
  with optional trailing function calls such as .as_rate() or .rollup(...)
- Log alert query (stored/exported form): logs"<log search terms>"
- Log alert query (API reference form):
  logs(query).index(index).rollup(method[, measure]).last(window) operator #

Parsing is intentionally strict and local. It validates shape only; metric
existence and log facet coherence are checked against the synthetic
catalogs by dd_obs.validator.
"""

import re

# Documented time aggregators for metric alert queries.
TIME_AGGREGATORS = ("avg", "sum", "max", "min", "change", "pct_change")
# Documented space aggregators for metric queries (avg/sum/min/max per the
# API reference; "count" is accepted here only as a widget-level convenience
# documented for count-style queries elsewhere in the docs).
SPACE_AGGREGATORS = ("avg", "sum", "max", "min", "count")
OPERATORS = (">=", "<=", "==", "!=", ">", "<")

# time_aggr(time_window):space_aggr:metric{tags} by {group} operator threshold
# The threshold slot accepts either a number or the preview keyword
# "threshold" (dynamic threshold sourced from options.thresholds).
_MONITOR_RE = re.compile(
    r"^(avg|sum|max|min|change|pct_change)"
    r"\((last_[0-9]+[mhd]|last_1d|last_1w)\)"
    r"\s*:\s*(avg|sum|min|max)\s*:\s*([A-Za-z0-9_.\-]+)"
    r"\s*(\{[^}]*\})?\s*(?:by\s+\{([^}]*)\})?\s*"
    r"(>=|<=|==|!=|>|<)\s*(threshold|[0-9]+(?:\.[0-9]+)?)$"
)

# space_aggr:metric{tags} by {group} with optional trailing function calls.
_FUNC_SUFFIX = re.compile(r"(?:\.\w+\([^)]*\))*$")
_WIDGET_RE = re.compile(
    r"^(avg|sum|max|min|count)\s*:\s*([A-Za-z0-9_.\-]+)"
    r"\s*(\{[^}]*\})?\s*(?:by\s+\{([^}]*)\})?$"
)

# Full API-reference log alert query form (docs "Create a monitor"):
# logs(query).index("*").rollup("count").last("5m") > 10
_LOG_ALERT_FORM_B = re.compile(
    r"^logs\((.+)\)"
    r"(?:\.index\((\"[^\"]*\"|\*)\))?"
    r"\.rollup\(\"(count|avg|cardinality)\"(?:,[^)]*)?\)"
    r"\.last\(\"([0-9]+[mhd])\"\)"
    r"\s*(>=|<=|==|!=|>|<)\s*([0-9]+(?:\.[0-9]+)?)$"
)

_LOG_PREFIX = "logs"


def _strip_function_suffixes(text):
    """Remove trailing .func(...) chains so the base query can be parsed."""
    while True:
        stripped = _FUNC_SUFFIX.sub("", text)
        if stripped == text:
            return stripped
        text = stripped


def parse_metric_monitor_query(query):
    """Parse a full metric alert monitor query.

    Returns a dict with keys time_aggr, window, space_aggr, metric,
    tag_scope, by, operator, threshold (float) or threshold_keyword (bool)
    on success, or None when the query does not match the documented
    grammar.
    """
    if not isinstance(query, str):
        return None
    m = _MONITOR_RE.match(query.strip())
    if not m:
        return None
    threshold_raw = m.group(8)
    parsed = {
        "time_aggr": m.group(1),
        "window": m.group(2),
        "space_aggr": m.group(3),
        "metric": m.group(4),
        "tag_scope": m.group(5),
        "by": m.group(6),
        "operator": m.group(7),
        "threshold": None,
        "threshold_keyword": threshold_raw == "threshold",
    }
    if not parsed["threshold_keyword"]:
        parsed["threshold"] = float(threshold_raw)
    return parsed


def parse_widget_metric_query(query):
    """Parse a dashboard widget metric query.

    Returns a dict with keys space_aggr, metric, tag_scope, by on success,
    or None when the query does not match the documented widget grammar
    (after any trailing function-call suffix has been removed).
    """
    if not isinstance(query, str):
        return None
    base = _strip_function_suffixes(query.strip())
    m = _WIDGET_RE.match(base)
    if not m:
        return None
    return {
        "space_aggr": m.group(1),
        "metric": m.group(2),
        "tag_scope": m.group(3),
        "by": m.group(4),
    }


def parse_log_alert_form_b(query):
    """Parse the API-reference log alert query form.

    Returns a dict with keys inner_query, index, rollup_method, window,
    operator, threshold on success, or None when the query does not match.
    """
    if not isinstance(query, str):
        return None
    m = _LOG_ALERT_FORM_B.match(query.strip())
    if not m:
        return None
    return {
        "inner_query": m.group(1),
        "index": m.group(2),
        "rollup_method": m.group(3),
        "window": m.group(4),
        "operator": m.group(5),
        "threshold": float(m.group(6)),
    }


def split_log_search_terms(text):
    """Tokenize a log search expression into individual terms.

    Returns a list of term dicts:
      {"kind": "facet", "key": "...", "value": "...", "negated": bool}
      {"kind": "text", "text": "...", "negated": bool}
    Operators AND/OR are returned as {"kind": "operator", "text": "..."}.
    Terms inside double quotes are kept as text terms (phrases).
    """
    terms = []
    tokens = _tokenize_quoted(text)
    for tok in tokens:
        if tok in ("AND", "OR"):
            terms.append({"kind": "operator", "text": tok})
            continue
        negated = False
        body = tok
        if body.startswith("-") and len(body) > 1:
            negated = True
            body = body[1:]
        if body.startswith('"') and body.endswith('"') and len(body) >= 2:
            body = body[1:-1]
        if ":" in body:
            key, _, value = body.partition(":")
            key = key.lstrip("@")
            if key and value:
                value = value.strip('"')
                terms.append(
                    {"kind": "facet", "key": key, "value": value, "negated": negated}
                )
                continue
        if body:
            terms.append({"kind": "text", "text": body, "negated": negated})
    return terms


def _tokenize_quoted(text):
    """Split on whitespace while honoring double-quoted phrases."""
    tokens = []
    current = []
    in_quote = False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
            current.append(ch)
        elif ch.isspace() and not in_quote:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current))
    return tokens


def has_balanced_quotes(text):
    """Return True when double-quote characters are balanced."""
    return text.count('"') % 2 == 0


def has_balanced_parens(text):
    """Return True when parentheses are balanced."""
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0
