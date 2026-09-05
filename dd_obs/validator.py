"""Local consistency validator for synthetic Datadog dashboard and monitor
JSON definitions.

Scope and honest boundary
-------------------------
This validator checks LOCAL, deterministic consistency only:

- structural shape documented by the Datadog API and product docs
  (required fields, documented enums, layout rules),
- threshold coherence (alert/warning ordering, query-to-options match),
- query coherence (referenced metrics exist in the synthetic metric
  catalog; log facets and values exist among the synthetic log events).

It does NOT reach the Datadog API. It is not a substitute for Datadog's
own server-side "Validate a monitor" endpoint or for dashboard acceptance
against a live org. Passing this validator means the JSON is internally
consistent and shaped like documented Datadog JSON, nothing more.
"""

from collections import namedtuple

from . import queries
from .catalog import MetricCatalog, LogCatalog

Issue = namedtuple("Issue", ["code", "severity", "path", "message"])
SEVERITY = ("error", "warning")

# Documented monitor types (API reference, "Create a monitor": Monitor Types).
MONITOR_TYPES = (
    "query alert",
    "trace-analytics alert",
    "composite",
    "service check",
    "process alert",
    "log alert",
    "rum alert",
    "slo alert",
    "event-v2 alert",
    "audit alert",
    "error-tracking alert",
    "database-monitoring alert",
    "network-performance alert",
    "cost alert",
    "network-path alert",
)

# Threshold-bearing monitor types used by this proof. Other documented
# types are accepted but receive only generic checks.
THRESHOLD_TYPES = ("query alert", "log alert")

# Documented widget types (dashboard widgets index, conservative subset).
WIDGET_TYPES = (
    "alert_graph",
    "check_status",
    "distribution",
    "event_stream",
    "event_timeline",
    "free_text",
    "geomap",
    "heatmap",
    "hostmap",
    "iframe",
    "image",
    "log_stream",
    "manage_status",
    "monitor_summary",
    "note",
    "process_stream",
    "query_table",
    "query_value",
    "run_workflow",
    "scatterplot",
    "service_map",
    "service_summary",
    "slo",
    "slo_list",
    "timeseries",
    "toplist",
    "trace_service",
    "treemap",
    "uptime",
)

# Widget types whose query strings are metric queries.
METRIC_WIDGET_TYPES = (
    "timeseries",
    "query_value",
    "toplist",
    "heatmap",
    "query_table",
    "distribution",
    "scatterplot",
)

# Widget types whose query strings are log/event search expressions.
LOG_WIDGET_TYPES = ("log_stream", "event_stream", "event_timeline")

# Widget types that carry no queries.
TEXT_WIDGET_TYPES = ("note", "free_text", "iframe", "image")

# Tag keys commonly applied by agents/integrations; unknown keys are warned
# about as a typo catcher. Values are free-form and not validated.
KNOWN_TAG_KEYS = (
    "env",
    "service",
    "host",
    "status",
    "region",
    "team",
    "version",
    "cluster",
    "pod",
    "instance",
    "device",
    "role",
)

DASHBOARD_KEYS = (
    "title",
    "description",
    "layout_type",
    "widgets",
    "template_variables",
    "notify_list",
    "reflow_type",
)

MONITOR_KEYS = (
    "name",
    "type",
    "query",
    "message",
    "tags",
    "options",
    "priority",
    "multi",
    "restricted_roles",
)

MONITOR_OPTION_KEYS = (
    "thresholds",
    "notify_no_data",
    "no_data_timeframe",
    "require_full_window",
    "evaluation_delay",
    "new_host_delay",
    "new_group_delay",
    "timeout_h",
    "include_tags",
    "notify_audit",
    "escalation_message",
    "renotify_interval",
    "enable_logs_sample",
    "silenced",
    "min_failure_duration",
    "min_location_failed",
    "group_retention_duration",
    "on_missing_data",
)

THRESHOLD_KEYS = (
    "critical",
    "warning",
    "critical_recovery",
    "warning_recovery",
)

_LOG_ALERT_STORED = 'logs"'  # stored/exported compact form


class Result:
    """Validation outcome for one artifact file."""

    def __init__(self, path, kind, issues):
        self.path = path
        self.kind = kind
        self.issues = list(issues)

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self):
        return not self.errors


