"""Small, secret-safe OpenAI Responses transport (standard library only)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    """A user-safe error; never includes HTTP bodies, prompts or credentials."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an Authorization header to a redirected endpoint.
        return None


def _open(request, timeout):
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


class OpenAIProvider:
    mode = "live"
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str, reasoning: str = "default"):
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 1000:
            raise ProviderError("OpenAI API 키를 입력해 주세요.")
        if not isinstance(model, str) or not model.strip() or len(model) > 120:
            raise ProviderError("사용할 모델 이름을 확인해 주세요.")
        self._key = api_key.strip()
        self.model = model.strip()
        # Lazy import keeps the original transport usable without an import cycle.
        from .model_providers import validate_reasoning
        self.reasoning = validate_reasoning('openai', self.model, reasoning)

    def complete(self, instructions, payload, *, schema=None, web_search=False, max_output_tokens=12000):
        body = {"model": self.model, "instructions": instructions,
                "input": json.dumps(payload, ensure_ascii=False), "store": False,
                "max_output_tokens": max_output_tokens}
        if self.reasoning != "default":
            body["reasoning"] = {"effort": self.reasoning}
        if schema is not None:
            body["text"] = {"format": {"type": "json_schema", "name": "research_result",
                                       "strict": True, "schema": schema}}
        if web_search:
            body["tools"] = [{"type": "web_search"}]
        request = urllib.request.Request(self.endpoint, data=json.dumps(body).encode("utf-8"),
                                         method="POST", headers={
                                             "Authorization": "Bearer " + self._key,
                                             "Content-Type": "application/json",
                                             "User-Agent": "Hyperpass-Research-Web/0.1"})
        try:
            with _open(request, timeout=180) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ProviderError("모델 응답이 너무 큽니다. 질문 범위를 줄여 다시 실행해 주세요.")
            data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            code = exc.code
            # Read only a bounded error code. Never expose provider messages,
            # request bodies, organization IDs or credentials to the UI/logs.
            error_code = None
            try:
                details = json.loads(exc.read(65536))
                error = details.get('error', {}) if isinstance(details, dict) else {}
                if isinstance(error, dict):
                    candidate = error.get('code') or error.get('type')
                    if isinstance(candidate, str): error_code = candidate
            except (ValueError, TypeError, OSError):
                pass
            finally:
                exc.close()
            messages = {401: "API 키 인증에 실패했습니다. 키를 확인해 주세요.",
                        403: "이 API 키 또는 프로젝트에 요청한 기능의 권한이 없습니다.",
                        404: "모델을 사용할 수 없습니다. API 프로젝트에서 허용된 모델을 선택해 주세요.",
                        429: "OpenAI가 429 오류를 반환했지만 상세 원인을 확인하지 못했습니다. 잔액 부족으로 단정할 수 없습니다. API 잔액·사용 한도·요청 속도 제한을 확인해 주세요.",
                        400: "API가 모델 또는 요청 옵션을 거절했습니다. 모델·웹 검색 지원 여부를 확인해 주세요."}
            message = "OpenAI 요청이 다른 주소로 이동하여 연결을 차단했습니다." if 300 <= code < 400 else messages.get(code, "OpenAI 서비스 요청이 실패했습니다. 잠시 후 다시 시도해 주세요.")
            if code == 429:
                reasons = {
                    'credit_balance_exhausted': 'OpenAI API 선불 크레딧이 소진됐습니다 (credit_balance_exhausted). 해당 키가 속한 API 조직의 Billing에서 잔액을 확인하세요. 다시 누르기만 해서는 해결되지 않습니다.',
                    'insufficient_quota': 'OpenAI API 사용 가능 할당량이 없습니다 (insufficient_quota). 해당 키가 속한 API 조직의 Billing 잔액·결제 활성화와 사용 한도를 확인하세요. ChatGPT 구독 상태와는 별도입니다.',
                    'organization_spend_limit_exceeded': 'OpenAI API 조직의 월간 지출 한도에 도달했습니다 (organization_spend_limit_exceeded). 조직의 한도 설정 또는 다음 초기화 시점을 확인하세요.',
                    'project_spend_limit_exceeded': '이 API 키가 속한 프로젝트의 월간 지출 한도에 도달했습니다 (project_spend_limit_exceeded). 해당 프로젝트의 한도 설정을 확인하세요.',
                    'organization_usage_limit_exceeded': 'OpenAI가 조직에 부여한 월간 API 사용 한도에 도달했습니다 (organization_usage_limit_exceeded). 잔액과 별개로 조직의 승인된 사용 한도를 확인하세요.',
                    'rate_limit_exceeded': '일시적인 API 요청·토큰 속도 제한입니다 (rate_limit_exceeded). 잠시 기다린 뒤 한 번만 다시 시도하세요. 이 오류만으로 결제가 필요하다는 뜻은 아닙니다.',
                    'rate_limit_error': '일시적인 API 요청 속도 제한입니다 (rate_limit_error). 잠시 기다린 뒤 한 번만 다시 시도하세요.',
                    'slow_down': 'API 요청량 증가 속도 제한입니다 (slow_down). 연속 재시도를 멈추고 잠시 기다린 뒤 다시 시도하세요.',
                }
                message = reasons.get(error_code, message)
            raise ProviderError(message) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("OpenAI에 연결하지 못했거나 응답 시간이 초과됐습니다. 네트워크를 확인해 주세요.") from None
        except (ValueError, TypeError):
            raise ProviderError("OpenAI 응답을 해석하지 못했습니다.") from None
        if data.get("status") != "completed":
            raise ProviderError("모델 응답이 완료되지 않았습니다. 질문을 좁히거나 호출 한도를 조정해 주세요.")
        text_parts, citations = [], []
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise ProviderError("모델이 요청 처리를 거절했습니다. 질문의 범위를 확인해 주세요.")
                if content.get("type") == "output_text":
                    text_parts.append(content.get("text", ""))
                    for note in content.get("annotations", []):
                        if note.get("type") == "url_citation":
                            url = note.get("url", "")
                            if url.startswith(("https://", "http://")):
                                citations.append({"url": url, "title": str(note.get("title", url))})
        output = "\n".join(text_parts)
        if not output:
            raise ProviderError("모델이 읽을 수 있는 결과를 반환하지 않았습니다.")
        parsed = None
        if schema is not None:
            try:
                parsed = json.loads(output)
            except (ValueError, TypeError):
                raise ProviderError("모델의 구조화 결과가 올바르지 않아 실행을 중단했습니다.") from None
        usage = data.get("usage") or {}
        return {"text": output, "data": parsed, "citations": citations,
                "response_id": str(data.get("id", "")),
                "usage": {key: int(usage.get(key, 0)) for key in ("input_tokens", "output_tokens", "total_tokens")}}

    def check(self):
        result = self.complete("This is a connection check. Reply only OK.", {"message": "OK"}, max_output_tokens=1024)
        return {"ok": True, "model": self.model, "response_id": result["response_id"],
                "usage": result["usage"], "message": "모델의 실제 응답을 확인했습니다."}


