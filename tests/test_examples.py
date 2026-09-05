import copy
import json
import unittest
from demo import ROOT, run
from dd_obs.catalog import MetricCatalog, LogCatalog
from dd_obs.validator import validate_monitor, validate_dashboard

class Examples(unittest.TestCase):
    def setUp(self):
        self.metrics, _ = MetricCatalog.from_path(ROOT / 'fixtures/metric_catalog.json')
        self.logs, _ = LogCatalog.from_path(ROOT / 'fixtures/log_catalog.json')
        self.monitor = json.loads((ROOT / 'examples/monitor.json').read_text())
        self.dashboard = json.loads((ROOT / 'examples/dashboard.json').read_text())
    def codes(self, obj):
        return {i.code for i in validate_monitor(obj, self.metrics, self.logs)}
    def test_examples_no_errors(self):
        self.assertFalse(run()['fixture_issues'])
        self.assertTrue(all(not v for v in run()['artifacts'].values()))
        self.assertFalse([i for v in run()['artifacts'].values() for i in v if i['severity'] == 'error'])
    def test_threshold_mismatch(self):
        self.monitor['options']['thresholds']['critical'] = 6
        self.assertIn('THRESHOLD_QUERY_MISMATCH', self.codes(self.monitor))
    def test_threshold_order(self):
        self.monitor['options']['thresholds']['warning'] = 8
        self.assertIn('THRESHOLD_ORDER_INVERTED', self.codes(self.monitor))
    def test_unknown_metric(self):
        self.monitor['query'] = self.monitor['query'].replace('storefront.checkout.failure_rate', 'unknown.metric')
        self.assertIn('UNKNOWN_METRIC', self.codes(self.monitor))
    def test_invalid_query(self):
        self.monitor['query'] = 'invalid'
        self.assertIn('MALFORMED_QUERY', self.codes(self.monitor))
    def test_missing_name(self):
        del self.monitor['name']
        self.assertIn('MISSING_NAME', self.codes(self.monitor))
    def test_boolean_option(self):
        self.monitor['options']['notify_no_data'] = 'false'
        self.assertIn('OPTION_NOT_BOOLEAN', self.codes(self.monitor))
    def test_dashboard_title(self):
        del self.dashboard['title']
        self.assertIn('MISSING_TITLE', {i.code for i in validate_dashboard(self.dashboard,self.metrics,self.logs)})
    def test_dashboard_layout(self):
        self.dashboard['layout_type'] = 'invalid'
        self.assertIn('BAD_LAYOUT_TYPE', {i.code for i in validate_dashboard(self.dashboard,self.metrics,self.logs)})
    def test_non_object(self):
        self.assertIn('NOT_OBJECT', self.codes([]))