def _err(code, path, message):
    return Issue(code, "error", path, message)


def _warn(code, path, message):
    return Issue(code, "warning", path, message)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Dashboard validation
# ---------------------------------------------------------------------------


def validate_dashboard(obj, metric_catalog, log_catalog, base="dashboard"):
    issues = []
    if not isinstance(obj, dict):
        return [_err("NOT_OBJECT", base, "dashboard JSON root must be an object")]

    title = obj.get("title")
    if not isinstance(title, str) or not title.strip():
        issues.append(_err("MISSING_TITLE", base, "dashboard requires a non-empty title"))

    for key in obj:
        if key not in DASHBOARD_KEYS:
            issues.append(_warn("UNKNOWN_DASHBOARD_KEY", base,
                                "key %r is not part of the documented dashboard schema" % key))

    layout_type = obj.get("layout_type")
    if layout_type not in ("free", "ordered"):
        issues.append(_err("BAD_LAYOUT_TYPE", base,
                           "layout_type must be 'free' or 'ordered', got %r" % (layout_type,)))

    widgets = obj.get("widgets")
    if not isinstance(widgets, list) or not widgets:
        issues.append(_err("MISSING_WIDGETS", base,
                           "dashboard requires a non-empty widgets list"))
        return issues

    for idx, widget in enumerate(widgets):
        wpath = "%s.widgets[%d]" % (base, idx)
        _check_widget(widget, layout_type, wpath, metric_catalog, log_catalog, issues)

    return issues


def _check_widget(widget, layout_type, wpath, metric_catalog, log_catalog, issues):
    if not isinstance(widget, dict):
        issues.append(_err("WIDGET_NOT_OBJECT", wpath, "widget must be an object"))
        return

    if layout_type == "free":
        layout = widget.get("layout")
        if not isinstance(layout, dict):
            issues.append(_err("WIDGET_MISSING_LAYOUT", wpath,
                               "widgets on a free-layout dashboard require layout {x,y,width,height}"))
        else:
            for axis in ("x", "y", "width", "height"):
                value = layout.get(axis)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    issues.append(_err("WIDGET_BAD_LAYOUT", wpath,
                                       "layout.%s must be numeric, got %r" % (axis, value)))
    elif widget.get("layout") is not None:
        issues.append(_warn("WIDGET_UNEXPECTED_LAYOUT", wpath,
                            "widget layout is set but layout_type is 'ordered'; layout applies to free dashboards only"))

    definition = widget.get("definition")
    if not isinstance(definition, dict):
        issues.append(_err("WIDGET_MISSING_DEFINITION", wpath,
                           "widget requires a definition object"))
        return

    wtype = definition.get("type")
    if wtype not in WIDGET_TYPES:
        issues.append(_err("UNKNOWN_WIDGET_TYPE", wpath,
                           "widget definition type %r is not in the documented widget type list" % (wtype,)))
        return

    if wtype in METRIC_WIDGET_TYPES:
        for q in _collect_requests_queries(definition):
            _check_widget_metric_query(q, wpath, metric_catalog, issues)
    elif wtype in LOG_WIDGET_TYPES:
        for q in _collect_requests_queries(definition):
            _check_log_query_terms(q, wpath, log_catalog, issues, expect_logs_prefix=False)
    elif wtype not in TEXT_WIDGET_TYPES:
        for q in _collect_requests_queries(definition):
            if isinstance(q, str) and q.strip():
                parsed = queries.parse_widget_metric_query(q)
                if parsed is None:
                    issues.append(_warn("UNPARSED_QUERY", wpath,
                                        "query %r is not a documented metric query shape; formula queries are out of scope for this validator" % q))


def _collect_requests_queries(definition):
    """Yield query strings found under definition.requests[].q and
    definition.requests[].queries[].query (both documented JSON forms)."""
    requests = definition.get("requests")
    if not isinstance(requests, list):
        return
    for request in requests:
        if not isinstance(request, dict):
            continue
        if isinstance(request.get("q"), str):
            yield request["q"]
        queries_list = request.get("queries")
        if isinstance(queries_list, list):
            for entry in queries_list:
                if isinstance(entry, dict) and isinstance(entry.get("query"), str):
                    yield entry["query"]


