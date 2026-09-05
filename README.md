# Datadog Observability Proof

An offline configuration-review MVP for a fictional storefront. It helps catch mismatched alert thresholds, misspelled metric names and basic dashboard mistakes before a human reviews deployment.

## Run

Python 3.9 or newer, standard library only:

```sh
python3 -m unittest discover -s tests -v
python3 demo.py
```

## What is here

- Synthetic metric and log catalogs in `fixtures/`.
- A metric monitor and a timeseries dashboard in `examples/`.
- A local consistency validator and small query parser in `dd_obs/`.
- Negative tests for threshold conflicts, unknown metrics, invalid queries and malformed configuration.

## Demonstration case study

A fictional shop wants to monitor failed checkouts. The example monitor uses a warning threshold of 3 percent and critical threshold of 5 percent. Both are illustrative choices, not measured business requirements. The dashboard and monitor refer to the same synthetic metric.

The reviewer runs the demo, then changes the critical option to 6 while leaving the query at 5. The test suite confirms that the validator flags that mismatch. This catches a configuration mistake; it does not simulate a real outage, calculate time-series values or prove an alert was delivered.

After an alert, an operator should inspect affected requests, recent releases and dependency errors before choosing a response. There is no automatic remediation in this project.

## Honest limits

This is an independent reference project, not a Datadog integration certification or a client case study. No metrics or logs are sent anywhere, and no credentials are needed. Catalog entries are descriptions and synthetic log records, not an ingestion pipeline.

Validation is a limited local subset, not the complete vendor schema or query language. Only the included metric monitor and dashboard path are covered by the current tests. Other monitor types, advanced formulas, logs syntax, arbitrary malformed catalogs and full layout constraints require further testing. Unknown fields and tags can generate advisory warnings; custom tags are legitimate. A passing result never means Datadog accepted a configuration.

The included monitor disables no-data notifications for this synthetic example. Production monitoring needs an explicit missing-data policy and a separate review of signal collection, permissions, routing and costs.

## Sources

- [Monitor API](https://docs.datadoghq.com/api/latest/monitors/): monitor fields and validation boundary.
- [Dashboard API](https://docs.datadoghq.com/api/latest/dashboards/): reference dashboard shapes.
- [Dashboard querying](https://docs.datadoghq.com/dashboards/querying/): metric and tag query concepts.
- [Metrics API](https://docs.datadoghq.com/api/latest/metrics/): future ingestion reference, not implemented here.

Public visibility does not grant a software license. No vendor affiliation or endorsement is implied.
