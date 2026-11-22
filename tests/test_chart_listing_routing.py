import unittest
from unittest.mock import patch

from hyperpass import symbol_search, tradingview_chart
from hyperpass.data_sources import DataSources


class ChartIdentityTests(unittest.TestCase):
    def test_delayed_krx_matches_in_both_directions_without_conflating_us_feeds(self):
        same = tradingview_chart.same_chart_symbol
        self.assertTrue(same("krx:005930", "KRX_DLY:005930"))
        self.assertTrue(same("KRX_DLY:005930", "krx:005930"))
        self.assertFalse(same("NASDAQ:AAPL", "BATS:AAPL"))
        self.assertFalse(same(None, "KRX:005930"))
        self.assertFalse(same("", None))
        self.assertFalse(same("KRX:005930", {}))

    def test_samsung_yahoo_and_delay_feed_share_a_canonical_chart(self):
        for symbol in ("005930.KS", "KRX:005930", "KRX_DLY:005930"):
            self.assertEqual(symbol_search.chart_identity(symbol, {}), {
                "name": "삼성전자", "ticker": "005930", "tradingview": "KRX:005930"})
        self.assertEqual(symbol_search.chart_identity("AAPL", {})["tradingview"], "NASDAQ:AAPL")

    def test_kosdaq_and_us_share_class_use_venue_and_listing_name(self):
        with patch.object(symbol_search, "kr_listings", side_effect=lambda board: (
                 ([("KRX:196170", "알테오젠", "196170.KQ", "ST")] if board == "kosdaq" else []), True)):
            self.assertEqual(symbol_search.chart_identity("196170.KQ", {}), {
                "name":"알테오젠", "ticker":"196170", "tradingview":"KRX:196170"})
        with patch.object(symbol_search, "_us_master", return_value=(
                 [("NYSE:BRK.B", "버크셔 해서웨이 B", "버크셔해서웨이b")], True)):
            self.assertEqual(symbol_search.chart_identity("BRK-B", {"exchange_code":"NYQ"}), {
                "name":"버크셔 해서웨이 B", "ticker":"BRK-B", "tradingview":"NYSE:BRK.B"})

    def test_yahoo_retains_source_bar_with_close_outside_day_range(self):
        service = DataSources()
        valid = {"timestamp":"2024-10-15","open":10,"high":11,"low":9,"close":10,"volume":50}
        invalid = {**valid,"timestamp":"2024-10-14","close":15}
        with patch.object(service, "_fetch_yahoo", return_value={"records":[invalid,valid],"warning":""}):
            packet = service.chart_history("005930.KS")
        self.assertEqual(packet["records"], [valid])
        self.assertEqual(packet["excluded_rows"], [invalid])
        self.assertIn("2024-10-14", packet["warning"])

    def test_unlisted_us_symbol_has_no_guessed_chart_link(self):
        with patch.object(symbol_search, "_us_master", return_value=([],False)):
            self.assertEqual(symbol_search.chart_identity("UNKNW", {"instrument_name":"회사명"}), {
                "name":"회사명","ticker":"UNKNW","tradingview":""})


class DesktopPriceRoutingTests(unittest.TestCase):
    def test_pinned_form_configures_target_and_reads_matching_real_timeframe(self):
        observed = {"connected":True,"target_id":"chart-A","chart":{"symbol":"NASDAQ:AAPL","timeframe":"60"}}
        with patch("hyperpass.tradingview_control.status", return_value=observed) as status, \
                patch("hyperpass.tradingview_control.configure_chart", return_value={
                    "status":"configured","target_id":"chart-A"}) as config, \
                patch.object(tradingview_chart, "fetch_chart", return_value={
                    "timeframe":"D","notes":[""],"observed_symbol":"KRX_DLY:005930"}) as read:
            result=tradingview_chart.fetch_selected_chart(9230,"KRX:005930",150,"chart-A","1D")
        status.assert_called_once_with(9230,"chart-A")
        config.assert_called_once_with(9230,symbol="KRX:005930",timeframe="1D",target_id="chart-A")
        read.assert_called_once_with(9230,"KRX:005930",150,target_id="chart-A")
        self.assertEqual(result["target_id"], "chart-A")

    def test_matching_delayed_listing_is_read_without_reconfiguring(self):
        observed = {"connected":True,"target_id":"chart-B","chart":{"symbol":"KRX_DLY:005930","timeframe":"1D"}}
        with patch("hyperpass.tradingview_control.status", return_value=observed), \
                patch("hyperpass.tradingview_control.configure_chart") as config, \
                patch.object(tradingview_chart, "fetch_chart", return_value={"timeframe":"D","notes":[""]}):
            tradingview_chart.fetch_selected_chart(9230,"KRX:005930",50,"chart-B","1D")
        config.assert_not_called()

    def test_stale_or_unknown_destination_never_configures_another_tab(self):
        with patch("hyperpass.tradingview_control.status", return_value={
                    "connected":True,"target_id":"other","chart":{"symbol":"NASDAQ:AAPL","timeframe":"D"}}), \
                patch("hyperpass.tradingview_control.configure_chart") as config, \
                patch.object(tradingview_chart, "fetch_chart") as read:
            for destination, count in (("chart-A",150),("",150),("chart-A",501)):
                with self.assertRaises(ValueError):
                    tradingview_chart.fetch_selected_chart(9230,"KRX:005930",count,destination,"1D")
        config.assert_not_called()
        read.assert_not_called()
