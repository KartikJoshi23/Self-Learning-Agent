"""Tests for the NASA POWER data layer.

Everything here runs offline except the tests marked ``network``. The offline
tests are the ones that matter for M0's "idempotent and offline-replayable"
acceptance criterion.
"""

from __future__ import annotations

import pandas as pd
import pytest

from rimal.config import MBR_SOLAR_PARK
from rimal.data import power


def _payload(year: int = 2020, hours: int = 48) -> dict:
    """A minimal NASA POWER JSON payload, including a -999 fill value."""
    stamps = pd.date_range(f"{year}-01-01", periods=hours, freq="h")
    keys = [t.strftime("%Y%m%d%H") for t in stamps]
    ghi = {k: float(i) for i, k in enumerate(keys)}
    aod = {k: 0.3 for k in keys}
    # One missing observation, expressed the way POWER expresses it.
    ghi[keys[3]] = power.FILL_VALUE
    return {"properties": {"parameter": {"ALLSKY_SFC_SW_DWN": ghi, "AOD_55": aod}}}


class TestParseResponse:
    def test_index_is_utc_hourly(self):
        frame = power._parse_response(_payload())
        assert isinstance(frame.index, pd.DatetimeIndex)
        assert str(frame.index.tz) == "UTC"
        assert frame.index.is_monotonic_increasing
        assert (frame.index[1] - frame.index[0]) == pd.Timedelta(hours=1)

    def test_fill_value_becomes_missing(self):
        frame = power._parse_response(_payload())
        assert frame["ALLSKY_SFC_SW_DWN"].isna().sum() == 1
        # The sentinel must not survive into the data.
        assert not (frame == power.FILL_VALUE).any().any()

    def test_empty_parameters_rejected(self):
        with pytest.raises(power.PowerFetchError):
            power._parse_response({"properties": {"parameter": {}}})

    def test_malformed_payload_rejected(self):
        with pytest.raises(power.PowerFetchError):
            power._parse_response({"nonsense": True})


class TestCaching:
    def test_writes_then_reads_without_network(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        class Response:
            ok = True
            status_code = 200

            @staticmethod
            def json():
                return _payload()

        def fake_get(*args, **kwargs):
            calls["n"] += 1
            return Response()

        monkeypatch.setattr(power.requests, "get", fake_get)
        params = ("ALLSKY_SFC_SW_DWN", "AOD_55")

        first = power.fetch_year(2020, parameters=params, cache_dir=tmp_path)
        assert calls["n"] == 1

        # Second call must be served from cache: no further network calls.
        def explode(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("network was used despite a warm cache")

        monkeypatch.setattr(power.requests, "get", explode)
        second = power.fetch_year(2020, parameters=params, cache_dir=tmp_path)

        pd.testing.assert_frame_equal(first, second)
        assert power._cache_path(MBR_SOLAR_PARK, 2020, tmp_path).exists()

    def test_http_error_raises(self, tmp_path, monkeypatch):
        class Response:
            ok = False
            status_code = 422
            text = "please shorten your requested time extent"

        monkeypatch.setattr(power.requests, "get", lambda *a, **k: Response())
        with pytest.raises(power.PowerFetchError, match="422"):
            power.fetch_year(2020, cache_dir=tmp_path)

    def test_missing_requested_parameter_raises(self, tmp_path, monkeypatch):
        class Response:
            ok = True
            status_code = 200

            @staticmethod
            def json():
                return _payload()

        monkeypatch.setattr(power.requests, "get", lambda *a, **k: Response())
        # Ask for a parameter the payload does not contain.
        with pytest.raises(power.PowerFetchError, match="omitted"):
            power.fetch_year(
                2020, parameters=("ALLSKY_SFC_SW_DWN", "T2M"), cache_dir=tmp_path
            )


class TestFetchYears:
    def test_reversed_range_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            power.fetch_years(2021, 2020, cache_dir=tmp_path)

    def test_chunks_concatenate_without_duplicates(self, tmp_path, monkeypatch):
        def fake_get(*args, **kwargs):
            year = int(kwargs["params"]["start"][:4])

            class Response:
                ok = True
                status_code = 200

                @staticmethod
                def json():
                    return _payload(year=year)

            return Response()

        monkeypatch.setattr(power.requests, "get", fake_get)
        frame = power.fetch_years(
            2019, 2021, parameters=("ALLSKY_SFC_SW_DWN", "AOD_55"), cache_dir=tmp_path
        )
        assert not frame.index.duplicated().any()
        assert frame.index.is_monotonic_increasing
        assert frame.index.year.nunique() == 3


class TestDerived:
    def test_to_local_shifts_to_gulf_standard_time(self):
        frame = power._parse_response(_payload())
        local = power.to_local(frame)
        assert "Asia/Dubai" in str(local.index.tz)
        # Dubai is UTC+4 year round; no DST.
        assert local.index[0].hour == (frame.index[0].hour + 4) % 24

    def test_daily_summary_sums_irradiance_and_averages_drivers(self):
        frame = power._parse_response(_payload(hours=48))
        daily = power.daily_summary(frame)
        assert set(daily.columns) == {"ALLSKY_SFC_SW_DWN", "AOD_55"}
        assert daily["AOD_55"].dropna().tolist() == pytest.approx([0.3] * 3)
        assert daily.index.name == "date_local"


@pytest.mark.network
class TestLiveApi:
    """Guards the two API constraints M0 established empirically."""

    def test_single_year_succeeds(self, tmp_path):
        frame = power.fetch_year(2020, cache_dir=tmp_path)
        assert len(frame) == 8784  # 2020 was a leap year
        assert set(frame.columns) >= set(power.DATA.power_parameters)

    @staticmethod
    def _raw(parameters: str, start: str, end: str):
        return power.requests.get(
            power.POWER_HOURLY_URL,
            params={
                "parameters": parameters,
                "community": "RE",
                "latitude": MBR_SOLAR_PARK.latitude,
                "longitude": MBR_SOLAR_PARK.longitude,
                "start": start,
                "end": end,
                "format": "JSON",
            },
            timeout=power.REQUEST_TIMEOUT_S,
        )

    def test_payload_cap_is_parameters_times_years(self):
        """The hourly JSON cap is on payload size, not span.

        Chunking one year at a time (9 parameter-years) is the mitigation. If
        this test starts failing because the large request now succeeds, the
        cap has been raised and fetch_years() chunking could be relaxed.
        """
        full = ",".join(power.DATA.power_parameters)
        assert self._raw(full, "20180101", "20221231").status_code == 422  # 9 x 5
        assert self._raw(full, "20180101", "20201231").status_code == 200  # 9 x 3

    def test_one_year_chunk_is_well_inside_the_cap(self):
        full = ",".join(power.DATA.power_parameters)
        assert self._raw(full, "20200101", "20201231").status_code == 200  # 9 x 1
