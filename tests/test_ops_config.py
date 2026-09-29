from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ALERT_FIELDS = (
    "name",
    "severity",
    "type",
    "condition",
    "duration",
    "channel",
    "slack_channel",
    "owner",
    "runbook",
)


def _load_yaml(relative_path: str) -> dict:
    return yaml.safe_load((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def _slugify_heading(heading: str) -> str:
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\- ]+", "", slug)
    return slug.replace(" ", "-")


def _headings(markdown: str) -> set[str]:
    return {
        _slugify_heading(line.lstrip("#").strip())
        for line in markdown.splitlines()
        if line.startswith("#")
    }


def test_three_symptom_based_alerts_are_fully_specified() -> None:
    alerts = _load_yaml("config/alert_rules.yaml")["alerts"]

    assert len(alerts) == 3
    assert len({alert["name"] for alert in alerts}) == 3

    for index, alert in enumerate(alerts, start=1):
        for field in REQUIRED_ALERT_FIELDS:
            value = alert.get(field)
            assert value not in (None, "", "TODO"), f"alert {index} thiếu {field}"
        assert alert["type"] == "symptom-based"
        assert alert["severity"] in {"critical", "warning"}
        assert alert["channel"] == "slack"
        assert alert["slack_channel"].startswith("#")
        assert re.match(r"^\d+[smh]$", alert["duration"]), alert["duration"]
        assert "window" in alert
        assert alert["dashboard_panel"] in {
            "latency",
            "traffic",
            "errors",
            "cost",
            "tokens",
            "quality",
        }


def test_alerts_describe_user_symptoms_not_internal_names() -> None:
    alerts = _load_yaml("config/alert_rules.yaml")["alerts"]

    for alert in alerts:
        symptom = alert["symptom"]
        assert "Người dùng" in symptom
        assert "retrieve(" not in symptom
        assert "generate(" not in symptom
        assert alert["condition"], alert["name"]


def test_every_alert_runbook_anchor_resolves_in_docs() -> None:
    alerts = _load_yaml("config/alert_rules.yaml")["alerts"]
    runbook = (REPO_ROOT / "docs" / "alerts.md").read_text(encoding="utf-8")
    headings = _headings(runbook)

    for alert in alerts:
        runbook_ref, _, anchor = alert["runbook"].partition("#")
        assert runbook_ref == "docs/alerts.md"
        assert anchor, alert["name"]
        assert anchor in headings, f"docs/alerts.md chưa có heading cho {alert['runbook']}"


def test_runbook_covers_required_operations_for_each_alert() -> None:
    runbook = (REPO_ROOT / "docs" / "alerts.md").read_text(encoding="utf-8")
    sections = re.findall(r"^## (Alert \d+)\n(.*?)(?=^## |\Z)", runbook, flags=re.MULTILINE | re.DOTALL)

    assert [title for title, _ in sections] == ["Alert 1", "Alert 2", "Alert 3"]
    for title, section in sections:
        for label in (
            "Tên:",
            "Severity:",
            "Duration:",
            "Kênh thông báo:",
            "SLI/SLO liên quan:",
            "Điều kiện và thời gian duy trì:",
            "Ảnh hưởng tới người dùng:",
            "Ba bước kiểm tra đầu tiên:",
            "Mitigation tạm thời:",
            "Owner:",
        ):
            assert label in section, f"thiếu '{label}' trong runbook {title}"


def test_slo_error_budget_is_mathematically_consistent() -> None:
    slo = _load_yaml("config/slo.yaml")["primary_slo"]

    target = slo["target_percent"]
    error_budget = slo["error_budget_percent"]

    assert 0 < target <= 100
    assert round(100 - target, 6) == error_budget
    assert slo["window"] == "28d"

    assert slo["error_budget_unit"] == "bad_requests"
    assert "good_event" in slo["sli"] and "total_event" in slo["sli"]


def test_slo_thresholds_agree_with_dashboard_contract() -> None:
    slo = _load_yaml("config/slo.yaml")
    dashboard = _load_yaml("config/dashboard.yaml")["dashboard"]
    panels = {panel["id"]: panel for panel in dashboard["panels"]}
    guardrails = slo["guardrails"]

    assert guardrails["error_rate_pct_max"] == panels["errors"]["threshold"]["value"]
    assert guardrails["daily_cost_usd_max"] == panels["cost"]["threshold"]["value"]
    assert guardrails["quality_score_avg_min"] == panels["quality"]["threshold"]["value"]

    latency_threshold = panels["latency"]["threshold"]["value"]
    assert f"latency_ms <= {latency_threshold}" in slo["primary_slo"]["sli"]["good_event"]
    assert slo["primary_slo"]["latency_threshold_ms"] == latency_threshold

    latency_alert = next(
        alert
        for alert in _load_yaml("config/alert_rules.yaml")["alerts"]
        if alert["dashboard_panel"] == "latency"
    )
    assert latency_alert["slo_threshold_ms"] == latency_threshold


def test_slo_guardrails_reference_existing_alerts() -> None:
    slo = _load_yaml("config/slo.yaml")
    alert_names = {alert["name"] for alert in _load_yaml("config/alert_rules.yaml")["alerts"]}

    assert set(slo["guardrails"]["alert_refs"]) == alert_names
