from datetime import date

from app import company_events


def test_report_periods_follow_disclosure_season():
    assert company_events._report_periods(date(2026, 3, 1)) == ["20251231", "20260331"]
    assert company_events._report_periods(date(2026, 8, 11)) == ["20260630"]
    assert company_events._report_periods(date(2026, 9, 1)) == ["20260930"]


def test_company_events_only_include_user_symbols(monkeypatch):
    monkeypatch.setattr(company_events, "_user_symbols", lambda user_id: {"600519"})
    monkeypatch.setattr(company_events, "_report_periods", lambda today: ["20260630"])
    monkeypatch.setattr(company_events, "_load_period", lambda period: [
        {"symbol": "600519", "name": "茅台", "period": period, "date": "2026-08-15", "status": "预约"},
        {"symbol": "000001", "name": "平安", "period": period, "date": "2026-08-16", "status": "预约"},
    ])

    result = company_events.list_company_events(7)

    assert [item["symbol"] for item in result["items"]] == ["600519"]
    assert result["source"] == "东方财富"
