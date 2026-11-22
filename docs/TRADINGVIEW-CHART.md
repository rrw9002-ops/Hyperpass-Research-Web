# TradingView 차트 연결

`chart` 모드는 TradingView Desktop에서 사용자가 이미 열어 둔 차트의 **OHLCV 봉,
시간주기, 통화, 로드된 지표 이름과 데이터 창 표시값**을 읽습니다. 공개 스크리너와
다른 경로입니다. Codex·MCP 서버·Node 설치는 필요하지 않습니다.

1. TradingView Desktop의 작업을 저장하고 앱을 정상 종료합니다.
2. 사용자가 직접 아래 디버그 옵션으로 실행합니다. 이 웹앱은 앱 종료나 디버그
   옵션 설정을 자동으로 수행하지 않습니다.
3. 원하는 차트와 지표를 열고 로딩을 기다립니다.
4. Hyperpass의 데이터 연결 → TradingView에서 `chart`, 포트 `9222`,
   정확한 `거래소:종목`을 입력하고 실제 조회로 연결을 확인합니다.

Mac의 기본 설치 경로에서는 터미널에서 다음과 같이 실행할 수 있습니다.

```sh
/Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=9222
```

Windows에서는 실제 설치된 `TradingView.exe` 경로로 실행합니다. 일반 설치의 예:

```powershell
& "$env:LOCALAPPDATA\TradingView\TradingView.exe" --remote-debugging-port=9222
```

Microsoft Store 설치는 설치 경로와 해당 빌드의 디버그 지원이 다를 수 있습니다.
해당 위치에 파일이 없으면 위 명령을 반복하지 말고 실제 설치 경로를 확인합니다.
일부 Store 빌드는 디버그 포트를 열지 않아 연결할 수 없습니다. 이 앱은 설치파일을
복제하거나 권한을 바꾸는 방식으로 우회하지 않습니다.

디버그 포트는 `127.0.0.1`에서만 사용하고 외부에 노출하지 마세요. 이 앱은 해당
포트로 **고정된 읽기 전용 getter**만 호출합니다. 종목·시간주기 변경, 지표 추가,
Pine 실행, 주문, 계좌, 쿠키·토큰 읽기는 제공하지 않습니다. CDP 자체는 강한 디버그
권한을 제공하므로 사용 후 필요 없으면 TradingView를 종료하고 평소처럼 다시 엽니다.

심볼이 일치하는 열린 차트만 읽으며 자동으로 다른 종목을 선택하지 않습니다.
최대 500개의 이미 로드된 봉을 읽고 새 과거 데이터를 강제로 로딩하지 않습니다.
마지막 봉은 진행 중일 수 있습니다. `as_of`는 봉 시작 시각이며 실시간 완료 시각이
아닙니다. 지표 값은 데이터 창의 표시값으로, 마우스 커서가 가리키는 봉일 수 있어
관측 봉 시각을 `data_window_selection_unknown`으로 표시합니다. 마지막 OHLCV 봉과
동일 시점이라고 가정하지 않습니다. 표시값에는 포맷·단위·반올림이 적용될 수 있습니다.

TradingView 내부 getter는 공식 외부 데이터 API가 아니므로 앱 업데이트에 따라
바뀔 수 있습니다. 표시되지 않거나 접근할 수 없는 지표는 생성하지 않습니다.
조회 실패 시 `scanner` 또는 사용자가 직접 내보낸 `csv`를 명시적으로 선택할 수
있지만, 이를 차트 연결 성공으로 표시하지 않습니다. 데이터 이용 권한은 사용자의
TradingView 계정·거래소 구독·서비스 약관을 따릅니다.

참고한 읽기 인터페이스: tradesdontlie의 tradingview-mcp 로컬 배포본
`src/connection.js`, `src/core/chart.js`, `src/core/data.js` (MIT).
저작권 고지와 라이선스는 `TRADINGVIEW-THIRD-PARTY-LICENSE.txt`에 포함했습니다.
이 웹앱의 WebSocket/CDP 전송 코드는 Python 표준 라이브러리로 별도 구현했습니다.
