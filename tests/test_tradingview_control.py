"""Contract and safety tests; simulated CDP fixtures are not market evidence."""
import json
import shutil
import subprocess
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from hyperpass import tradingview_control as tv


TARGET = {"id": "chart-test", "type": "page", "url": "https://www.tradingview.com/chart/Test/",
          "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/chart-test"}
CODE = '//@version=6\nstrategy("Test only")\nplot(close)\n'
CHART = {"symbol": "NASDAQ:AAPL", "timeframe": "1D", "studies": [{"id": "old", "name": "Existing"}]}


class Clock:
    def __init__(self): self.t = 0
    def now(self): self.t += .25; return self.t


class Session:
    def __init__(self, snapshots=None, failure=None):
        self.calls, self.snapshots, self.failure = [], snapshots or [], failure
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def call(self, action, params=None):
        self.calls.append((action, params))
        if action == self.failure: raise tv.ChartControlError("Simulated disconnected chart")
        if action == "status": return {"chart": CHART, "capabilities": {"chart": True}}
        if action == "open_editor": return {"ready": True}
        if action == "editor": return {"ready": True, "source": "ORIGINAL PRIVATE CODE", "uri": "test.pine"}
        if action == "new_script": return {"created": True}
        if action == "set_source": return {"source_matches": True, "previous_source": "DEFAULT TEMPLATE"}
        if action == "compile": return {"triggered": True, "mode": "add"}
        if action == "open_tester": return {"requested": True}
        if action == "run_state":
            return self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]
        raise AssertionError(action)


def snapshot(new=True, errors=None):
    return {"source_matches": True, "chart": CHART, "new_ids": ["new"] if new else [],
            "changed_ids": ["new"] if new else ["old"], "errors": errors or [],
            "reports": [{"study_id": "new" if new else "old", "strategy": "Test only", "available": True,
                         "metrics": {"total_trades": 0, "net_profit": 0}}]}