class DemoProvider:
    """Explicit scripted walkthrough; never used as recovery for live errors."""
    mode = "demo"
    model = "scripted-demo"
    CONCLUSION = "가상 자료의 매출·영업이익 개선만으로 지속 가능한 사업 품질 개선을 확정할 수 없습니다. 현금 전환, 채권 회수와 고객 집중도를 추가 확인해야 합니다."

    def check(self):
        return {"ok": True, "model": self.model, "message": "API를 사용하지 않는 고정 예제입니다."}

    def complete(self, instructions, payload, *, schema=None, web_search=False):
        stage = payload["stage"]
        if stage == "plan":
            data = {"outcome": "가상 기업의 사업 품질 검토", "horizon": "제공 자료 기간",
                    "as_of": "가상 자료 기준", "direct_answer": "", "require_risk": False,
                    "tasks": [{"role": "fundamental-analyst", "question": "가상 자료의 사업 품질과 반대 근거를 검토하세요.", "input_ids": []}],
                    "reason": "사업·재무 자료의 최소 담당자부터 시작합니다."}
        elif stage == "reassess":
            data = {"acceptances": [{"artifact_id": a["id"], "state": "accepted", "reason": "고정 예제의 제한적 연구 근거로 채택"} for a in payload["pending"]],
                    "next_action": "finish", "tasks": [], "conclusion": self.CONCLUSION,
                    "reason": "추가 자료가 없으므로 한계를 남기고 독립 검토합니다.",
                    "evidence_readiness": "screen", "require_risk": False}
        else:
            role = payload["role"]
            reviewing = role in {"judgment-reviewer", "risk-manager"}
            data = {"report": ("## 고정 데모 · AI 분석 아님\n\n" +
                                ("독립 검토 예제: 제한된 결론을 유지합니다. 경영진 주장과 시점 없는 가격은 확정 근거가 아닙니다." if reviewing else
                                 "제공된 가상 자료에 이익 개선과 현금 전환 약화가 함께 나타납니다. 실제 기업이나 현재 시장을 분석한 결과가 아닙니다.")),
                    "summary": self.CONCLUSION, "evidence_readiness": "screen",
                    "missing_evidence": ["감사자료", "채권 회수 내역", "고객 계약"],
                    "follow_up_requests": [], "review_verdict": "accept" if reviewing else "not_applicable"}
        return {"text": json.dumps(data, ensure_ascii=False), "data": data, "citations": [],
                "response_id": "demo-script", "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}
