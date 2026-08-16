from app.data import market


def test_top_turnover_stock_uses_full_market_snapshot(monkeypatch):
    class Response:
        @staticmethod
        def json():
            return {"data": {"rank_list": [{"code": "sz300308", "name": "中际旭创", "turnover": "4576439"}]}}

    monkeypatch.setattr(market.http_client, "get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(market, "cached", lambda _key, _ttl, fn: fn())

    result = market.get_top_turnover_stock()

    assert result["code"] == "300308"
    assert result["amount"] == 45_764_390_000
    assert result["scope"] == "a_share_full_market"