class ControlTests(unittest.TestCase):
    def run_fixture(self, session, callback=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(tv, "_select", return_value=(TARGET, [TARGET])))
            stack.enter_context(patch.object(tv, "_Session", return_value=session))
            stack.enter_context(patch.object(tv.time, "sleep"))
            stack.enter_context(patch.object(tv.time, "monotonic", side_effect=Clock().now))
            return tv.run_strategy(code=CODE, timeout=5, on_progress=callback)

    def test_new_report_completes_even_with_zero_trades_and_backup_precedes_mutation(self):
        session, callbacks = Session([snapshot()]), []
        def progress(stage, message=None):
            callbacks.append(stage)
            if isinstance(stage, dict):
                self.assertEqual(stage["previous_source"], "ORIGINAL PRIVATE CODE")
                self.assertNotIn("new_script", [x[0] for x in session.calls])
                self.assertNotIn("set_source", [x[0] for x in session.calls])
        result = self.run_fixture(session, progress)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["study_id"], "new")
        self.assertEqual(result["previous_source"], "ORIGINAL PRIVATE CODE")
        self.assertEqual(result["report"]["metrics"]["total_trades"], 0)
        self.assertTrue(any(isinstance(c, dict) and c["stage"] == "backup" for c in callbacks))
        self.assertEqual(next(params for action, params in session.calls if action == "new_script")["backed_up_source"], "ORIGINAL PRIVATE CODE")

    def test_previous_report_even_if_refreshed_never_completes_new_run(self):
        result = self.run_fixture(Session([snapshot(new=False)]))
        self.assertEqual(result["status"], "no_report")
        self.assertIsNone(result["report"])
        self.assertIsNone(result["study_id"])

    def test_compile_failure_preserves_backup_and_never_returns_old_report(self):
        error = {"severity": 8, "line": 3, "column": 1, "message": "Undeclared identifier"}
        result = self.run_fixture(Session([snapshot(new=False, errors=[error])]))
        self.assertEqual(result["status"], "compile_error")
        self.assertEqual(result["compile_errors"], [error])
        self.assertEqual(result["previous_source"], "ORIGINAL PRIVATE CODE")
        self.assertIsNone(result["report"])

    def test_connection_failure_after_replacement_returns_original_backup(self):
        result = self.run_fixture(Session(failure="compile"))
        self.assertEqual(result["status"], "no_report")
        self.assertEqual(result["previous_source"], "ORIGINAL PRIVATE CODE")
        self.assertTrue(result["warnings"])

    def test_backup_persistence_failure_stops_before_replacing_source(self):
        session = Session([snapshot()])
        def progress(stage, message=None):
            if isinstance(stage, dict): raise OSError("disk full")
        with self.assertRaises(OSError): self.run_fixture(session, progress)
        self.assertNotIn("set_source", [x[0] for x in session.calls])
        self.assertFalse(tv._MUTATION_LOCK.locked())

    def test_source_changed_or_ambiguous_new_studies_cannot_complete(self):
        altered = snapshot(); altered["source_matches"] = False
        ambiguous = snapshot(); ambiguous["new_ids"].append("new2")
        ambiguous["reports"].append({"study_id": "new2", "available": True})
        for value in [altered, ambiguous]:
            with self.subTest(value=value):
                result = self.run_fixture(Session([value]))
                self.assertEqual(result["status"], "no_report")
                self.assertIsNone(result["report"])

    def test_runtime_error_is_not_success(self):
        bad = snapshot(); bad["reports"][0]["runtime_status"] = {"type": 3}
        self.assertEqual(self.run_fixture(Session([bad]))["status"], "no_report")

    def test_chart_symbol_change_during_run_cannot_complete(self):
        moved = snapshot(); moved["chart"] = {**CHART, "symbol": "NYSE:MSFT"}
        result = self.run_fixture(Session([moved]))
        self.assertEqual(result["status"], "no_report")
        self.assertIsNone(result["report"])

    def test_untrusted_input_rejected_before_chart_access(self):
        bad_indicators = [[{"name": "RSI", "inputs": {"constructor": 1}}],
                          [{"name": "RSI", "inputs": {"length": float("nan")}}],
                          [{"name": "RSI", "inputs": {"pineId": "anything"}}],
                          [{"name": "RSI", "inputs": {"length": {"unexpected": 1}}}]]
        with patch.object(tv, "_select") as connect:
            for indicators in bad_indicators:
                with self.assertRaises(tv.ChartControlError): tv.configure_chart(indicators=indicators)
            for code in ["", "indicator('not strategy')", "x" * 200001, "strategy('x')\x00"]:
                with self.assertRaises(tv.ChartControlError): tv.run_strategy(code=code)
            with self.assertRaises(tv.ChartControlError): tv.configure_chart(symbol="AAPL';fetch('evil')")
            with self.assertRaises(tv.ChartControlError): tv.configure_chart(timeframe="1D;alert(1)")
            connect.assert_not_called()

    def test_target_allowlist_and_multiple_chart_selection(self):
        self.assertTrue(tv._valid_target(TARGET, 9222))
        for url in ["https://tradingview.com.evil.test/chart/", "https://tradingview.com/chart-evil/",
                    "file:///chart/", "https://user@www.tradingview.com/chart/", "https://www.tradingview.com:9999/chart/"]:
            self.assertFalse(tv._valid_target({**TARGET, "url": url}, 9222))
        self.assertFalse(tv._valid_target({**TARGET, "webSocketDebuggerUrl": "ws://192.168.1.5:9222/devtools/page/abc"}, 9222))
        other = {**TARGET, "id": "other"}
        with patch.object(tv, "_targets", return_value=[TARGET, other]):
            with self.assertRaises(tv.ChartControlError): tv._select(9222)
            self.assertEqual(tv._select(9222, "other")[0]["id"], "other")

    def test_partial_indicator_error_reports_actual_prior_change_without_rollback_deletion(self):
        current = {**CHART, "studies": CHART["studies"] + [{"id": "rsi", "name": "RSI"}]}
        class Partial(Session):
            def call(self, action, params=None):
                self.calls.append((action, params))
                if action == "status": return {"chart": current if any(x[0] == "add_study" for x in self.calls) else CHART}
                if action == "add_study": return {"entity_id": "rsi", "before": ["old"]}
                if action == "set_inputs": return {"error": "unknown_inputs", "unknown": ["bad"]}
                raise AssertionError(action)
        session = Partial()
        with patch.object(tv, "_select", return_value=(TARGET, [TARGET])), patch.object(tv, "_Session", return_value=session):
            result = tv.configure_chart(indicators=[{"name": "RSI", "inputs": {"bad": 14}}])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["changed"][0]["entity_id"], "rsi")
        self.assertIn("old", [x["id"] for x in result["chart"]["studies"]])
        self.assertNotIn("remove", [x[0] for x in session.calls])

    def test_json_report_never_contains_nonfinite_numbers(self):
        value = tv._finite_json({"metrics": {"profit_factor": float("inf"), "ratio": float("nan")}, "values": [1, -float("inf")]})
        json.dumps(value, allow_nan=False)
        self.assertIsNone(value["metrics"]["profit_factor"])

    def test_fixed_program_cannot_invoke_broker_or_save_publish_or_remove(self):
        for forbidden in ("submitOrder", "createOrder", "removeEntity", "localStorage", "document.cookie", "XMLHttpRequest", "fetch("):
            self.assertNotIn(forbidden, tv._PROGRAM)
        with self.assertRaises(tv.ChartControlError):
            tv._Session(TARGET, 9222).call("eval", {"expression": "alert(1)"})

    @unittest.skipUnless(shutil.which("node"), "Node is optional for JavaScript compatibility checks")
    def test_real_report_metric_units_and_literal_pine_insertion(self):
        # Execute the exact fixed page program on an isolated synthetic chart.
        harness = r'''
const execute=PROGRAM;
let source='old';
const ed={getValue:()=>source,setValue:v=>{source=v},focus:()=>{}};
const env={editor:{getEditors:()=>[ed]}};
const container={contains:()=>true,__reactFiber$test:{memoizedProps:{value:{monacoEnv:env}}}};
global.document={querySelector:()=>container};
const strategy={id:()=> 's1',metaInfo:()=>({isTVScriptStrategy:true,description:'Fixture'}),reportData:()=>({currency:'USD',performance:{all:{netProfit:20,netProfitPercent:.2,totalTrades:3,numberOfWiningTrades:1,numberOfLosingTrades:1,percentProfitable:1/3},maxStrategyDrawDownPercent:.1}}),ordersData:()=>[]};
global.window={TradingViewApi:{_activeChartWidgetWV:{value:()=>({_chartWidget:{model:()=>({model:()=>({dataSources:()=>[strategy]}),mainSeries:()=>({symbolInfo:()=>({currency:'USD'})})})},symbol:()=> 'FIXTURE',resolution:()=> '1D',getAllStudies:()=>[]})}}};
(async()=>{
 const code='strategy("x"); global.pwned=true; </script>';
 const set=await execute('set_source',{code,token:'test'});
 if(source!==code || global.pwned || set.previous_source!=='old')throw Error('source interpreted');
 const result=await execute('reports',{});
 const m=result.reports[0].metrics;
 if(m.net_profit_percent!==20 || m.max_drawdown_percent!==10 || m.total_trades!==3 || Math.abs(m.percent_profitable-100/3)>1e-10)throw Error('incorrect units/count');
 if(result.reports[0].performance.all.netProfitPercent!==.2)throw Error('raw report modified');
 console.log('verified');
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace("PROGRAM", "(" + tv._PROGRAM + ")")
        result = subprocess.run(["node"], input=harness, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node is optional for JavaScript compatibility checks")
    def test_unsaved_pine_dialog_requires_exact_backup_before_discard(self):
        harness = r'''
