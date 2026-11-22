# 데이터와 AI 연결하기

처음에는 키 없이 차트 연구실에서 `삼성전자` 또는 `AAPL`을 조회할 수 있습니다. 국내 현재가를 직접 받을 때는 KIS를, 에이전트가 보고서를 작성할 때는 AI 서비스를 한 곳 연결하세요.

## 국내 스크리너에 한국투자증권 KIS 연결하기

**스크리너 → 국내**에는 한국투자증권의 코스피·코스닥 종목 마스터가 들어옵니다. 공식 파일의 기준가, 전일 거래량, 전일 기준 시가총액, 재무 기준일을 확인할 수 있습니다. 기준가는 권리락 등에 따라 직전 종가와 차이가 날 수 있습니다. 장중 현재가와 누적 거래대금을 받으려면 KIS를 연결하세요. [KIS 종목정보파일](https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info)

1. KIS Developers의 **API 신청**에서 본인 계좌의 **실전투자** Open API 서비스를 신청하고 발급된 **App Key와 App Secret**을 준비합니다. 가입·서비스 신청은 본인의 한국투자증권 계정에서 진행하세요. [KIS Developers](https://apiportal.koreainvestment.com/) · [한국투자증권 공식 연동 예제](https://github.com/koreainvestment/open-trading-api)
2. 앱 상단 **데이터 연결 → 한국투자증권 KIS**를 엽니다. App Key와 App Secret을 각각 입력하고 **검사 / 수집 종목 코드**에 `005930`을 입력합니다. 이 앱의 입력 항목은 두 키와 조회할 종목 코드입니다.
3. **실제 조회로 연결 확인**을 누릅니다. **실제 조회 성공** 또는 **조회 확인됨**이 표시되면 삼성전자 시세를 읽은 것입니다.
4. **스크리너 → 국내**에서 시세를 갱신합니다. KIS API는 여러 종목을 나누어 호출합니다. 수집 상태가 완료되면 **현재가**와 **누적 거래대금**을 확인하세요. 수신 시각은 앱이 응답을 받은 시각이고, 재무 지표의 기준일은 별도입니다. **이 페이지 KIS 상세 시세·PER 갱신**을 누르면 현재 페이지의 종목에 KIS가 제공하는 PER·PBR도 조회합니다. 이후 PER 조건으로 검색할 때는 **항목별 출처와 제공 종목 수**에서 몇 종목에 값이 있는지 확인하세요.
5. API 키를 등록하지 않은 상태에서는 마스터의 **기준가**가 표시됩니다. 마스터와 복수종목 시세 API가 제공하지 않는 PER·PBR 등에는 빈칸이 생길 수 있습니다. 키 등록 전에도 국내 전 종목에 PER 등 조건을 적용해 보려면 **미제공 재무 지표 보강 · TradingView**를 선택해 조회합니다. 실제로 값이 제공된 종목만 해당 조건을 통과하며, 보강한 항목은 TradingView 출처로 표시됩니다.

**인증 오류가 나면** 실전용 키 쌍이 맞는지, 두 입력란이 뒤바뀌지 않았는지 확인합니다. 호출 제한이 표시되면 현재 수집이 끝난 뒤 잠시 기다려 다시 조회하세요. [KIS 복수종목 시세 명세](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/intstock_multprice) · [KIS 현재가 명세](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/inquire_price)

## 미국 스크리너에서 Yahoo Finance 사용하기

1. **스크리너 → 미국**을 고릅니다. Yahoo Finance 공개 데이터는 별도 키 없이 조회합니다.
2. 시세 수집이 끝나면 `AAPL`을 검색해 종목 이름, 티커, 통화, 출처를 확인합니다. 결과 표의 기준 시각과 갱신 상태를 확인한 다음 필터를 적용하세요.
3. 차트만 보고 싶다면 **차트 연구실 → Yahoo Finance**에서 종목·기간·봉 주기를 고릅니다. 국내 종목은 `삼성전자`, `005930`, 미국 종목은 `애플`, `AAPL`처럼 입력합니다. 동명이거나 여러 거래소에서 거래되는 종목은 검색 결과의 코드를 확인하세요.

휴장·주말에는 직전 거래 세션 자료일 수 있습니다. Yahoo는 거래소·상품에 따라 지연 자료를 제공하며 공개 데이터 연결을 일시적으로 제한할 수 있습니다. 조회 시간이 갱신돼도 가격의 거래일은 그대로일 수 있습니다. [Yahoo 거래소별 데이터 및 지연 안내](https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html)

## TradingView 차트와 CSV 연결하기

1. Windows 또는 Mac에 TradingView Desktop을 설치하세요. 앱 차트를 불러오는 데 TradingView API 키는 필요 없습니다. [TradingView Desktop 공식 다운로드](https://www.tradingview.com/desktop/)
2. Hyperpass에서 **차트 연구실 → 차트 데이터 → TradingView · Desktop 차트 조회**를 선택하세요. 오른쪽에 **TradingView Desktop 연결하기**가 보이면 **Desktop 연결 실행**을 누릅니다. 일반 모드로 실행 중이어서 연결되지 않으면 TradingView에서 작업을 저장하고 앱을 완전히 종료한 뒤 이 버튼을 다시 누르세요. 기본 연결 포트는 `9222`입니다.
3. TradingView Desktop에서 종목 차트 하나를 엽니다. 로그인을 요청하면 본인 계정으로 로그인하세요. Hyperpass가 잠시 동안 열린 차트를 자동 확인합니다. 나중에 차트를 열었으면 **연결 확인 · 차트 조회**를 누릅니다. 사용할 탭을 선택하라는 안내가 보이면 오른쪽에서 실습에 쓸 탭을 고르세요. 그 탭의 종목·주기가 변경됩니다.
4. Hyperpass 종목 입력란에 `SK하이닉스` 또는 `000660`을 입력하세요. 오른쪽 제목에 **SK하이닉스 · 000660**, 출처에 **TradingView Desktop**과 봉 개수가 보이면 연결에 성공한 것입니다. 상단 **차트 조회**로 직접 다시 불러올 수 있습니다. KRX 지연 피드를 받으면 지연 시세로 표시됩니다. 이전 버전에서 저장한 Desktop 차트의 종목과 가격이 의심되면 같은 종목·주기를 새로 조회해 날짜별 가격을 대조하세요. 남기고 싶은 차트만 **이 차트를 Second Brain에 저장**을 누르세요.
5. 조회되는 기간은 Desktop이 해당 차트에 로드한 봉 수에 따라 달라지며 최대 500봉입니다. 원하는 봉 주기를 지정할 때는 **조회·지표에 사용할 Desktop 주기**를 사용합니다. 기존 Yahoo 차트의 조회 기간을 늘려도 Desktop의 봉 수가 늘지는 않습니다.
6. TradingView에서 내보낸 파일로 연습하려면 차트 데이터에서 **TradingView · CSV 가져오기**를 선택해 해당 종목의 CSV를 넣습니다. CSV의 통화·봉 주기를 실제 파일과 맞추고 조회합니다. CSV는 내보낸 시점의 자료를 재현합니다. [TradingView 차트 데이터 내보내기](https://www.tradingview.com/support/solutions/43000537255-how-to-export-chart-data/)

**Desktop 연결 실패**가 표시되면 이 PC에서 Desktop이 실행 중인지, 차트 탭이 열려 있는지, 포트가 일치하는지 확인하세요. **TradingView에서 열기**는 선택한 종목을 외부 웹 차트로 여는 링크입니다. 앱 안에서 Desktop 시세를 읽으려면 위 연결 단계가 필요합니다.

## AI 한 곳을 등록하고 리서치 시작하기

1. **리서치 팀 → API 연결하기** 또는 화면 상단의 AI 연결 메뉴를 엽니다. **OpenAI**, **Claude**, **Gemini** 중 사용할 서비스 한 곳을 선택합니다.
2. 해당 서비스의 개발자 계정에서 본인 프로젝트용 API 키를 발급합니다. OpenAI는 API 대시보드, Claude는 Claude Console, Gemini는 Google AI Studio에서 발급합니다. 웹 채팅 로그인·구독과 개발자 API의 사용 권한·한도·결제 설정은 따로 관리됩니다. [OpenAI API 시작 안내](https://developers.openai.com/api/docs/quickstart) · [Claude API 키 발급](https://platform.claude.com/docs/en/get-api-key) · [Gemini API 키 설정](https://ai.google.dev/gemini-api/docs/api-key)
3. 키를 앱의 **API 키** 칸에 붙여넣고 **모델 목록 불러오기**를 누릅니다. 본인 프로젝트에 표시되는 모델을 선택하거나 사용할 수 있는 모델 ID를 입력합니다. **연결 확인 후 시작**을 누르면 선택한 키와 모델로 소량의 실제 요청을 보냅니다.
4. **이번 질문의 AI**에서 연결한 서비스와 모델을 확인합니다. 질문별로 모델과 지원되는 **추론 강도**를 고를 수 있습니다. 목록에 원하는 강도가 없으면 모델 기본값으로 시작하세요.
5. **누구에게 물어볼까요?**에서 종합 분석 또는 특정 에이전트를 고르고 질문을 입력합니다. 예를 들어 `첨부 차트에 나타난 가격 추세와 이 자료만으로 판단하기 어려운 점을 정리해 주세요.`라고 요청할 수 있습니다. 개인 차트를 분석하려면 먼저 차트 연구실에서 조회한 차트를 분석에 연결하세요. **리서치 시작**을 누르고 단계별 진행 상태를 확인합니다.
6. 완료되면 **최종 보고서가 완성됐습니다**와 **최종 보고서** 탭이 표시됩니다. 이전 결과는 **Second Brain**에서 다시 엽니다.

**연결이 안 되면** 선택한 서비스의 키가 맞는지, 모델 사용 권한이 있는지, 프로젝트의 API 사용 한도와 잔액이 충분한지 확인하세요. 응답 속도 제한은 잠시 기다렸다 재시도합니다. 키는 실행 중인 로컬 서버의 메모리에 보관되므로 앱을 완전히 종료했다면 다시 입력하세요. 문의할 때는 오류 문구와 서비스·모델 이름만 공유하고 키 입력란은 가리세요.

## FMP와 OpenBB를 추가로 쓰는 경우

- **FMP**를 사용하려면 Financial Modeling Prep 개발자 대시보드에서 키를 발급하고 **데이터 연결 → FMP**에 입력하세요. 검사 종목에 `AAPL`을 넣고 **실제 조회로 연결 확인**을 누릅니다. 요금제별로 열 수 있는 엔드포인트와 호출 한도가 다릅니다. [FMP API 시작 안내](https://site.financialmodelingprep.com/developer/docs/quickstart)
- **OpenBB**를 쓰는 수강생은 자신의 PC에 필요한 OpenBB REST API와 데이터 제공자 확장을 설치하고 `openbb-api`를 실행합니다. 터미널에 표시된 포트와 설치한 API 버전을 **데이터 연결 → OpenBB**에 입력하세요. 기본 포트는 `6900`입니다. 앱은 v5의 Cboe 시세 또는 v4의 yfinance 가격 이력을 조회합니다. 설치된 서버에 사용하는 경로와 제공자가 있어야 합니다. 서버 인증을 켰다면 해당 서버의 사용자명·비밀번호를 함께 입력한 뒤 `AAPL`로 연결을 확인하세요. [OpenBB REST API 시작 안내](https://docs.openbb.co/odp/python/quickstart/rest_api)
