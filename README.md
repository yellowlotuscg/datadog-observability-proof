# Datadog Observability Proof

Offline checks for Datadog-style monitor and dashboard JSON. The examples are a fictional storefront. `demo.py` checks the two example files. The tests call the same checks on those files and on in-memory copies with mistakes: a threshold that does not match the query, a metric name missing from the local catalog, a dashboard with a missing title or a bad layout type, and a few other broken shapes.

## Run

Python 3.9 or newer, standard library only. Clone with HTTPS and run the commands from the repository root:

```sh
git clone https://github.com/yellowlotuscg/datadog-observability-proof.git
cd datadog-observability-proof
python3 -m unittest discover -s tests -v
python3 demo.py
```

`demo.py` reads `examples/monitor.json` and `examples/dashboard.json`, checks them against the catalogs in `fixtures/`, and prints JSON. It exits 0 when the catalogs load cleanly and neither file has an error. Warnings are included in the JSON and do not change the exit code. The checked-in examples currently produce no errors and no warnings.

## What is here

- Synthetic metric and log catalogs in `fixtures/`.
- A `query alert` monitor, and an ordered dashboard with one timeseries widget, in `examples/`.
- A local checker and a small query parser in `dd_obs/`.
- Tests for threshold conflicts, unknown metrics, invalid queries, and malformed configuration.

## Example

The sample monitor watches failed checkouts. `options.thresholds` sets warning to 3 and critical to 5. `storefront.checkout.failure_rate` is a percent gauge in the metric catalog, so those numbers are percents. They are sample choices, not measured requirements. The dashboard widget queries the same metric.

The query in `examples/monitor.json` ends in `> 5`, and `options.thresholds.critical` is also 5. In `tests/test_examples.py`, `test_threshold_mismatch` sets that critical value to 6 and leaves the query at 5. The checker returns `THRESHOLD_QUERY_MISMATCH`. `test_threshold_order` sets warning to 8, above critical, on a `>` comparison. The checker returns `THRESHOLD_ORDER_INVERTED`.

These checks catch inconsistencies in the JSON. They do not simulate an outage, compute a time series, or show that an alert was sent.

The monitor message says to review synthetic checkout errors and recent changes, and not to auto-remediate. This repository has no remediation. After a real alert, someone still needs to look at the affected requests, the recent release, and dependency errors before choosing a response.

## Limits

This is an independent reference project. It is not a Datadog integration certification or a client case study. It sends no metrics or logs, and it needs no credentials. The metric catalog stores names, types, units, and descriptions. The log catalog stores made-up log events. There is no ingestion pipeline.

The checker covers a limited local subset of the vendor schema and query language. The current tests exercise the included metric monitor and the included dashboard. Other monitor types, formula queries, log search syntax, malformed catalogs, and full layout rules still need tests. Log query parsing exists in `dd_obs/queries.py` and `dd_obs/validator.py`, and no test in this repository calls it. Keys outside the checker's allow lists for dashboards, monitors, options, and thresholds produce warnings. In a query scope or `by` group, tag keys other than `env`, `service`, `host`, `status`, `region`, `team`, `version`, `cluster`, `pod`, `instance`, `device`, and `role` also produce a warning. The monitor `tags` list is not checked that way. A custom tag can still be valid. The warning is only a local hint. A passing result does not mean Datadog accepted the configuration.

The included monitor sets `notify_no_data` to false. Production monitoring needs an explicit missing-data policy, and a separate review of how the signal is collected, who can edit the monitor, where notifications go, and what it costs.

## Sources

- [Monitor API](https://docs.datadoghq.com/api/latest/monitors/): monitor fields used as the shape reference for this checker.
- [Dashboard API](https://docs.datadoghq.com/api/latest/dashboards/): dashboard shapes used as the shape reference.
- [Dashboard querying](https://docs.datadoghq.com/dashboards/querying/): metric and tag query concepts.
- [Metrics API](https://docs.datadoghq.com/api/latest/metrics/): future ingestion reference. Submitting metrics is not implemented here.

Copyright (c) 2026 Matthew Coggins. Licensed under the MIT License. See [LICENSE](LICENSE). No Datadog affiliation or endorsement is implied.