const execute=PROGRAM;
global.setTimeout=fn=>{fn();return 0};
async function run(changed) {
 let source='backed-up original', pending=true, created=false, cancelled=0, discarded=0;
 const ed={getValue:()=>source,getModel:()=>({uri:'unchanged-editor-uri'})};
 const env={editor:{getEditors:()=>[ed]}};
 const container={contains:()=>true,__reactFiber$test:{memoizedProps:{value:{monacoEnv:env}}}};
 const cancel={click:()=>{pending=false;cancelled++}};
 const discard={click:()=>{pending=false;created=true;source='strategy("new template")';discarded++}};
 const dialog={textContent:'전환하기 전에 스크립트를 저장하시겠습니까?',querySelector:s=>s.includes('dontSave-btn')?discard:s.includes('cancel-btn')?cancel:null};
 const title={getAttribute:()=> 'false',click:()=>{}};
 const add={textContent:'차트에 넣기',disabled:false};
 const item={textContent:'새로 만들기',focus:()=>{},dispatchEvent:()=>{}};
 const strategy={textContent:'전략Ctrl + K, Ctrl + S',getAttribute:()=>null,click:()=>{pending=true;if(changed)source='USER EDIT AFTER BACKUP'}};
 global.KeyboardEvent=class {};
 global.document={querySelector:s=>s.includes('monaco-editor')?container:s.includes('warning-dialog')?(pending?dialog:null):s.includes('pine-script-title-button')?title:s.includes('add-script-to-chart')?(created?add:null):null,querySelectorAll:()=>[item,strategy]};
 global.window={TradingViewApi:{_activeChartWidgetWV:{value:()=>({})}}};
 const result=await execute('new_script',{backed_up_source:'backed-up original'});
 if(cancelled!==1)throw Error('stale pending navigation not cancelled');
 if(changed) {if(result.error!=='source_changed_before_new_script' || discarded!==0)throw Error('unbacked edit discarded');}
 else {if(!result.created || discarded!==1)throw Error('backed-up draft did not reach new document');}
}
(async()=>{await run(false);await run(true);console.log('verified')})().catch(e=>{console.error(e);process.exit(1)});
'''.replace("PROGRAM", "(" + tv._PROGRAM + ")")
        result = subprocess.run(["node"], input=harness, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified", result.stdout)


if __name__ == "__main__":
    unittest.main()
