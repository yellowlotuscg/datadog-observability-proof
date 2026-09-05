import json
from pathlib import Path
from dd_obs.catalog import MetricCatalog, LogCatalog
from dd_obs.validator import validate_monitor, validate_dashboard
ROOT = Path(__file__).parent

def run():
    metrics, mi = MetricCatalog.from_path(ROOT / 'fixtures/metric_catalog.json')
    logs, li = LogCatalog.from_path(ROOT / 'fixtures/log_catalog.json')
    result = {'fixture_issues': mi + li, 'artifacts': {}}
    for kind, check in [('monitor', validate_monitor), ('dashboard', validate_dashboard)]:
        data = json.loads((ROOT / ('examples/' + kind + '.json')).read_text())
        result['artifacts'][kind] = [i._asdict() for i in check(data, metrics, logs)]
    return result

if __name__ == '__main__':
    result = run()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['fixture_issues']) or any(i['severity'] == 'error' for issues in result['artifacts'].values() for i in issues))
