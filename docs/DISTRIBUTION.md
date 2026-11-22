# 강사용 배포 안내 · v0.4.1-preview

Windows, Apple Silicon Mac, Intel Mac용 실행 파일을 각각 해당 OS에서 빌드합니다.
실행 파일 ZIP에는 Python이 포함되어 수강생이 Python이나 Codex를 설치할 필요가
없습니다. 소스 ZIP만 사용할 때는 Python 3.11 이상이 필요합니다.

2026-11-22 [GitHub Actions 실행 `45009985262`](https://github.com/rrw9002-ops/Hyperpass-Research-Web/actions/runs/45009985262),
커밋 `6e7c0f7`에서 Windows x64·macOS arm64·macOS x86_64 작업이 모두 성공했습니다.
각 OS에서 Python 3.11.9와 PyInstaller 6.22.3을 사용했고 단위 검사 175개, 소스 설치·단독
실행 파일·압축 해제 ZIP의 각 9개 HTTP 설치 점검을 통과했습니다.
검증 JSON과 단위 검사 로그는 해당 실행의 `validation-v0.4.0-preview-*` 아티팩트에 있습니다.
작업 폴더에는 `.ci/45009985262/validation-v0.4.0-preview-*/`로 보관했습니다.
이 결과는 고정 데모·합성 CSV·로컬 실패 응답을 사용하는 네이티브 CI 설치 점검입니다.
실제 사용자 Mac의 GUI·Gatekeeper·서명·공증·TradingView 연동을 검증한 결과는 아닙니다.
실제 AI는 `gpt-5.4`·추론 `medium`로 백테스트 해석 보고서의 전체 완료를 확인했습니다.
기존 등록 키 프로세스에서 확인한 결과이며 새 EXE의 유료 호출 검사와는 구분합니다.
이번 릴리스의 정확한 커밋·CI 결과·SHA-256은 첨부 검증 JSON을 기준으로 확인하세요.

GitHub Actions가 통과한 아티팩트와 해당 검증 결과를 함께 확인하고 배포하세요.
CI의 통과는 외부 AI 모델이나 실제 TradingView에서의 실행 검증을 대신하지 않습니다.
현재 문서·다음 배포의 버전은 `v0.4.1-preview`입니다. 위 CI 기록은 `6e7c0f7`의
`v0.4.0-preview` 이름으로 생성됐으므로 다른 커밋의 파일까지 검증된 것으로 취급하지 않습니다.
강사는 배포할 파일의 커밋과 검증 결과, 실제 키·차트 확인 기록을 함께 검토합니다.

## 포함할 파일

`tools/build_release.py`와 PyInstaller spec은 같은 허용 목록을 사용합니다.

- 앱 소스, 화면 자원, 시작 파일, 원본 출처 기록과 기본 분석 방법.
- `team/common.md` 1개, `team/roles/` 10개, `team/skills/` 10개,
  `team/references/` 12개: 고정 33개 문서만 포함.
- OS별 빌드 옵션을 선택한 경우 해당 실행 파일.

`team/.history`, `team/.edit-lock`, 임시 파일, 사용자 연구 데이터, API 키,
SQLite 기록과 미등록 역할 파일은 포함하지 않습니다. 배포 작업은 깨끗한 저장소
체크아웃에서 수행하세요. 33개 기본 문서에 작성한 사용자 내용도 배포본에 들어가므로
개인 내용을 넣은 로컬 작업 폴더를 원본 배포용 체크아웃으로 사용하지 마세요.

## 로컬 빌드와 검사

개발·배포 담당자가 실행하는 명령입니다. 수강생에게 빌드를 요구하지 않습니다.

```text
python -m unittest discover -s tests -v
python tools/smoke_installed.py --source . --output validation/source-smoke.json
python -m pip install pyinstaller==6.22.3
python -m PyInstaller --clean --noconfirm Hyperpass-Research-Web.spec
```

Windows에서 다음을 실행합니다.

```text
python tools/smoke_installed.py --executable dist/Hyperpass-Research-Web.exe --output validation/frozen-smoke.json
python tools/build_release.py --windows
python tools/smoke_installed.py --archive dist/Hyperpass-Research-Web-Windows.zip --output validation/archive-smoke.json
```

Apple Silicon Mac에서는 다음을 실행합니다. Intel Mac에서는 `arm64`를 `x86_64`로
바꿉니다. 다른 CPU의 실행 파일 이름만 바꾸어 배포하지 마세요.

```text
python tools/smoke_installed.py --executable dist/Hyperpass-Research-Web --output validation/frozen-smoke.json
python tools/build_release.py --mac --architecture arm64
python tools/smoke_installed.py --archive dist/Hyperpass-Research-Web-macOS-arm64.zip --output validation/archive-smoke.json
```

소스 ZIP만 만들려면 `python tools/build_release.py`를 실행합니다. 각 ZIP 옆에
SHA-256 파일이 생성됩니다. `Start-Windows.cmd`는 EXE를, `Start-Mac.command`는
Mac 실행 파일을 우선 실행합니다. 실행 파일이 없는 경우 Python 소스를 실행합니다.
Mac ZIP의 실행 파일과 `.command`에는 실행 권한 `755`를 기록합니다.

실행 파일만 새 폴더에 복사해도 번들 내부의 기본 지침과 출처로 `team/`을 처음
생성합니다. 기존 파일은 덮어쓰지 않습니다. 이미 편집한 지침을 유지하려면 새
버전의 기본 `team/` 폴더를 기존 폴더 위에 그대로 덮어쓰지 마세요.

## GitHub Actions

`.github/workflows/validate.yml`은 main push, PR, 버전 태그, 수동 실행을 지원합니다.
Windows `windows-2022`, Apple Silicon `macos-15`, Intel `macos-15-intel`에서
Python 3.11과 PyInstaller 6.22.3으로 각각 빌드합니다. Mac 라벨과 CPU는
[GitHub 공식 runner 문서](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)를 기준으로 지정했습니다.

각 OS에서 전체 단위 테스트 → 독립 소스 설치 점검 → 실행 파일 빌드 → 실행 파일
초기 지침 생성 점검 → ZIP 생성 → 실제 압축 해제본 점검 순서로 진행합니다.
모든 단계가 성공해야 OS별 배포 ZIP과 SHA-256을 업로드합니다. 검증 로그와 JSON은
실패 시에도 별도 `validation-v0.4.1-preview-*` 아티팩트로 업로드합니다.

## 검증 결과의 범위

설치 점검은 한글·공백이 있는 임시 폴더와 임시 데이터베이스에서 앱을 별도
프로세스로 실행하고 실제 localhost HTTP 요청을 보냅니다. 기존 앱이나 강사
컴퓨터의 저장 자료를 건드리지 않으며, 자신이 시작한 프로세스만 종료합니다.

- 페이지와 화면 자원, 팀 33개 문서, 편집·백업·충돌 방지·경로 차단.
- 합성 CSV 120행의 지표·로컬 백테스트 계산, JSON/Pine 내보내기.
- 명시된 고정 데모의 역할 배정·근거 채택·독립 검토·최종 보고서 및 지침 버전 기록.
- 호출 한도에서 미완료 상태와 100% 미만 진행률 유지.
- 차트가 없는 로컬 모의 서버에서 TradingView 작업 실패를 정확히 기록.
- 데모와 실제 AI 보고서의 라이브러리 분리, 임시 프로세스 종료.

다음은 별도로 검증하고 기록해야 합니다.

- OpenAI·Claude·Gemini의 실제 키, 선택 모델, 추론 강도, 실제 분석 응답.
- KIS·FMP·Yahoo·OpenBB 등 실제 데이터 연결과 계정별 허용 범위.
- 실제 TradingView Desktop 버전의 차트 설정, Pine 컴파일, Strategy Tester 결과.
- 실제 사용자 Mac에서 다운로드 후 시작, 브라우저 열기 및 Gatekeeper 처리.

Mac 빌드 설정은 Apple 개발자 서명·공증을 제공하지 않습니다. 위 Mac 네이티브 CI 성공은
다운로드한 파일의 Gatekeeper 통과를 검증한 결과는 아닙니다. 검증되지 않은 항목을
완료로 표시하거나 모의 결과를 실제 시장 성과로 안내하지 마세요.
