# AI 모델과 추론 강도

공식 문서 확인일: **2026-11-22**. 구현: `hyperpass/model_providers.py`, `hyperpass/provider.py`.

이 앱의 추론 강도는 요청을 처리하는 모델의 생각량 설정입니다. 에이전트 수·역할 선정·독립 검토 순서를 바꾸지 않습니다. Codex 앱의 표시 이름을 다른 API의 값으로 치환하지 않습니다. 예를 들어 여기서 GPT-6.2 Astra의 최댓값은 API의 `max`이며 `ultra`를 보내지 않습니다.

## 모델 목록과 연결 확인

- OpenAI `/v1/models`, Anthropic `/v1/models`, Gemini `/v1beta/models`에서 해당 키로 조회한 모델을 표시합니다. 문서의 모델 이름을 사용 권한이 있는 모델인 것처럼 자동 등록하지 않습니다.
- 모델 목록 조회는 생성 성공을 보장하지 않습니다. 연결 확인은 실제 응답을 요청합니다. Claude·Gemini는 작은 JSON 결과도 검사합니다.
- 추론 강도 표에 없는 모델·확인하지 않은 스냅샷은 **기본**만 제공합니다. 입력 형식이 맞는 사용자 지정 모델은 기본 설정으로 연결 검사할 수 있습니다.
- API 키는 HTTP 인증 헤더에만 사용합니다. 응답·로그·보고서에 포함하지 않으며, 다른 서버로의 리다이렉트는 거부합니다.

