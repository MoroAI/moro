"""SQL acceptance checks: closed identifiers, no pre-validation query, no leaks."""

import json

import pytest
from fastapi.testclient import TestClient

from moro.analytics.columns import (
    EXPERIMENT_METRIC_COLUMNS,
    HYPERPARAM_COLUMNS,
    AnalyticsColumnError,
    resolve_hyperparam,
    resolve_metric,
)
from moro.analytics.schema import initialize_experiment_db
from moro.analytics.tracker import ExperimentTracker
from moro.analytics.visualizations import VisualAnalyticsEngine
from moro.dashboard.mission_control import app

PAYLOADS = [
    "learning_rate || (SELECT value FROM audit_marker LIMIT 1)",
    "lora_r; DROP TABLE experiments",
    "(SELECT 1)",
    "learning_rate AS x, (SELECT value FROM audit_marker) AS y",
    "eval_delta --",
    "eval_delta\x00",
    "eval_delta\n",
    "EVAL_DELTA",
    "unknown",
]


@pytest.fixture
def tracker(tmp_path):
    db = tmp_path / "analytics.db"
    conn = initialize_experiment_db(db)
    conn.execute("CREATE TABLE audit_marker(value TEXT)")
    conn.execute("INSERT INTO audit_marker VALUES ('PRIVATE_MARKER')")
    for i, (lr, delta) in enumerate([(1.0, 1.0), (None, 100.0), (2.0, 2.0), (3.0, 3.0)]):
        conn.execute(
            "INSERT INTO experiments(experiment_id,experiment_name,base_model,eval_delta,status) VALUES(?,?,?,?,?)",
            (str(i), str(i), "tiny", delta, "completed"),
        )
        conn.execute(
            "INSERT INTO hyperparameters(param_id,experiment_id,learning_rate,lora_r) VALUES(?,?,?,?)",
            (str(i), str(i), lr, 16),
        )
    conn.commit()
    conn.close()
    return ExperimentTracker(db)


@pytest.mark.parametrize("bad", PAYLOADS)
@pytest.mark.parametrize("entry", ["x", "y", "metric", "correlation"])
def test_rejection_occurs_before_database_access(tracker, monkeypatch, bad, entry):
    def forbidden():
        raise AssertionError("Invalid identifier reached database access")

    monkeypatch.setattr(tracker, "_get_conn", forbidden)
    with pytest.raises(AnalyticsColumnError):
        if entry == "correlation":
            tracker.get_hyperparameter_correlations(bad)
        else:
            params = {"x_param": "learning_rate", "y_param": "lora_r", "metric": "eval_delta"}
            params[{"x": "x_param", "y": "y_param", "metric": "metric"}[entry]] = bad
            VisualAnalyticsEngine(tracker).generate_hyperparameter_heatmap(**params)


def test_valid_columns_match_actual_schema_and_queries(tracker):
    conn = tracker._get_conn()
    try:
        hp = {r[1] for r in conn.execute("PRAGMA table_info(hyperparameters)")}
        metrics = {r[1] for r in conn.execute("PRAGMA table_info(experiments)")}
        assert set(HYPERPARAM_COLUMNS.values()) <= hp
        assert set(EXPERIMENT_METRIC_COLUMNS.values()) <= metrics
    finally:
        conn.close()
    viz = VisualAnalyticsEngine(tracker)
    for name in HYPERPARAM_COLUMNS:
        assert resolve_hyperparam(name) == name
        viz.generate_hyperparameter_heatmap(name)
    for name in EXPERIMENT_METRIC_COLUMNS:
        assert resolve_metric(name) == name
        viz.generate_hyperparameter_heatmap(metric=name)
        tracker.get_hyperparameter_correlations(name)
    data = viz.generate_hyperparameter_heatmap()
    assert data["x_values"] == [1.0, 2.0, 3.0]
    assert "PRIVATE_MARKER" not in json.dumps(data)
    # Missing hyperparameters cannot shift targets onto the wrong experiments.
    result = tracker.get_hyperparameter_correlations()
    assert result["correlations"]["learning_rate"] == 1.0


@pytest.mark.parametrize("parameter", ["x_param", "y_param", "metric"])
def test_http_rejection_does_not_initialize_database(tmp_path, monkeypatch, parameter):
    monkeypatch.setenv("MORO_API_TOKEN", "sql-acceptance-" + "a" * 32)

    def forbidden():
        raise AssertionError("Invalid identifier initialized database")

    monkeypatch.setattr("moro.dashboard.mission_control._get_analytics_viz_engine", forbidden)
    client = TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer sql-acceptance-" + "a" * 32},
    )
    r = client.get("/api/analytics/viz/hyperparameter-heatmap", params={parameter: PAYLOADS[0]})
    assert r.status_code == 400
    assert "SELECT" not in r.text and "PRIVATE_MARKER" not in r.text
