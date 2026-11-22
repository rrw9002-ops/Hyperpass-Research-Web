# Reproducible numeric work

Quote source-reported figures with provenance. For conclusion-driving derived
numbers, preserve exact inputs, periods, units, currency and instrument identity;
write inspectable formulas/code and run them using an actually available native
calculation tool or local runtime. Save the observed outputs and tool/runtime
identity with source references under the assigned run. Use Decimal or suitable
numerical precision for money. Reject non-finite values, unit mismatches and
unjustified denominators. Read `data-qc.md` before accepting results.

No Python installation is required to open or use this kit. If no trustworthy
calculation capability is available, report that the requested numeric conclusion
is uncomputed and limit readiness. Do not call `tcx-calc`, invent a calculation
receipt, or silently substitute mental arithmetic for a material model run.

For DCF, bind revenue growth, margins, tax, reinvestment, working capital,
discount rate, terminal assumptions, net debt and diluted shares to evidence or
explicit scenarios. Reconcile enterprise to equity/per-share value, ensure the
terminal growth/discount relation is valid, and test sensitivities. Reverse DCF
is an expectations test, not proof of intrinsic value. Preserve supported ranges
and abstain when a material base or market anchor is missing.

For strategy performance use `anti-overfit.md`. Preserve every trial, chronological
splits, costs, data vintage and execution assumptions. A chart or simulated fill
does not establish tradable alpha. For unsupported tests use a clear gap; do not
mark an unrun test `pass` or use `not_applicable` to conceal missing evidence.

## 웹앱의 실제 백테스트 자료 해석

- 먼저 단위를 확인합니다. 이 앱의 TradingView `report.metrics`에서
  `net_profit_percent`, `max_drawdown_percent`, `buy_hold_return_percent`,
  `percent_profitable`은 이미 퍼센트 단위입니다. 반면 원본
  `report.performance`의 `*Percent` 및 `percentProfitable`은 분수입니다.
  원본 분수에 100을 곱한 뒤 표시용 퍼센트와 비교합니다. 예: 0.25와 25%는
  같은 값이며 단위 차이만으로 원본 오류나 계산 불일치라고 판단하지 않습니다.
- 이 분석 실행에는 별도 계산 도구가 제공되지 않습니다. 공급자가 반환한 평균·비율·
  합계를 우선 인용하고, 복잡한 산술·날짜 변환을 머릿속으로 수행한 뒤 검산했다고
  쓰지 않습니다. 검산이나 새 민감도 계산이 필요하면 미실행 항목으로 남깁니다.
- 절대 손실·증거금·포지션을 초기자본과 비교하는 것만으로 레버리지, 부채, 파산,
  마진콜을 추정하지 않습니다. 복리로 자본이 변하므로 해당 시점의 equity와
  포지션·증거금 조건이 필요합니다. 실제 `marginCalls` 관측과 가상의 위험을 구분합니다.
- 금액 최대 낙폭과 비율 최대 낙폭은 서로 다른 구간에서 발생할 수 있습니다.
  발생 시점이 일치한다는 근거 없이 둘을 결합해 당시 equity를 역산하지 않습니다.
- `*_selection.returned`, `stored`, 전체 거래 수를 구분합니다. 마지막 일부 거래만
  전달되었다면 그것을 전체 거래 목록이라고 쓰거나 전체 분포를 재계산하지 않습니다.
- `settings.dateRange.backtest`와 거래의 `e.tm`/`x.tm`은 밀리초 기반 시각입니다.
  주문의 `time_index`는 거래 순서/인덱스이며 절대시각으로 변환하지 않습니다.
  이미 제공된 날짜를 우선 사용하고, 불확실한 변환 날짜를 추정해 쓰지 않습니다.
- 수수료·슬리피지·사이징 변경의 최종 성과는 실제 재계산과 구분합니다.
  복리·체결·거래 수가 바뀔 수 있으므로 재계산 없이 성과가 비례 변한다고 단정하지
  않습니다. 고정 거래를 가정한 근사라면 그 가정과 적용 범위를 명시합니다.
- 연결 대상 ID, 저장 작업 ID, 전략 ID, 자료의 관측 시점, 보고서 생성 시각은
  서로 다른 정보입니다. 출처의 종류와 기준 시점을 임의로 바꾸지 않습니다.
- 독립 검토는 채택된 근거의 단위·분모·표본 범위와 반증을 확인합니다. 근거에
  필요한 원본 필드가 없으면 해당 담당자에게 보완을 요청하고 새 수치를 만들지 않습니다.

TradingView 설정 정의 참고:
https://www.tradingview.com/support/solutions/43000628599-strategy-properties/

- Pine `margin_long`/`margin_short`는 포지션 금액 중 자기자금으로 충당해야 하는
  **퍼센트**입니다. 주문 크기의 `default_qty_type/value`와 별개입니다. 예를 들어
  `margin_long=100`을 100배 레버리지, 100통화 고정 증거금 또는 주문크기 100%로
  해석하지 않습니다. 원본 설정의 의미와 실제 equity 경로 검증 가능성은 구분합니다.
- Pine `slippage`는 틱 수입니다. 퍼센트 비용 시나리오를 제안할 때는 틱 크기와
  가격별 환산 또는 별도 비용 모델이 필요하며 재실행 전에는 결과가 없습니다.
- `fill_orders_on_standard_ohlc`는 Heikin-Ashi 차트에서 실제 OHLC 체결가격을
  사용하도록 하는 옵션입니다. 표준 캔들에서 false인 사실은 OHLC 미사용의 증거가
  아닙니다. 하위 시간대 체결 재현을 사용하는 Bar Magnifier와도 별개입니다.
- `source_scope.equity_availability`가 저장본 0행을 명시하면 전체 saved_job에도
  곡선이 없습니다. 전체 거래·주문 목록을 받는 일과 자산곡선을 새로 확보하는 일을
  구분합니다. 검토자는 필요한 설정이 인계되지 않았다면 그 누락을 지적하되,
  공식적으로 정의된 설정을 여러 가상의 의미 중 하나라고 추측하지 않습니다.

- 최대 승리/손실의 **금액 최대값과 비율 최대값은 서로 다른 거래**일 수 있습니다.
  거래 ID와 개별 필드로 동일 거래임을 확인하기 전에는 둘을 한 거래의 금액·수익률로
  묶지 말고 별도의 집계 최대값으로 표시합니다. 평균 승패 금액·비율도 단위를 보존합니다.
- `settings.dateRange.trade`의 시작·끝은 공급자가 보고한 범위 경계입니다.
  이를 곧바로 실제 최초 진입일·마지막 청산일이라고 표현하지 않습니다.
  관측된 체결일은 저장된 거래의 `e.tm`/`x.tm`에서 별도로 확인해야 하며,
  표본이 잘렸다면 해당 표본의 체결일이라는 한계도 남깁니다.
- 슬리피지 0 또는 Bar Magnifier 미사용을 가격 갭 자체가 시뮬레이션에서
  사라졌다는 뜻으로 쓰지 않습니다. 기본 broker emulator도 봉 사이 갭과 다음
  봉의 시가를 처리합니다. 추가 체결 마찰·유동성·시장충격의 검증 한계와 구분합니다.
  공식 설명: https://www.tradingview.com/pine-script-docs/concepts/strategies/#broker-emulator