def _check_widget_metric_query(query, wpath, metric_catalog, issues):
    if not isinstance(query, str) or not query.strip():
        return
    if not queries.has_balanced_parens(query):
        issues.append(_err("UNBALANCED_PARENS", wpath,
                           "query %r has unbalanced parentheses" % query))
        return
    parsed = queries.parse_widget_metric_query(query)
    if parsed is None:
        issues.append(_err("MALFORMED_QUERY", wpath,
                           "query %r does not match the documented metric query grammar "
                           "space_aggr:metric{tags} by {key}" % query))
        return
    if parsed["metric"] not in metric_catalog.names:
        issues.append(_err("UNKNOWN_METRIC", wpath,
                           "query references metric %r which is absent from the synthetic metric catalog"
                           % parsed["metric"]))
    _check_tag_keys(parsed["tag_scope"], wpath, issues)
    _check_tag_keys(parsed["by"], wpath, issues)


def _check_tag_keys(scope, wpath, issues):
    """Warn about tag keys that are not among commonly documented keys."""
    if not scope or scope.strip() == "*":
        return
    scope = scope.strip().strip("{}")
    for item in scope.split(","):
        item = item.strip()
        if not item:
            continue
        if item == "*":
            continue
        key = item.partition(":")[0]
        if key not in KNOWN_TAG_KEYS:
            issues.append(_warn("UNKNOWN_TAG_KEY", wpath,
                                "tag key %r is not among the commonly documented tag keys" % key))


# ---------------------------------------------------------------------------
# Monitor validation
# ---------------------------------------------------------------------------


def validate_monitor(obj, metric_catalog, log_catalog, base="monitor"):
    issues = []
    if not isinstance(obj, dict):
        return [_err("NOT_OBJECT", base, "monitor JSON root must be an object")]

    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        issues.append(_err("MISSING_NAME", base, "monitor requires a non-empty name"))

    mtype = obj.get("type")
    if mtype not in MONITOR_TYPES:
        issues.append(_err("UNKNOWN_MONITOR_TYPE", base,
                           "monitor type %r is not in the documented monitor type list" % (mtype,)))
        return issues

    for key in obj:
        if key not in MONITOR_KEYS:
            issues.append(_warn("UNKNOWN_MONITOR_KEY", base,
                                "key %r is not part of the documented monitor create schema" % key))

    query = obj.get("query")
    if not isinstance(query, str) or not query.strip():
        issues.append(_err("MISSING_QUERY", base, "monitor requires a query string"))

    tags = obj.get("tags")
    if tags is not None and not isinstance(tags, list):
        issues.append(_err("TAGS_NOT_LIST", base, "monitor tags must be a list of strings"))

    options = obj.get("options")
    if options is not None and not isinstance(options, dict):
        issues.append(_err("OPTIONS_NOT_OBJECT", base, "monitor options must be an object"))
        options = None

    if isinstance(query, str) and query.strip():
        _check_monitor_query(query, mtype, base, metric_catalog, log_catalog, issues)

    if mtype in THRESHOLD_TYPES:
        _check_monitor_thresholds(obj, query, options, mtype, base, issues)

    if isinstance(options, dict):
        _check_monitor_options(options, base, issues)

    return issues


