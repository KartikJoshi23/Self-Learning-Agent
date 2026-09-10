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
        daily = power.daily_summary(frame, complete_days_only=False)
        assert set(daily.columns) == {"ALLSKY_SFC_SW_DWN", "AOD_55"}
        assert daily["AOD_55"].dropna().tolist() == pytest.approx([0.3] * 3)
        assert daily.index.name == "date_local"

    def test_partial_local_days_are_dropped_by_default(self):
        """The UTC->local shift truncates the first day and invents a phantom
        day in the next calendar year. Neither may reach the daily frame."""
        # 48 UTC hours starting 2020-01-01 00:00Z spans three local days in
        # Dubai (UTC+4): a 20-hour day, a full day, and a 4-hour phantom.
        frame = power._parse_response(_payload(year=2020, hours=48))

        kept_all = power.daily_summary(frame, complete_days_only=False)
        assert len(kept_all) == 3

        daily = power.daily_summary(frame)
        assert len(daily) == 1, "only the one complete local day should survive"
        assert daily.index[0].date().isoformat() == "2020-01-02"

    def test_complete_days_only_leaves_no_spurious_year(self):
        """A phantom day would leak an extra year into any groupby."""
        frame = power._parse_response(_payload(year=2020, hours=48))
        years = set(power.daily_summary(frame).index.year)
        assert years == {2020}

        leaky = set(power.daily_summary(frame, complete_days_only=False).index.year)
        assert 2020 in leaky  # the unfiltered frame is where the phantom lives


@pytest.mark.network
class TestLiveApi:
    """Guards the two API constraints M0 established empirically."""

    def test_single_year_request_returns_a_full_year(self):
        """The API-shape invariant: one year of all nine parameters comes back
        complete.

        Deliberately checks the raw response rather than ``fetch_year``, which
        also validates the *values*. Those are separate concerns, and conflating
        them makes this test fail whenever an upstream parameter is faulty --
        which says nothing about whether a one-year request fits the payload
        cap. ``TestFillValues`` covers value quality.
        """
        response = self._raw(
            ",".join(power.DATA.power_parameters), "20200101", "20201231"
        )
        assert response.status_code == 200
        frame = power._parse_response(response.json())
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

    def test_daily_rainfall_matches_the_power_daily_product(self, tmp_path):
        """Hourly PRECTOTCORR is a mm/day rate, so it must be averaged.

        POWER's own daily product is the ground truth. If daily_summary ever
        goes back to summing, this diverges by a factor of 24.
        """
        response = power.requests.get(
            "https://power.larc.nasa.gov/api/temporal/daily/point",
            params={
                "parameters": "PRECTOTCORR",
                "community": "RE",
                "latitude": MBR_SOLAR_PARK.latitude,
                "longitude": MBR_SOLAR_PARK.longitude,
                "start": "20200101",
                "end": "20201231",
                "format": "JSON",
            },
            timeout=power.REQUEST_TIMEOUT_S,
        )
        assert response.ok
        reference = pd.Series(
            response.json()["properties"]["parameter"]["PRECTOTCORR"]
        ).replace(power.FILL_VALUE, float("nan"))
        assert reference.sum() > 0, "the daily product itself looks unusable"

        # Checked against the project's cached data rather than a fresh fetch.
        # The hourly endpoint has been observed serving this one parameter as
        # roughly -99,000 while the daily product stayed correct, and a test
        # that fails on an upstream fault teaches nothing. TestFillValues covers
        # our handling of that fault directly.
        ours = power.daily_summary(power.fetch_year(2020))["PRECTOTCORR"]

        # Compared as annual totals; the UTC->local shift moves a few hours
        # across day boundaries, so daily rows will not match exactly.
        assert ours.sum() == pytest.approx(reference.sum(), rel=0.02)


class TestFillValues:
    """Guarding a silent-corruption path.

    Observed 2026-09-10: the hourly endpoint returned PRECTOTCORR around
    -99,000 for every hour of 2020 while every other parameter was healthy and
    the daily product was correct. That is not the documented -999 sentinel, so
    it passed straight through the parser. Rainfall drives the natural-cleaning
    resets, so a fresh clone would have run the whole soiling model with no rain
    washes at all and produced quietly wrong results rather than an error.
    """

    @staticmethod
    def _fill_payload(value: float, hours: int = 48) -> dict:
        stamps = pd.date_range("2020-01-01", periods=hours, freq="h")
        keys = [t.strftime("%Y%m%d%H") for t in stamps]
        return {
            "properties": {
                "parameter": {
                    "PRECTOTCORR": {k: value for k in keys},
                    "ALLSKY_SFC_SW_DWN": {k: 500.0 for k in keys},
                }
            }
        }

    def test_documented_sentinel_is_rejected(self):
        frame = power._parse_response(self._fill_payload(power.FILL_VALUE))
        assert frame["PRECTOTCORR"].isna().all()

    def test_undocumented_negative_fill_is_also_rejected(self):
        """The actual failure: a large negative that is not -999."""
        frame = power._parse_response(self._fill_payload(-99000.0))
        assert frame["PRECTOTCORR"].isna().all()

    def test_any_negative_rainfall_is_rejected(self):
        frame = power._parse_response(self._fill_payload(-0.5))
        assert frame["PRECTOTCORR"].isna().all()

    def test_valid_rainfall_survives(self):
        frame = power._parse_response(self._fill_payload(3.25))
        assert (frame["PRECTOTCORR"] == 3.25).all()

    def test_validate_raises_and_names_the_parameter(self):
        frame = power._parse_response(self._fill_payload(-99000.0))
        with pytest.raises(power.PowerFetchError, match="PRECTOTCORR"):
            power._validate(frame, 2020)

    def test_validate_accepts_a_healthy_frame(self):
        power._validate(power._parse_response(self._fill_payload(1.0)), 2020)

    def test_a_bad_fetch_is_never_cached(self, tmp_path, monkeypatch):
        """A corrupt year must not reach disk, or it poisons every later
        offline run."""
        payload = self._fill_payload(-99000.0)

        class Response:
            ok = True
            status_code = 200

            @staticmethod
            def json():
                return payload

        monkeypatch.setattr(power.requests, "get", lambda *a, **k: Response())
        with pytest.raises(power.PowerFetchError):
            power.fetch_year(
                2020,
                parameters=("PRECTOTCORR", "ALLSKY_SFC_SW_DWN"),
                cache_dir=tmp_path,
            )
        assert not list(tmp_path.glob("*.parquet")), "a bad fetch was cached"