공식 모델 목록 문서: [OpenAI Models](https://developers.openai.com/api/reference/resources/models/methods/list), [Anthropic Models](https://platform.claude.com/docs/en/api/models/list), [Gemini Models](https://aistudio.google.com/api-reference/models).

## OpenAI

기본을 선택하면 `reasoning` 필드를 생략합니다. 그 외 값은 Responses API의 `reasoning.effort`로 그대로 전송합니다.

| 확인한 모델 ID | 기본 외 제공 옵션 |
| --- | --- |
| `gpt-5`, `gpt-5-mini`, `gpt-5-nano` | minimal, low, medium, high |
| `gpt-5.1` | none, low, medium, high |
| `gpt-5.2`, `gpt-5.4`, `gpt-5.5` | none, low, medium, high, xhigh |
| `gpt-5.5-pro` | medium, high, xhigh |
| `gpt-5.6-sol` | none, low, medium, high, xhigh, max |
| `gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6-astra`, `gpt-6.1-sol` | low, medium, high, xhigh, max |
| `gpt-6.1-terra`, `gpt-6-sol`, `gpt-6-luna` | none, low, medium, high, xhigh, max |

별도 확인한 스냅샷은 동일한 옵션을 제공합니다: `gpt-5-mini-2025-08-07`, `gpt-5.1-2025-11-13`, `gpt-5.2-2025-12-11`, `gpt-5.5-2026-04-23`. 날짜 모양만 보고 임의의 새 스냅샷을 지원한다고 추정하지 않습니다.

근거: [GPT-5](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5), [GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini), [GPT-5.1](https://developers.openai.com/api/docs/models/gpt-5.1), [GPT-5.2](https://developers.openai.com/api/docs/models/gpt-5.2), [GPT-5.4](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.4), [GPT-5.5](https://developers.openai.com/api/docs/models/gpt-5.5), [GPT-5.5 Pro](https://developers.openai.com/api/docs/models/gpt-5.5-pro), [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), [API deployment checklist](https://developers.openai.com/api/docs/guides/deployment-checklist), [Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).

## Claude

기본 외 강도는 `output_config.effort`로 전송합니다.

| 확인한 모델 ID | 기본 외 제공 옵션 |
| --- | --- |
| `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-mythos-preview` | low, medium, high, max |
| `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-opus-5-5` | low, medium, high, xhigh, max |
| `claude-sonnet-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` | low, medium, high, xhigh, max |
| `claude-fable-5`, `claude-fable-5-1`, `claude-fable-5-2` | low, medium, high, xhigh, max |
| `claude-mythos-5`, `claude-mythos-5-1`, `claude-mythos-5-2` | low, medium, high, xhigh, max |

현재 [공식 Effort 표](https://platform.claude.com/docs/en/build-with-claude/effort)는 **Sonnet 4.6의 `max` 지원을 명시**합니다. 같은 모델의 `xhigh`는 목록에 없으므로 제공하지 않습니다.

Opus 4.6·4.7·4.8과 Sonnet 4.6은 thinking 기본값이 꺼져 있습니다. 이 모델에서 강도를 직접 선택하면 `thinking: {"type":"adaptive","display":"omitted"}`도 보냅니다. Claude 5 계열은 문서상 adaptive thinking이 기본 활성화되어 추가 설정을 생략합니다. 기본 선택은 모델 기본값을 그대로 유지합니다. Opus 4.5는 별도 legacy thinking budget 설정을 이 앱에서 제공하지 않으므로 기본만 노출합니다. [Thinking 설정표](https://platform.claude.com/docs/en/build-with-claude/thinking)

모델 ID는 [현재 모델 목록](https://platform.claude.com/docs/en/models/overview)과 [ID 규칙](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions)을 따릅니다. 4.6 이후 모델에 임의의 날짜를 붙인 ID에는 강도를 추정 적용하지 않습니다. 특정 모델에 대한 별도 접근 권한은 목록 조회와 연결 검사 결과를 따릅니다.

## Gemini

Gemini 3·4의 기본 외 선택은 `generationConfig.thinkingConfig.thinkingLevel`로 대문자 값을 전송합니다.

| 확인한 모델 ID | 기본 외 제공 옵션 |
| --- | --- |
| `gemini-4-carbon`, `gemini-4-argon`, `gemini-3.8-flash` | low, medium, high |
| `gemini-4-neon`, `gemini-4-hydrogen` | low, medium, high, xhigh |
| `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview` | minimal, low, medium, high |
| `gemini-3.1-pro-preview` | low, medium, high |
| `gemini-3-pro-preview` | low, high |
| `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` | 생각 예산 1,024 / 4,096 / 8,192 토큰 |

Gemini 2.5에는 `thinkingLevel`을 보내면 오류가 납니다. 세 예산 프리셋은 해당 모델의 허용 범위 안에서 앱이 제공하는 선택지이며, API 고유의 low/medium/high와 같다는 뜻이 아닙니다. 실제 요청은 `thinkingConfig.thinkingBudget` 정수입니다. 기본은 이 설정을 생략합니다.

근거: [Gemini Thinking 모델별 수준](https://aistudio.google.com/docs/thinking#thinking-levels), [generateContent 필드 정의](https://aistudio.google.com/api-reference/generate-content), [Google의 Gemini 2.5 예산 범위](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking#gemini_25_and_earlier_models).

## JSON 결과와 웹 검색

검색을 끄면 각 API의 구조화 출력 설정을 사용합니다. 검색을 켠 Claude·Gemini는 네이티브 검색 도구를 허용하고, JSON 스키마를 지시문에 넣어 결과를 받습니다. 전체 텍스트 또는 마지막 JSON 텍스트 블록을 파싱한 다음 엔진이 필드·타입·열거값을 다시 검증합니다. 파싱 실패를 추정 결과로 메우거나 자동 재호출하지 않습니다.

Claude는 네이티브 citations와 `output_config.format` 조합이 공식적으로 충돌하므로 검색 시 format을 생략합니다. Gemini의 스키마와 검색 도구 결합은 일부 세대의 preview 기능이므로 이 앱은 그 조합을 모든 모델에 강제하지 않습니다. [Claude 구조화 출력의 호환성](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Gemini 도구와 구조화 출력](https://aistudio.google.com/docs/structured-output#tools)

Claude 출처는 텍스트 블록의 citations에서, Gemini 출처는 `groundingMetadata.groundingChunks[].web`에서만 가져옵니다. 모델이 적은 URL을 API 검색 출처로 승격하지 않습니다. Gemini 원문의 인용 위치는 JSON 문자열과 보고서 본문의 위치가 다르므로 별도의 출처 목록으로 보존합니다. [Gemini generateContent 응답](https://aistudio.google.com/api-reference/generate-content)

Gemini의 `searchEntryPoint.renderedContent`는 최대 64 KiB의 `search_suggestions_html`로 전달합니다. 검색 제안 표시가 필요한 HTML이며 메인 페이지의 `innerHTML`로 실행해서는 안 됩니다. 소비자는 스크립트와 same-origin 권한이 없는 sandbox iframe에 격리해야 합니다. 초과 데이터는 임의로 자르지 않고 실패 처리합니다. [Google Search 표시 응답과 사용 조건 안내](https://aistudio.google.com/docs/google-search#understanding-the-grounding-response)

## 검증 범위

자동 검사는 인증 헤더, 비밀정보를 제외한 오류, 리다이렉트 차단, 모델별 강도, 실제 전송 필드, JSON·인용 처리, 미완료 응답 차단, 역할별 라우팅을 모의 API 응답으로 확인합니다. Claude·Gemini의 실제 유료 호출 성공 여부까지 검증한 것은 아닙니다. 사용자의 계정·권한·할당량과 선택 모델의 실제 연결 검사는 별도입니다.

일반 호출은 최대 출력 12,000 토큰, 연결 검사는 1,024 토큰으로 제한합니다. 높은 강도나 큰 생각 예산도 이 한도 안에서 실행됩니다. 완결되지 않은 응답은 완료 보고서로 표시하지 않습니다. 한 번의 `complete()`는 모델 HTTP 요청 한 번이며, 네이티브 검색 도구 요금은 제공자가 별도 청구할 수 있습니다.