def _check_monitor_query(query, mtype, base, metric_catalog, log_catalog, issues):
    if not queries.has_balanced_parens(query):
        issues.append(_err("UNBALANCED_PARENS", base,
                           "query %r has unbalanced parentheses" % query))
        return
    if mtype == "log alert":
        if query.startswith(_LOG_ALERT_STORED):
            if not query.endswith('"'):
                issues.append(_err("MALFORMED_QUERY", base,
                                   "stored log alert query must end with a closing quote"))
                return
            inner = query[len(_LOG_ALERT_STORED):-1]
            if not queries.has_balanced_quotes(inner):
                issues.append(_err("UNBALANCED_QUOTES", base,
                                   "log search expression has unbalanced quotes"))
                return
            _check_log_query_terms(inner, base, log_catalog, issues, expect_logs_prefix=False)
            return
        form_b = queries.parse_log_alert_form_b(query)
        if form_b is None:
            issues.append(_err("MALFORMED_QUERY", base,
                               "log alert query matches neither the stored form logs\"...\" nor the "
                               "documented form logs(query).index(...).rollup(...).last(...) operator #"))
        else:
            if not queries.has_balanced_quotes(form_b["inner_query"]):
                issues.append(_err("UNBALANCED_QUOTES", base,
                                   "log search expression has unbalanced quotes"))
            else:
                _check_log_query_terms(form_b["inner_query"], base, log_catalog, issues,
                                       expect_logs_prefix=False)
        return

    parsed = queries.parse_metric_monitor_query(query)
    if parsed is None:
        issues.append(_err("MALFORMED_QUERY", base,
                           "query %r does not match the documented metric alert grammar "
                           "time_aggr(window):space_aggr:metric{tags} by {key} operator #" % query))
        return
    if parsed["metric"] not in metric_catalog.names:
        issues.append(_err("UNKNOWN_METRIC", base,
                           "query references metric %r which is absent from the synthetic metric catalog"
                           % parsed["metric"]))
    _check_tag_keys(parsed["tag_scope"], base, issues)
    _check_tag_keys(parsed["by"], base, issues)


def _check_log_query_terms(expression, base, log_catalog, issues, expect_logs_prefix):
    """Check log search terms against the synthetic log catalog.

    Facet keys must exist in the catalog (error otherwise). Facet values
    that never appear in any fixture event produce a warning, as does an
    expression that matches zero fixture events.
    """
    if expect_logs_prefix and not expression.startswith(_LOG_ALERT_STORED):
        issues.append(_err("MALFORMED_QUERY", base,
                           "log query must start with the logs prefix"))
        return
    text = expression[len(_LOG_ALERT_STORED):-1] if expect_logs_prefix else expression
    if not queries.has_balanced_quotes(text):
        issues.append(_err("UNBALANCED_QUOTES", base,
                           "log search expression has unbalanced quotes"))
        return

    terms = queries.split_log_search_terms(text)
    if not terms:
        issues.append(_err("EMPTY_LOG_QUERY", base,
                           "log search expression is empty after parsing"))
        return

    has_or = any(t["kind"] == "operator" and t["text"] == "OR" for t in terms)
    has_negation = any(t.get("negated") for t in terms)
    has_wildcard = any(
        (t["kind"] == "facet" and "*" in t["value"]) or (t["kind"] == "text" and "*" in t["text"])
        for t in terms
    )
    positives = [t for t in terms if t["kind"] in ("facet", "text") and not t.get("negated")]
    negatives = [t for t in terms if t["kind"] in ("facet", "text") and t.get("negated")]

    matched = log_catalog.logs
    for t in positives:
        if t["kind"] == "facet":
            observed = log_catalog.facet_observed_values(t["key"])
            if not observed:
                issues.append(_err("UNKNOWN_LOG_FACET", base,
                                   "facet %r in query never appears in the synthetic log catalog"
                                   % t["key"]))
                continue
            if "*" not in t["value"] and t["value"] not in observed:
                issues.append(_warn("LOG_FACET_VALUE_NO_MATCH", base,
                                    "facet %s:%s in query never appears in the synthetic log catalog"
                                    % (t["key"], t["value"])))
            matched = [e for e in matched if e in log_catalog.events_for_facet(t["key"], t["value"])]
        else:
            if "*" not in t["text"]:
                hits = log_catalog.message_contains(t["text"])
                matched = [e for e in matched if e in hits]
    for t in negatives:
        if t["kind"] == "facet":
            excluded = log_catalog.events_for_facet(t["key"], t["value"])
        else:
            excluded = log_catalog.message_contains(t["text"])
        matched = [e for e in matched if e not in excluded]

    if not has_or and not has_negation and not has_wildcard and len(matched) == 0:
        issues.append(_warn("LOG_QUERY_ZERO_MATCH", base,
                            "expression matches none of the synthetic log events; verify the query is intentional"))
    if has_or:
        issues.append(_warn("LOG_QUERY_OR_APPROXIMATE", base,
                            "OR expressions are matched approximately by this local validator"))


