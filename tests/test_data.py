import json

import data
from data import fetch_symbol, load_cache, make_client, SPOT_CANDLES_PATH


class FakeClient:
    """Stands in for the vendored BitgetApi; records params, can fail per symbol."""

    def __init__(self, fail_symbols=(), rows=70):
        self.fail_symbols = set(fail_symbols)
        self.rows = rows
        self.calls = []

    def get(self, request_path, params):
        self.calls.append((request_path, dict(params)))
        if params["symbol"] in self.fail_symbols:
            raise ConnectionError("simulated network failure")
        return {"code": "00000", "data": [["1704067200000", "1", "1", "1", "1", "1", "1", "1"]] * self.rows}


def test_make_client_is_official_sdk_instance():
    from bitget.bitget_api import BitgetApi  # vendored official SDK
    c = make_client()
    assert isinstance(c, BitgetApi)
    assert c.API_KEY == "" and c.PASSPHRASE == ""   # public data: empty credentials


def test_fetch_symbol_hits_official_candles_path():
    fc = FakeClient()
    rows = fetch_symbol(fc, "RNVDAUSDT")
    assert len(rows) == 70
    path, params = fc.calls[0]
    assert path == SPOT_CANDLES_PATH
    assert params == {"symbol": "RNVDAUSDT", "granularity": "1day", "limit": "300"}


def test_fetch_symbol_retries_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(data.time, "sleep", lambda s: sleeps.append(s))

    class FlakyTwice:
        def __init__(self):
            self.n = 0

        def get(self, request_path, params):
            self.n += 1
            if self.n < 3:
                raise ConnectionError("proxy hiccup")
            return {"code": "00000", "data": [["1704067200000", "1", "1", "1", "1", "1", "1", "1"]] * 60}

    fc = FlakyTwice()
    rows = fetch_symbol(fc, "RNVDAUSDT")
    assert len(rows) == 60
    assert fc.n == 3
    assert sleeps == [3, 10]            # first retry delay is 0, recorded only for real sleeps


def test_fetch_symbol_gives_up_after_backoff_chain(monkeypatch):
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    fc = FakeClient(fail_symbols={"RBADUSDT"})
    assert fetch_symbol(fc, "RBADUSDT") is None
    assert len(fc.calls) == len(data.RETRY_DELAYS)


def _full_cache(tmp_path, skip=()):
    """Seed a cache covering every symbol with full data, minus `skip`."""
    cache_path = str(tmp_path / "closes_raw.json")
    full = [["1704067200000", "1", "1", "1", "1", "1", "1", "1"]] * 300
    cache = {s: full for s in data.SYMBOLS if s not in skip}
    json.dump(cache, open(cache_path, "w"))
    return cache_path


def test_load_cache_resumes_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    cache_path = _full_cache(tmp_path, skip=("RNVDAUSDT",))
    fc = FakeClient()
    result = load_cache(cache_path, client_factory=lambda: fc)
    assert [c[1]["symbol"] for c in fc.calls] == ["RNVDAUSDT"]   # only the gap filled
    assert "RNVDAUSDT" in result


def test_load_cache_skips_short_data_on_resume(tmp_path, monkeypatch):
    # symbol present in cache with < MIN_DAYS rows must be re-fetched
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    cache_path = _full_cache(tmp_path)
    sym = data.SYMBOLS[0]
    cache = json.load(open(cache_path))
    cache[sym] = cache[sym][:10]
    json.dump(cache, open(cache_path, "w"))
    fc = FakeClient()
    result = load_cache(cache_path, client_factory=lambda: fc)
    assert [c[1]["symbol"] for c in fc.calls] == [sym]           # short data re-fetched
    assert len(result[sym]) == 70
