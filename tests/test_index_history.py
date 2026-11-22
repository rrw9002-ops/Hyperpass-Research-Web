import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from hyperpass import index_history as history
from hyperpass.chart_lab import market_index


class IndexHistoryTests(unittest.TestCase):
    def setUp(self):
        self.sources = Mock()
        self.sources.chart_history.side_effect = ValueError("Yahoo limit")
        self.today = datetime.now(timezone.utc).date()
        self.first = self.today - timedelta(days=2)

    def fred(self, series="SP500"):
        return f"observation_date,{series}\n{self.first},5000\n{self.today-timedelta(days=1)},.\n{self.today},5010\n".encode()

    def test_fred_holiday_cache_and_offline_last_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(history, "_read", return_value=self.fred()) as remote:
                result = market_index(self.sources, "^GSPC", directory)
                self.assertEqual((result["provider"], result["cache_status"], result["as_of"]), ("FRED", "live", self.today.isoformat()))
                self.assertEqual([row["close"] for row in result["series"]], [5000,5010])
                self.assertEqual(result["source_url"], "https://fred.stlouisfed.org/series/SP500")
                again = market_index(self.sources, "^GSPC", directory)
                self.assertEqual(again["cache_status"], "fresh_cache")
                remote.assert_called_once()
                self.sources.chart_history.assert_called_once()
            path = Path(directory) / "GSPC.json"
            saved = json.loads(path.read_text(encoding="utf8"))
            saved["retrieved_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            path.write_text(json.dumps(saved), encoding="utf8")
            with patch.object(history, "_read", side_effect=TimeoutError):
                stale = market_index(self.sources, "^GSPC", directory)
            self.assertEqual(stale["cache_status"], "stale_cache")
            self.assertEqual(stale["series"], result["series"])
            self.assertEqual(stale["retrieved_at"], saved["retrieved_at"])

    def test_naver_requires_requested_symbol_and_reads_close_column(self):
        rows = "".join(f'<item data="{day:%Y%m%d}|1|3|1|{close}|150" />' for day,close in ((self.first,2),(self.today,2.5)))
        document = ('<?xml version="1.0" encoding="EUC-KR" ?><protocol><chartdata symbol="KOSPI" name="코스피" timeframe="day">'+rows+'</chartdata></protocol>').encode("cp949")
        with patch.object(history, "_read", return_value=document):
            result = market_index(self.sources, "^KS11")
            self.assertEqual(result["provider"], "Naver 금융")
            self.assertEqual(result["series"][-1]["close"], 2.5)
            with self.assertRaisesRegex(ValueError, "보조 제공처"):
                market_index(self.sources, "^KQ11")

    def test_wrong_fred_series_and_future_cache_do_not_become_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(history,"_read",return_value=self.fred()):
                market_index(self.sources, "^GSPC", directory)
            path = Path(directory) / "GSPC.json"
            saved = json.loads(path.read_text(encoding="utf8"))
            saved["retrieved_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            path.write_text(json.dumps(saved), encoding="utf8")
            with patch.object(history,"_read",return_value=self.fred("DJIA")):
                with self.assertRaisesRegex(ValueError, "보조 제공처"):
                    market_index(self.sources, "^GSPC", directory)
        with self.assertRaisesRegex(ValueError, "선택"):
            market_index(self.sources, "AAPL")

    def test_calendar_window_crosses_year_and_month_end(self):
        self.assertEqual(history._window(date(2026,1,31)), date(2025,10,31))
        self.assertEqual(history._window(date(2026,5,31)), date(2026,2,28))


if __name__ == "__main__":
    unittest.main()