def _check_monitor_thresholds(obj, query, options, mtype, base, issues):
    thresholds = None
    if isinstance(options, dict) and isinstance(options.get("thresholds"), dict):
        thresholds = options["thresholds"]
        for key in thresholds:
            if key not in THRESHOLD_KEYS:
                issues.append(_warn("UNKNOWN_THRESHOLD_KEY", base,
                                    "options.thresholds key %r is not documented" % key))
        for key in ("critical", "warning", "critical_recovery", "warning_recovery"):
            if key in thresholds and not _is_number(thresholds[key]):
                issues.append(_err("THRESHOLD_NOT_NUMERIC", base,
                                   "options.thresholds.%s must be numeric, got %r" % (key, thresholds[key])))

    parsed = None
    if isinstance(query, str) and mtype == "query alert":
        parsed = queries.parse_metric_monitor_query(query)

    if parsed is not None:
        if parsed["threshold_keyword"]:
            if thresholds is None or not _is_number(thresholds.get("critical")):
                issues.append(_err("THRESHOLD_CRITICAL_MISSING", base,
                                   "query uses the dynamic 'threshold' keyword, so options.thresholds.critical is required"))
        elif thresholds is not None and "critical" in thresholds and _is_number(thresholds["critical"]):
            if abs(parsed["threshold"] - float(thresholds["critical"])) > 1e-9:
                issues.append(_err("THRESHOLD_QUERY_MISMATCH", base,
                                   "query threshold %s conflicts with options.thresholds.critical %s"
                                   % (parsed["threshold"], thresholds["critical"])))
    else:
        # Log alert and other threshold monitors carry thresholds in options.
        if thresholds is None:
            issues.append(_err("THRESHOLD_CRITICAL_MISSING", base,
                               "options.thresholds with a critical value is required for %s monitors" % mtype))
            return
        if not _is_number(thresholds.get("critical")):
            issues.append(_err("THRESHOLD_CRITICAL_MISSING", base,
                               "options.thresholds.critical is required for %s monitors" % mtype))

    if not isinstance(thresholds, dict) or not _is_number(thresholds.get("critical")):
        return

    critical = float(thresholds["critical"])
    warning = thresholds.get("warning")
    if not _is_number(warning):
        return
    warning = float(warning)

    if warning == critical:
        issues.append(_warn("THRESHOLD_WARNING_EQUALS_CRITICAL", base,
                            "warning threshold equals critical threshold; the warning state can never fire"))

    direction = parsed["operator"] if parsed is not None else ">"
    if direction in (">", ">="):
        if critical < warning:
            issues.append(_err("THRESHOLD_ORDER_INVERTED", base,
                               "critical %s is below warning %s on an above-threshold monitor; "
                               "warning would fire before alert" % (critical, warning)))
    elif direction in ("<", "<="):
        if critical > warning:
            issues.append(_err("THRESHOLD_ORDER_INVERTED", base,
                               "critical %s is above warning %s on a below-threshold monitor; "
                               "warning would fire before alert" % (critical, warning)))


def _check_monitor_options(options, base, issues):
    for key in options:
        if key not in MONITOR_OPTION_KEYS:
            issues.append(_warn("UNKNOWN_OPTION", base,
                                "options key %r is not part of the documented monitor options" % key))
    if "evaluation_delay" in options:
        value = options["evaluation_delay"]
        if not _is_number(value) or value < 0:
            issues.append(_err("BAD_EVALUATION_DELAY", base,
                               "options.evaluation_delay must be a non-negative integer of seconds"))
    for key in ("notify_no_data", "require_full_window", "include_tags",
                "notify_audit", "enable_logs_sample"):
        if key in options and not isinstance(options[key], bool):
            issues.append(_err("OPTION_NOT_BOOLEAN", base,
                               "options.%s must be a boolean, got %r" % (key, options[key])))
    if "timeout_h" in options:
        value = options["timeout_h"]
        if not _is_number(value) or value < 0:
            issues.append(_err("BAD_TIMEOUT", base,
                               "options.timeout_h must be a non-negative number of hours"))
    if "on_missing_data" in options and options["on_missing_data"] not in (
        "default", "show_and_notify_no_data", "show_no_data", "show_ok", "evaluate_as_zero", "show_last_known_status"
    ):
        issues.append(_err("BAD_ON_MISSING_DATA", base,
                           "options.on_missing_data %r is not a documented value" % options["on_missing_data"]))
