from __future__ import annotations

import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from hyperpass.engine import DemoProvider, Engine, OpenAIProvider, ProviderError, SPECIALIST_ROLES
from hyperpass.provider import _open

ROOT = Path(__file__).resolve().parents[1]


class Scripted(DemoProvider):
    def __init__(self, edit=None):
        self.edit = edit
        self.seen = []
        self.lock = threading.Lock()

    def complete(self, instructions, payload, *, schema=None, web_search=False):
        with self.lock:
            self.seen.append({"instructions": instructions, "payload": payload, "web_search": web_search})
            if payload["stage"] == "task_correction":
                # A correction is deliberately unchanged unless this case's
                # explicit fixture supplies a corrected model response.
                result = {"data": {"tasks": [{**task, "input_ids": list(task["input_ids"])} for task in payload["original_tasks"]],
                                   "reason": "Fixture retained the original tasks."}, "usage": {}}
            else:
                result = super().complete(instructions, payload, schema=schema, web_search=web_search)
            if self.edit:
                self.edit(payload, result["data"])
            return result


class EngineTests(unittest.TestCase):
    def run_engine(self, provider=None, **kwargs):
        events = []
        provider = provider or Scripted()
        engine = Engine(provider, events.append, lambda: False, ROOT)
        return engine.run("제공 자료로 사업 품질을 검토하세요.", evidence="fixture", **kwargs), events, provider

    def test_real_workflow_structure_demo_explicit_and_isolated(self):
        result, events, provider = self.run_engine()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["usage"]["calls"], 5)
        fundamental, reviewer = result["artifacts"]
        self.assertNotEqual(fundamental["owner_id"], reviewer["owner_id"])
        self.assertEqual(reviewer["input_ids"], [fundamental["id"]])
        self.assertTrue(result["reviews"]["judgment-reviewer"])
        self.assertIn("AI 분석 아님", result["report"])
        review_call = next(c for c in provider.seen if c["payload"].get("role") == "judgment-reviewer")
        self.assertFalse(review_call["web_search"])
        self.assertEqual(review_call["payload"]["provided_evidence"], "")
        self.assertEqual(review_call["payload"]["prior_own_versions"], [])
        self.assertIn("# Agent Judgment Review", review_call["instructions"])
        self.assertEqual([e["type"] for e in events].count("artifact"), 2)

    def test_budget_cannot_skip_independent_review(self):
        result, _, _ = self.run_engine(max_calls=4)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertFalse(result["reviews"]["judgment-reviewer"])
        self.assertIn("미완료", result["report"])

    def test_invalid_role_never_dispatched(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"][0]["role"] = "../../execute-order"
        result, _, provider = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(provider.seen), 1)
        self.assertEqual(result["artifacts"], [])

    def test_unknown_or_unaccepted_input_is_rejected(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"][0]["input_ids"] = ["fabricated-receipt"]
        result, _, _ = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["usage"]["calls"], 2)
        self.assertEqual(result["artifacts"], [])

    def test_first_task_keeps_source_attachment_with_empty_artifact_input_ids(self):
        evidence = json.dumps({"provider": "tradingview_strategy_tester", "report_id": "9" * 32,
                               "symbol": "TEST", "metrics": {"total_trades": 2}})
        provider = Scripted()
        result = Engine(provider, lambda event: None, lambda: False, ROOT).run(
            "제공한 차트 보고서의 한계를 검토하세요.", evidence=evidence,
            target_role="technical-analyst", web_search=False)
        self.assertEqual(result["status"], "completed")
        head = provider.seen[0]
        self.assertIn('every delegated task MUST have `"input_ids": []`', head["instructions"])
        self.assertIn("At initial stage=plan, every task MUST use input_ids: []", head["instructions"])
        producer = next(call for call in provider.seen if call["payload"].get("role") == "technical-analyst")
        self.assertEqual(producer["payload"]["provided_evidence"], evidence)
        self.assertEqual(result["artifacts"][0]["input_ids"], [])
        reviewer = next(call for call in provider.seen if call["payload"].get("role") == "judgment-reviewer")
        self.assertEqual(reviewer["payload"]["provided_evidence"], "")
        self.assertEqual([item["id"] for item in reviewer["payload"]["accepted_inputs"]], ["technical-analyst-v1"])
        self.assertTrue(result["reviews"]["judgment-reviewer"])

    def test_source_report_id_in_evidence_never_becomes_an_accepted_artifact_id(self):
        source_id = "9" * 32
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"][0]["input_ids"] = [source_id]
        provider = Scripted(edit)
        result = Engine(provider, lambda event: None, lambda: False, ROOT).run(
            "첨부 보고서를 검토하세요.", evidence=json.dumps({"report_id": source_id}))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["usage"]["calls"], 2)
        self.assertEqual(result["artifacts"], [])
        self.assertFalse(result["report_complete"])

    def test_initial_duplicate_tasks_are_corrected_by_head_before_any_specialist(self):
        for target in (None, "technical-analyst"):
            role = target or "fundamental-analyst"
            first_question, second_question = "첫 번째 근거를 확인하세요.", "두 번째 반대 근거를 확인하세요."
            def edit(payload, data):
                if payload["stage"] == "plan":
                    data["tasks"] = [{"role": role, "question": question, "input_ids": []}
                                     for question in (first_question, second_question)]
                if payload["stage"] == "task_correction":
                    self.assertEqual(engine.artifacts, [])
                    self.assertEqual(engine.deferred_reviews, {})
                    self.assertEqual(payload["required_roles"], [role])
                    self.assertEqual([task["question"] for task in payload["original_tasks"]], [first_question, second_question])
                    data["tasks"] = [{"role": role, "question": first_question + " " + second_question, "input_ids": []}]
                    data["reason"] = "같은 담당자가 원래 두 질문을 함께 검토하도록 명시적으로 보정합니다."
            provider = Scripted(edit)
            events = []
            engine = Engine(provider, events.append, lambda: False, ROOT)
            with self.subTest(target=target):
                result = engine.run("두 근거를 함께 검토하세요.", evidence="fixture", target_role=target)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["usage"]["calls"], 6)
                self.assertEqual([call["payload"]["stage"] for call in provider.seen[:3]], ["plan", "task_correction", "specialist"])
                self.assertEqual([a["role"] for a in result["artifacts"]], [role, "judgment-reviewer"])
                correction = next(event for event in events if event["type"] == "task_correction")
                self.assertEqual(len(correction["original_tasks"]), 2)
                self.assertEqual(correction["tasks"][0]["question"], first_question + " " + second_question)

    def test_duplicate_followup_correction_preserves_owner_and_latest_review(self):
        def edit(payload, data):
            if payload["stage"] == "reassess" and payload["pending"][0]["id"] == "fundamental-analyst-v1":
                data["next_action"] = "delegate"
                data["tasks"] = [{"role": "fundamental-analyst", "question": question, "input_ids": ["fundamental-analyst-v1"]}
                                 for question in ("현금 전환을 보완하세요.", "반대 가설을 보완하세요.")]
            if payload["stage"] == "task_correction":
                self.assertEqual(payload["accepted_input_ids"], ["fundamental-analyst-v1"])
                data["tasks"] = [{"role": "fundamental-analyst", "question": "현금 전환과 반대 가설을 보완하세요.",
                                  "input_ids": ["fundamental-analyst-v1"]}]
                data["reason"] = "원래 보완 질문 둘을 같은 담당자의 한 작업으로 묶습니다."
        result, _, provider = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["usage"]["calls"], 8)
        first, revised, review = result["artifacts"]
        self.assertEqual(first["owner_id"], revised["owner_id"])
        self.assertEqual(review["input_ids"], ["fundamental-analyst-v2"])
        self.assertEqual(len([call for call in provider.seen if call["payload"]["stage"] == "task_correction"]), 1)

    def test_repeated_task_shape_error_blocks_before_dispatch_or_role_state_mutation(self):
        for fault in ("duplicate", "reference"):
            def edit(payload, data):
                if payload["stage"] != "plan":
                    return
                first = {"role": "portfolio-manager", "question": "제공된 노출만 검토하세요.", "input_ids": []}
                if fault == "reference":
                    first["input_ids"] = ["unaccepted-source-id"]
                data["tasks"] = [first]
                if fault == "duplicate":
                    data["tasks"].append({"role": "portfolio-manager", "question": "제공된 집중도만 검토하세요.", "input_ids": []})
                data["tasks"].append({"role": "risk-manager", "question": "근거 채택 후 독립 검토", "input_ids": []})
            provider = Scripted(edit)  # Its correction deliberately repeats the fault.
            engine = Engine(provider, lambda event: None, lambda: False, ROOT)
            with self.subTest(fault=fault):
                result = engine.run("제공된 포트폴리오 검토", evidence="fixture")
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["usage"]["calls"], 2)
                self.assertEqual(result["artifacts"], [])
                self.assertEqual(engine.owners, {})
                self.assertEqual(engine.deferred_reviews, {})
                self.assertFalse(engine.require_risk)
                self.assertEqual([call["payload"]["stage"] for call in provider.seen], ["plan", "task_correction"])

    def test_head_can_correct_source_reference_without_losing_provided_evidence(self):
        evidence = json.dumps({"report_id": "raw-source-id", "observations": ["fixture"]})
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"][0]["input_ids"] = ["raw-source-id"]
            if payload["stage"] == "task_correction":
                self.assertEqual(payload["accepted_input_ids"], [])
                self.assertEqual(payload["provided_evidence"], evidence)
                data["tasks"] = [{"role": "fundamental-analyst", "question": "제공된 raw-source-id 원자료를 검토하세요.", "input_ids": []}]
                data["reason"] = "원자료는 provided_evidence로 전달되며 채택된 전문 산출물이 아니므로 원자료 ID를 질문에 명시합니다."
        provider = Scripted(edit)
        result = Engine(provider, lambda event: None, lambda: False, ROOT).run("첨부 검토", evidence=evidence)
        self.assertEqual(result["status"], "completed")
        producer = next(call for call in provider.seen if call["payload"].get("role") == "fundamental-analyst")
        self.assertEqual(producer["payload"]["provided_evidence"], evidence)
        self.assertEqual(producer["payload"]["accepted_inputs"], [])
        self.assertEqual(result["artifacts"][0]["input_ids"], [])
        self.assertTrue(result["reviews"]["judgment-reviewer"])

    def test_task_correction_cannot_add_remove_or_exchange_roles(self):
        for change in ("add", "remove", "exchange", "unknown"):
            def edit(payload, data):
                if payload["stage"] == "plan":
                    data["tasks"] = [{"role": "fundamental-analyst", "question": question, "input_ids": []}
                                     for question in ("사업 확인", "현금 전환 확인")]
                    if change == "remove":
                        data["tasks"].append({"role": "news-analyst", "question": "관련 뉴스 확인", "input_ids": []})
                if payload["stage"] == "task_correction":
                    data["tasks"] = [{"role": "fundamental-analyst", "question": "사업과 현금 전환 확인", "input_ids": []}]
                    if change == "add":
                        data["tasks"].append({"role": "news-analyst", "question": "새 뉴스 작업", "input_ids": []})
                    if change in ("exchange", "unknown"):
                        data["tasks"][0]["role"] = "technical-analyst" if change == "exchange" else "execute-order"
                    data["reason"] = "Fixture attempts an unauthorized role change."
            with self.subTest(change=change):
                result, _, provider = self.run_engine(Scripted(edit))
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["usage"]["calls"], 2)
                self.assertEqual(result["artifacts"], [])
                self.assertFalse(any(call["payload"]["stage"] == "specialist" for call in provider.seen))

    def test_task_correction_uses_budget_without_skipping_review(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"] *= 2
            if payload["stage"] == "task_correction":
                data["tasks"] = [data["tasks"][0]]
                data["reason"] = "중복된 동일 질문을 같은 담당자의 한 작업으로 보정합니다."
        result, _, provider = self.run_engine(Scripted(edit), max_calls=4)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["usage"]["calls"], 4)
        self.assertFalse(result["report_complete"])
        self.assertFalse(result["reviews"]["judgment-reviewer"])
        self.assertEqual(len(provider.seen), 4)

    def test_task_correction_never_exceeds_an_already_exhausted_budget(self):
        def edit(payload, data):
            if payload["stage"] == "reassess" and payload["pending"][0]["role"] == "judgment-reviewer":
                data["next_action"] = "delegate"
                data["tasks"] = [{"role": "fundamental-analyst", "question": "같은 담당자의 보완", "input_ids": []}] * 2
        result, _, provider = self.run_engine(Scripted(edit), max_calls=5)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["usage"]["calls"], 5)
        self.assertEqual(len(provider.seen), 5)
        self.assertFalse(any(call["payload"]["stage"] == "task_correction" for call in provider.seen))
        self.assertEqual([a["id"] for a in result["artifacts"]], ["fundamental-analyst-v1", "judgment-reviewer-v1"])

    def test_wrong_task_schema_is_not_sent_for_shape_correction(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"][0]["input_ids"] = "not-an-array"
        result, _, provider = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(provider.seen), 1)
        self.assertEqual(result["artifacts"], [])

    def test_reassessment_repairs_cumulative_acceptance_ids_once_without_applying_bad_decision(self):
        events = []
        prior_draft = []
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["require_risk"] = True
            if payload["stage"] != "reassess" or payload["pending"][0]["role"] != "risk-manager":
                return
            if "acceptance_reference_feedback" not in payload:
                prior_draft.append(engine.draft)
                data["acceptances"].append({"artifact_id": "technical-analyst-v1", "state": "blocked", "reason": "invalid cumulative row"})
                data["conclusion"] = "REJECTED CANDIDATE MUST NOT BE APPLIED"
                data["evidence_readiness"] = "decision-grade"
            else:
                self.assertEqual(engine.draft, prior_draft[0])
                self.assertEqual(payload["candidate_report"], prior_draft[0])
                self.assertEqual([a["state"] for a in engine.artifacts], ["accepted", "pending"])
                feedback = payload["acceptance_reference_feedback"]
                self.assertEqual(feedback["expected_artifact_ids"], ["risk-manager-v1"])
                self.assertEqual(feedback["received_artifact_ids"], ["risk-manager-v1", "technical-analyst-v1"])
        provider = Scripted(edit)
        engine = Engine(provider, events.append, lambda: False, ROOT)
        result = engine.run("제공 자료의 위험을 검토하세요.", evidence="fixture", target_role="technical-analyst")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["usage"]["calls"], 8)
        self.assertTrue(result["reviews"]["risk-manager"])
        self.assertTrue(result["reviews"]["judgment-reviewer"])
        self.assertNotIn("REJECTED CANDIDATE", result["report"])
        corrections = [call for call in provider.seen if "acceptance_reference_feedback" in call["payload"]]
        self.assertEqual(len(corrections), 1)
        self.assertEqual(corrections[0]["payload"]["remaining_calls"], 7)
        warnings = [event for event in events if event["type"] == "acceptance_reference_error"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["received_artifact_ids"], ["risk-manager-v1", "technical-analyst-v1"])

    def test_repeated_acceptance_id_errors_block_without_partial_state_changes(self):
        for fault in ("missing", "duplicate", "unexpected"):
            events = []
            def edit(payload, data):
                if payload["stage"] != "reassess":
                    return
                if fault == "missing":
                    data["acceptances"] = []
                elif fault == "duplicate":
                    data["acceptances"] *= 2
                else:
                    data["acceptances"][0]["artifact_id"] = "unaccepted-source-id"
                data["conclusion"] = "REJECTED CANDIDATE"
                data["require_risk"] = True
                data["evidence_readiness"] = "decision-grade"
            provider = Scripted(edit)
            engine = Engine(provider, events.append, lambda: False, ROOT)
            with self.subTest(fault=fault):
                result = engine.run("fixture research", evidence="fixture")
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["usage"]["calls"], 4)
                self.assertEqual(result["artifacts"][0]["state"], "pending")
                self.assertEqual(engine.draft, "")
                self.assertFalse(engine.require_risk)
                self.assertEqual(engine.readiness, "insufficient")
                self.assertFalse(any(event["type"] == "acceptance" for event in events))
                self.assertEqual(len([event for event in events if event["type"] == "acceptance_reference_error"]), 2)
                self.assertIn("expected=", result["reason"])
                self.assertIn("received=", result["reason"])

    def test_acceptance_correction_counts_against_existing_call_budget(self):
        def edit(payload, data):
            if payload["stage"] == "reassess" and "acceptance_reference_feedback" not in payload:
                data["acceptances"] = []
        result, _, provider = self.run_engine(Scripted(edit), max_calls=4)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["usage"]["calls"], 4)
        self.assertFalse(result["report_complete"])
        self.assertFalse(result["reviews"]["judgment-reviewer"])
        self.assertFalse(any(call["payload"].get("role") == "judgment-reviewer" for call in provider.seen))

    def test_acceptance_error_at_call_limit_does_not_send_an_extra_request(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"].append({"role": "news-analyst", "question": "독립 뉴스 확인", "input_ids": []})
            if payload["stage"] == "reassess":
                data["acceptances"] = []
        result, events, provider = self.run_engine(Scripted(edit), max_calls=4)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["usage"]["calls"], 4)
        self.assertEqual(len(provider.seen), 4)
        self.assertTrue(all(artifact["state"] == "pending" for artifact in result["artifacts"]))
        self.assertFalse(any("acceptance_reference_feedback" in call["payload"] for call in provider.seen))
        warning = next(event for event in events if event["type"] == "acceptance_reference_error")
        self.assertEqual(warning["status"], "budget_exhausted")

    def test_acceptance_correction_cannot_overrule_independent_revise_or_block(self):
        for verdict in ("revise", "blocked"):
            def edit(payload, data):
                if payload["stage"] == "specialist" and payload["role"] == "judgment-reviewer":
                    data["review_verdict"] = verdict
                if (payload["stage"] == "reassess" and payload["pending"][0]["role"] == "judgment-reviewer"
                        and "acceptance_reference_feedback" not in payload):
                    data["acceptances"].append({"artifact_id": "fundamental-analyst-v1", "state": "accepted", "reason": "cumulative row"})
            with self.subTest(verdict=verdict):
                result, _, provider = self.run_engine(Scripted(edit))
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["usage"]["calls"], 6)
                self.assertEqual(result["artifacts"][-1]["state"], verdict)
                self.assertFalse(result["reviews"]["judgment-reviewer"])
                self.assertEqual(len([call for call in provider.seen if "acceptance_reference_feedback" in call["payload"]]), 1)

    def test_empty_review_candidate_is_repaired_before_any_acceptance_or_readiness_mutation(self):
        for action in ("finish", "delegate"):
            events = []
            def edit(payload, data):
                if payload["stage"] != "reassess" or payload["pending"][0]["role"] != "fundamental-analyst":
                    return
                data["next_action"] = action
                data["tasks"] = ([{"role": "judgment-reviewer", "question": "독립 후보 검토", "input_ids": [payload["pending"][0]["id"]]}]
                                 if action == "delegate" else [])
                if "candidate_handoff_feedback" not in payload:
                    data["conclusion"] = " \n\t"
                    data["require_risk"] = True
                    data["evidence_readiness"] = "decision-grade"
                    data["acceptances"][0]["state"] = "blocked"
                else:
                    self.assertEqual(engine.draft, "")
                    self.assertEqual(engine.readiness, "insufficient")
                    self.assertFalse(engine.require_risk)
                    self.assertEqual(engine.artifacts[0]["state"], "pending")
                    self.assertEqual(payload["accepted"], [])
                    self.assertFalse(any(event["type"] == "acceptance" for event in events))
                    self.assertEqual(payload["candidate_handoff_feedback"]["next_action"], action)
            provider = Scripted(edit)
            engine = Engine(provider, events.append, lambda: False, ROOT)
            with self.subTest(action=action):
                result = engine.run("fixture research", evidence="fixture")
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["usage"]["calls"], 6)
                self.assertTrue(result["reviews"]["judgment-reviewer"])
                self.assertEqual(len([call for call in provider.seen if "candidate_handoff_feedback" in call["payload"]]), 1)
                reviewer = next(call for call in provider.seen if call["payload"].get("role") == "judgment-reviewer")
                self.assertEqual(reviewer["payload"]["candidate_report"], DemoProvider.CONCLUSION)
                self.assertEqual(reviewer["payload"]["provided_evidence"], "")

    def test_repeated_empty_candidate_blocks_without_partial_state_or_review_dispatch(self):
        for action in ("finish", "delegate"):
            events = []
            def edit(payload, data):
                if payload["stage"] == "reassess":
                    data.update(conclusion=" ", next_action=action, require_risk=True, evidence_readiness="decision-grade")
                    if action == "delegate":
                        data["tasks"] = [{"role": "judgment-reviewer", "question": "review", "input_ids": []}]
            provider = Scripted(edit); engine = Engine(provider, events.append, lambda: False, ROOT)
            with self.subTest(action=action):
                result = engine.run("fixture research", evidence="fixture")
                self.assertEqual((result["status"], result["usage"]["calls"]), ("blocked", 4))
                self.assertEqual(engine.artifacts[0]["state"], "pending")
                self.assertEqual(engine.draft, "")
                self.assertEqual(engine.readiness, "insufficient")
                self.assertFalse(engine.require_risk)
                self.assertFalse(any(event["type"] == "acceptance" for event in events))
                self.assertEqual(len([event for event in events if event["type"] == "candidate_handoff_error"]), 2)
                self.assertFalse(any(call["payload"].get("role") == "judgment-reviewer" for call in provider.seen))

    def test_candidate_and_acceptance_errors_share_one_correction_attempt(self):
        for sequence in ("references_then_candidate", "candidate_then_references", "both_then_valid"):
            def edit(payload, data):
                if payload["stage"] != "reassess" or payload["pending"][0]["role"] != "fundamental-analyst":
                    return
                retry = "candidate_handoff_feedback" in payload or "acceptance_reference_feedback" in payload
                if (not retry and sequence in ("references_then_candidate", "both_then_valid")) or (retry and sequence == "candidate_then_references"):
                    data["acceptances"] = []
                if (not retry and sequence in ("candidate_then_references", "both_then_valid")) or (retry and sequence == "references_then_candidate"):
                    data["conclusion"] = ""
            with self.subTest(sequence=sequence):
                result, events, provider = self.run_engine(Scripted(edit))
                corrections = [call for call in provider.seen if "candidate_handoff_feedback" in call["payload"] or "acceptance_reference_feedback" in call["payload"]]
                self.assertEqual(len(corrections), 1)
                if sequence == "both_then_valid":
                    self.assertEqual((result["status"], result["usage"]["calls"]), ("completed", 6))
                    self.assertIn("candidate_handoff_feedback", corrections[0]["payload"])
                    self.assertIn("acceptance_reference_feedback", corrections[0]["payload"])
                else:
                    self.assertEqual((result["status"], result["usage"]["calls"]), ("blocked", 4))
                    self.assertEqual(result["artifacts"][0]["state"], "pending")
                    self.assertFalse(any(event["type"] == "acceptance" for event in events))

    def test_candidate_correction_respects_budget_and_never_skips_independent_review(self):
        for already_exhausted in (False, True):
            def edit(payload, data):
                if already_exhausted and payload["stage"] == "plan":
                    data["tasks"].append({"role": "news-analyst", "question": "독립 뉴스 확인", "input_ids": []})
                if payload["stage"] == "reassess" and "candidate_handoff_feedback" not in payload:
                    data["conclusion"] = ""
            with self.subTest(already_exhausted=already_exhausted):
                result, events, provider = self.run_engine(Scripted(edit), max_calls=4)
                self.assertEqual((result["status"], result["usage"]["calls"]), ("budget_exhausted", 4))
                self.assertEqual(len(provider.seen), 4)
                self.assertFalse(result["report_complete"])
                self.assertFalse(result["reviews"]["judgment-reviewer"])
                self.assertFalse(any(call["payload"].get("role") == "judgment-reviewer" for call in provider.seen))
                corrections = [call for call in provider.seen if "candidate_handoff_feedback" in call["payload"]]
                self.assertEqual(len(corrections), 0 if already_exhausted else 1)
                if already_exhausted:
                    self.assertTrue(all(artifact["state"] == "pending" for artifact in result["artifacts"]))

    def test_producer_delegation_and_stop_allow_empty_candidate_without_correction(self):
        for action in ("delegate", "stop"):
            def edit(payload, data):
                if payload["stage"] == "reassess" and payload["pending"][0]["id"] == "fundamental-analyst-v1":
                    data.update(conclusion="", next_action=action)
                    if action == "delegate":
                        data["tasks"] = [{"role": "fundamental-analyst", "question": "근거 보완", "input_ids": [payload["pending"][0]["id"]]}]
            with self.subTest(action=action):
                result, events, provider = self.run_engine(Scripted(edit))
                self.assertEqual(result["status"], "completed" if action == "delegate" else "blocked")
                self.assertEqual(result["usage"]["calls"], 7 if action == "delegate" else 3)
                self.assertFalse(any(event["type"] == "candidate_handoff_error" for event in events))
                if action == "delegate":
                    first, second = result["artifacts"][:2]
                    self.assertEqual(first["owner_id"], second["owner_id"])
                    self.assertTrue(result["reviews"]["judgment-reviewer"])

    def test_candidate_correction_cannot_override_independent_reviewer_rejection(self):
        for verdict in ("revise", "blocked"):
            def edit(payload, data):
                if payload["stage"] == "specialist" and payload["role"] == "judgment-reviewer":
                    data["review_verdict"] = verdict
                if (payload["stage"] == "reassess" and payload["pending"][0]["role"] == "judgment-reviewer"
                        and "candidate_handoff_feedback" not in payload):
                    data["conclusion"] = ""
            with self.subTest(verdict=verdict):
                result, _, provider = self.run_engine(Scripted(edit))
                self.assertEqual((result["status"], result["usage"]["calls"]), ("blocked", 6))
                self.assertEqual(result["artifacts"][-1]["state"], verdict)
                self.assertFalse(result["reviews"]["judgment-reviewer"])
                self.assertEqual(len([call for call in provider.seen if "candidate_handoff_feedback" in call["payload"]]), 1)

    def test_non_reference_schema_error_is_not_retried(self):
        def edit(payload, data):
            if payload["stage"] == "reassess":
                data["acceptances"][0]["state"] = "approved"
        result, events, _ = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["usage"]["calls"], 3)
        self.assertEqual(result["artifacts"][0]["state"], "pending")
        self.assertFalse(any(event["type"] == "acceptance_reference_error" for event in events))

    def test_revision_reuses_owner_and_invalidates_old_review(self):
        def edit(payload, data):
            if payload["stage"] == "reassess" and payload["pending"][0]["id"] == "judgment-reviewer-v1":
                data["next_action"] = "delegate"
                data["tasks"] = [{"role": "fundamental-analyst", "question": "현금 전환 불확실성 설명을 보완하세요.", "input_ids": ["fundamental-analyst-v1"]}]
        result, _, provider = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["usage"]["calls"], 9)
        by_id = {a["id"]: a for a in result["artifacts"]}
        self.assertEqual(by_id["fundamental-analyst-v1"]["owner_id"], by_id["fundamental-analyst-v2"]["owner_id"])
        self.assertEqual(by_id["judgment-reviewer-v1"]["owner_id"], by_id["judgment-reviewer-v2"]["owner_id"])
        self.assertEqual(by_id["judgment-reviewer-v2"]["input_ids"], ["fundamental-analyst-v2"])
        revising = next(c for c in provider.seen if c["payload"].get("role") == "fundamental-analyst" and c["payload"]["version"] == 2)
        self.assertEqual(len(revising["payload"]["prior_own_versions"]), 1)

    def test_changed_final_candidate_requires_another_review(self):
        def edit(payload, data):
            if payload["stage"] == "reassess" and payload["pending"][0]["role"] == "judgment-reviewer":
                data["conclusion"] = payload["candidate_report"]
                if payload["pending"][0]["version"] == 1:
                    data["conclusion"] += " 추가 결론."
        result, _, _ = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["usage"]["calls"], 7)
        self.assertEqual(len([a for a in result["artifacts"] if a["role"] == "judgment-reviewer"]), 2)

    def test_head_cannot_overrule_reviewer_block(self):
        def edit(payload, data):
            if payload["stage"] == "specialist" and payload["role"] == "judgment-reviewer":
                data["review_verdict"] = "blocked"
        result, _, _ = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["artifacts"][-1]["state"], "blocked")
        self.assertFalse(result["reviews"]["judgment-reviewer"])

    def test_portfolio_requires_different_risk_and_judgment_owners(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"][0]["role"] = "portfolio-manager"
        result, _, _ = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "completed")
        self.assertEqual([a["role"] for a in result["artifacts"]], ["portfolio-manager", "risk-manager", "judgment-reviewer"])
        self.assertEqual(len({a["owner_id"] for a in result["artifacts"]}), 3)
        self.assertTrue(result["reviews"]["risk-manager"])

    def test_reviewer_cannot_run_before_accepted_evidence(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"][0]["role"] = "judgment-reviewer"
        result, _, _ = self.run_engine(Scripted(edit))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["usage"]["calls"], 1)

    def test_mixed_initial_roadmap_defers_reviews_until_accepted_candidate(self):
        def edit(payload, data):
            if payload['stage'] == 'plan':
                data['tasks'] = [
                    {'role':'judgment-reviewer','question':'채택 결론의 반대 가설을 검토하세요.','input_ids':[]},
                    {'role':'fundamental-analyst','question':'사업 품질을 검토하세요.','input_ids':[]},
                    {'role':'risk-manager','question':'확인된 근거의 하방 위험을 검토하세요.','input_ids':[]},
                    {'role':'valuation-analyst','question':'가치평가 입력의 부족을 검토하세요.','input_ids':[]},
                ]
        result, events, provider = self.run_engine(Scripted(edit))
        self.assertEqual(result['status'],'completed')
        specialist_calls=[c['payload'] for c in provider.seen if c['payload']['stage']=='specialist']
        self.assertEqual({c['role'] for c in specialist_calls[:2]}, {'fundamental-analyst','valuation-analyst'})
        self.assertEqual([c['role'] for c in specialist_calls[2:]], ['risk-manager','judgment-reviewer'])
        for call in specialist_calls[2:]:
            self.assertTrue(call['candidate_report'])
            self.assertTrue(call['accepted_inputs'])
            self.assertTrue(all(a['state']=='accepted' for a in call['accepted_inputs']))
        self.assertEqual(specialist_calls[2]['question'],'확인된 근거의 하방 위험을 검토하세요.')
        self.assertEqual(specialist_calls[3]['question'],'채택 결론의 반대 가설을 검토하세요.')
        self.assertEqual(len({a['owner_id'] for a in result['artifacts']}),4)
        self.assertTrue(any(e['type']=='review_deferred' for e in events))

    def test_mixed_roadmap_still_rejects_invalid_producer_inputs(self):
        def edit(payload, data):
            if payload['stage']=='plan':
                data['tasks'][0]['input_ids']=['not-accepted']
                data['tasks'].append({'role':'judgment-reviewer','question':'독립 검토','input_ids':[]})
        result, _, provider=self.run_engine(Scripted(edit))
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(len(provider.seen),2)
        self.assertEqual(result['artifacts'],[])
        self.assertFalse(result['report_complete'])
        self.assertLess(result['progress']['percent'],100)

    def test_progress_is_stage_based_monotonic_during_revision(self):
        def edit(payload,data):
            if payload['stage']=='reassess' and payload['pending'][0]['id']=='judgment-reviewer-v1':
                data['next_action']='delegate'
                data['tasks']=[{'role':'fundamental-analyst','question':'현금흐름 해석 보완','input_ids':['fundamental-analyst-v1']}]
        result, events, _=self.run_engine(Scripted(edit))
        values=[e['progress']['percent'] for e in events]
        self.assertEqual(values,sorted(values))
        self.assertEqual(result['progress']['percent'],100)
        self.assertTrue(result['report_complete'])
        self.assertTrue(any(e['progress']['stage']=='revising' for e in events))
        self.assertTrue(all(e['progress']['percent']<=95 for e in events if e['progress']['stage']!='completed'))
        self.assertEqual(result['progress']['calls_completed'],9)
        self.assertEqual(result['progress']['call_limit'],12)

    def test_terminal_incomplete_never_claims_100_percent(self):
        exhausted, _, _=self.run_engine(max_calls=4)
        self.assertEqual(exhausted['status'],'budget_exhausted')
        self.assertLess(exhausted['progress']['percent'],100)
        self.assertFalse(exhausted['report_complete'])
        cancelled=Engine(Scripted(),lambda e:None,lambda:True,ROOT).run('test')
        self.assertEqual(cancelled['progress']['percent'],0)
        self.assertEqual(cancelled['progress']['stage'],'cancelled')

    def test_actual_model_metadata_is_preserved_on_artifacts(self):
        class Identified(Scripted):
            def complete(self,*args,**kwargs):
                result=super().complete(*args,**kwargs)
                result.update(provider='test-provider',model='test-model')
                return result
        result, events, _=self.run_engine(Identified())
        self.assertTrue(all(a['provider']=='test-provider' and a['model']=='test-model' for a in result['artifacts']))
        self.assertTrue(all(e['model']=='test-model' for e in events if e['type']=='agent_completed'))

    def test_cancel_does_not_dispatch(self):
        result = Engine(Scripted(), lambda e: None, lambda: True, ROOT).run("test")
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["usage"]["calls"], 0)

    def test_live_error_never_falls_back_to_demo(self):
        class FailedProvider:
            mode = "live"
            def complete(self, *args, **kwargs):
                raise ProviderError("API 키 인증에 실패했습니다.")
        result, events, _ = self.run_engine(FailedProvider())
        lifecycle = [(e["type"], e["role"], e["call_number"]) for e in events if e["type"].startswith("agent_")]
        self.assertEqual(lifecycle, [("agent_started", "head-manager", 1), ("agent_failed", "head-manager", 1)])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["mode"], "live")
        self.assertNotIn("AI 분석 아님", result["report"])
        self.assertEqual(result["artifacts"], [])

    def test_memory_not_given_before_independent_current_view(self):
        result, _, provider = self.run_engine(context={"memory": "OLD MEMORY", "strategy": "selected"})
        self.assertEqual(result["status"], "completed")
        plan = provider.seen[0]["payload"]
        self.assertNotIn("OLD MEMORY", json.dumps(plan))
        producer = next(c for c in provider.seen if c["payload"].get("role") == "fundamental-analyst")
        self.assertNotIn("OLD MEMORY", json.dumps(producer["payload"]))
        head_assess = next(c for c in provider.seen if c["payload"]["stage"] == "reassess")
        self.assertEqual(head_assess["payload"]["decision_memory_after_independent_current_view"], "OLD MEMORY")

    def test_each_selected_specialist_runs_without_other_producers_and_keeps_reviews(self):
        for role in SPECIALIST_ROLES:
            with self.subTest(role=role):
                result, events, provider = self.run_engine(target_role=role)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["target_role"], role)
                self.assertEqual(result["mandate"]["target_role"], role)
                expected = [role] + (["risk-manager"] if role == "portfolio-manager" else []) + ["judgment-reviewer"]
                self.assertEqual([a["role"] for a in result["artifacts"]], expected)
                self.assertEqual(len({a["owner_id"] for a in result["artifacts"]}), len(expected))
                self.assertTrue(result["reviews"]["judgment-reviewer"])
                head_calls = [c for c in provider.seen if c["payload"]["stage"] in ("plan", "reassess")]
                self.assertTrue(all(c["payload"]["target_role"] == role for c in head_calls))
                self.assertTrue(any(e["type"] == "scope_selected" and e["role"] == role for e in events))

    def test_focused_plan_cannot_replace_specialist_with_head_direct_answer(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"] = []
                data["direct_answer"] = "검토하지 않은 직접 답변"
        result, _, provider = self.run_engine(Scripted(edit), target_role="technical-analyst")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["usage"]["calls"], 5)
        self.assertNotIn("검토하지 않은 직접 답변", result["report"])
        specialist = next(c for c in provider.seen if c["payload"].get("role") == "technical-analyst")
        self.assertEqual(specialist["payload"]["question"], "제공 자료로 사업 품질을 검토하세요.")
        self.assertTrue(result["reviews"]["judgment-reviewer"])

    def test_focused_roadmap_keeps_chosen_task_and_defers_review_intent(self):
        def edit(payload, data):
            if payload["stage"] == "plan":
                data["tasks"] += [
                    {"role": "technical-analyst", "question": "제공된 OHLCV의 변동성과 추세만 검토", "input_ids": []},
                    {"role": "judgment-reviewer", "question": "기술적 해석의 반증 가능성을 검토", "input_ids": []},
                ]
        result, _, provider = self.run_engine(Scripted(edit), target_role="technical-analyst")
        self.assertEqual(result["status"], "completed")
        calls = [c["payload"] for c in provider.seen if c["payload"]["stage"] == "specialist"]
        self.assertEqual([c["role"] for c in calls], ["technical-analyst", "judgment-reviewer"])
        self.assertEqual(calls[0]["question"], "제공된 OHLCV의 변동성과 추세만 검토")
        self.assertEqual(calls[1]["question"], "기술적 해석의 반증 가능성을 검토")
        self.assertEqual([a["id"] for a in calls[1]["accepted_inputs"]], ["technical-analyst-v1"])

    def test_focused_followup_cannot_silently_expand_to_another_specialist(self):
        def edit(payload, data):
            if payload["stage"] == "reassess" and payload["pending"][0]["role"] == "technical-analyst":
                data["next_action"] = "delegate"
                data["tasks"] = [{"role": "news-analyst", "question": "새 전문 분석", "input_ids": []}]
        result, _, provider = self.run_engine(Scripted(edit), target_role="technical-analyst")
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["report_complete"])
        self.assertIn("종합 분석", result["reason"])
        self.assertEqual(result["usage"]["calls"], 3)
        self.assertFalse(any(c["payload"].get("role") == "news-analyst" for c in provider.seen))

    def test_focused_revision_keeps_owner_and_reviews_latest_version(self):
        def edit(payload, data):
            if payload["stage"] == "reassess" and payload["pending"][0]["id"] == "technical-analyst-v1":
                data["acceptances"][0]["state"] = "revise"
                data["next_action"] = "delegate"
                data["tasks"] = [{"role": "technical-analyst", "question": "시점과 불확실성을 보완", "input_ids": []}]
        result, _, _ = self.run_engine(Scripted(edit), target_role="technical-analyst")
        self.assertEqual(result["status"], "completed")
        first, revised, review = result["artifacts"]
        self.assertEqual(first["owner_id"], revised["owner_id"])
        self.assertEqual(review["input_ids"], ["technical-analyst-v2"])
        self.assertTrue(result["reviews"]["judgment-reviewer"])

    def test_review_only_and_invalid_targets_fail_before_paid_calls(self):
        for target in ("risk-manager", "judgment-reviewer", "head-manager", "unknown", "", [], False):
            with self.subTest(target=target):
                provider = Scripted()
                with self.assertRaises(ValueError):
                    self.run_engine(provider, target_role=target)
                self.assertEqual(provider.seen, [])


