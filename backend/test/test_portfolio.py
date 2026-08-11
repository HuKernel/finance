from app import portfolio


def test_portfolio_cost_includes_unpriced_positions(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio, "DB_PATH", tmp_path / "portfolio.db")
    portfolio.buy_stock(1, "600519", "茅台", 10, 100, fee=5)
    portfolio.buy_stock(1, "000001", "平安", 20, 10)
    monkeypatch.setattr(
        "app.data.fetcher.get_stock_brief",
        lambda symbol, **kwargs: {"price": 110} if symbol == "600519" else None,
    )

    result = portfolio.get_portfolio(1)

    assert result["summary"] == {
        "total_market_value": 1100.0,
        "total_cost": 1205.0,
        "total_pnl": 95.0,
        "total_pnl_pct": 9.45,
        "position_count": 2,
        "unpriced_count": 1,
    }
    assert result["positions"][1]["cost"] == 200.0


def test_delete_transaction_rebuilds_position(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio, "DB_PATH", tmp_path / "portfolio.db")
    first = portfolio.buy_stock(1, "600519", "茅台", 10, 100, fee=10)
    portfolio.buy_stock(1, "600519", "茅台", 10, 200)
    transaction_id = portfolio.list_transactions(1)[0]["id"]

    assert first["total"] == 1010
    assert portfolio.delete_transaction(transaction_id, 1) is True
    monkeypatch.setattr("app.data.fetcher.get_stock_brief", lambda *args, **kwargs: None)
    position = portfolio.get_portfolio(1)["positions"][0]
    assert position["shares"] == 10
    assert position["avg_cost"] == 101


def test_cannot_delete_another_users_transaction(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio, "DB_PATH", tmp_path / "portfolio.db")
    portfolio.buy_stock(1, "600519", "茅台", 10, 100)
    transaction_id = portfolio.list_transactions(1)[0]["id"]

    assert portfolio.delete_transaction(transaction_id, 2) is False
    assert len(portfolio.list_transactions(1)) == 1