class ProviderTests(unittest.TestCase):
    def test_quota_and_rate_errors_are_distinct_without_echoing_provider_message(self):
        checks = {'credit_balance_exhausted':'크레딧이 소진',
                  'insufficient_quota':'할당량',
                  'organization_spend_limit_exceeded':'조직의 월간 지출',
                  'project_spend_limit_exceeded':'프로젝트의 월간 지출',
                  'organization_usage_limit_exceeded':'월간 API 사용',
                  'rate_limit_exceeded':'일시적인', 'slow_down':'증가 속도'}
        for code, expected in checks.items():
            with self.subTest(code=code):
                body=json.dumps({'error':{'code':code,'message':'sk-private-secret'}}).encode()
                failure=urllib.error.HTTPError('https://api.openai.com/v1/responses',429,'error',{},io.BytesIO(body))
                with patch('hyperpass.provider._open',side_effect=failure):
                    with self.assertRaises(ProviderError) as caught: OpenAIProvider('sk-test').check()
                self.assertIn(expected,str(caught.exception))
                self.assertNotIn('sk-private-secret',str(caught.exception))
                self.assertTrue(failure.closed)

    def test_unknown_429_does_not_assert_billing_failure(self):
        for body in (b'not json',b'{"error":[]}',b'{"error":{"code":"sk-secret"}}'):
            failure=urllib.error.HTTPError('https://api.openai.com/v1/responses',429,'error',{},io.BytesIO(body))
            with patch('hyperpass.provider._open',side_effect=failure):
                with self.assertRaises(ProviderError) as caught: OpenAIProvider('sk-test').check()
            self.assertIn('단정할 수 없습니다',str(caught.exception))
            self.assertNotIn('sk-secret',str(caught.exception))

    def test_connection_check_uses_small_output_reservation(self):
        body={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}]}
        with patch('hyperpass.provider._open',return_value=io.BytesIO(json.dumps(body).encode())) as call:
            self.assertTrue(OpenAIProvider('sk-test').check()['ok'])
        self.assertEqual(json.loads(call.call_args[0][0].data)['max_output_tokens'],1024)

    def test_http_failure_does_not_expose_key_or_response_body(self):
        key = "sk-secret-not-for-logs"
        failure = urllib.error.HTTPError("https://api.openai.com/v1/responses", 401, key, {}, io.BytesIO(key.encode()))
        with patch("hyperpass.provider._open", side_effect=failure):
            with self.assertRaises(ProviderError) as caught:
                OpenAIProvider(key).check()
        self.assertNotIn(key, str(caught.exception))
        self.assertIn("인증", str(caught.exception))
        self.assertTrue(failure.closed)

    def test_request_shape_and_real_citation_extraction(self):
        body = {"status": "completed", "id": "resp_test", "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "{\"answer\":\"yes\"}",
                                                            "annotations": [{"type": "url_citation", "url": "https://example.org/source", "title": "source"}]}]}]}
        response = io.BytesIO(json.dumps(body).encode())
        with patch("hyperpass.provider._open", return_value=response) as call:
            result = OpenAIProvider("sk-test").complete("instructions", {"question": "test"}, schema={"type": "object"}, web_search=True)
        request = call.call_args[0][0]
        sent = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertFalse(sent["store"])
        self.assertEqual(sent["tools"], [{"type": "web_search"}])
        self.assertNotIn("sk-test", request.data.decode())
        self.assertEqual(result["data"], {"answer": "yes"})
        self.assertEqual(result["citations"][0]["url"], "https://example.org/source")

    def test_incomplete_response_is_not_success(self):
        with patch("hyperpass.provider._open", return_value=io.BytesIO(b'{"status":"incomplete"}')):
            with self.assertRaises(ProviderError):
                OpenAIProvider("sk-test").check()

    def test_redirect_does_not_forward_authorization(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                received.append((self.path, self.headers.get("Authorization")))
                if self.path == "/first":
                    self.send_response(302)
                    self.send_header("Location", "/second")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/first", headers={"Authorization": "Bearer test-sentinel"})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                _open(request, timeout=5)
            caught.exception.close()
            self.assertEqual(caught.exception.code, 302)
            self.assertEqual(received, [("/first", "Bearer test-sentinel")])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)


if __name__ == "__main__":
    unittest.main()
