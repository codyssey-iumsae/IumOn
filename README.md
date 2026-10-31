# 이음온 (IumOn)

팀 **이음새**가 만드는 고령자 AI 복지 길잡이입니다. 생활 속 어려움을 이야기하면 필요한 지원을 탐색하고 상담·신청을 준비할 수 있습니다.

대상은 **충남 청양군 만 65세 이상 주민**입니다. 현재 음성 입력·읽어주기를 지원하는 PWA이며 네이티브 앱 패키징은 후속 단계입니다.

## 서비스 흐름

생활 이야기 → 어려움 확인 → 필요한 도움 선택 → 관련 상황 질문 → 나이·거주 읍면 → 정책별 추가 질문 → 정책 후보·원문 설명 → 상담·신청 준비.

“무릎이 아픈데 병원에 갈 택시비가 부담돼요.”처럼 입력하면 지금 필요한 도움을 확인합니다. 질환·수급 자격을 추측하지 않고 모르는 답은 미확인으로 남깁니다. 정책 선택 후 공식 서류·문의처·확인 질문·내 상황 전달문을 정리하고 메모를 저장할 수 있습니다. 최종 선정 확정이나 실제 신청 접수 기능은 아닙니다.

## 기술 스택

| 영역 | 현재 구현 |
| --- | --- |
| 서버 | Python 3.12+, FastAPI, Pydantic, Uvicorn |
| 화면 | HTML, CSS, JavaScript (별도 빌드 도구 없음) |
| 앱 | Manifest·Service Worker 기반 PWA |
| LLM | Codyssey OpenAI 호환 Chat Completions, 기본 gpt-5.4-mini |
| 외부 통신 | Python urllib.request, JSON·XML 파싱 |
| 저장 | 공개 정책 JSON·상세 캐시, SQLite 정책 분석 캐시 |
| 검증·협업 | unittest, JavaScript 문법 검사, GitHub Actions, Dependabot |
| 실행 | PowerShell 통합 스크립트, Windows 배치 파일 |

소형모델은 아직 학습하지 않았으며 조건 추출·중복 비교·맞춤 설명 역할을 LLM이 대신합니다.

## 웹 사용 방법

1. 아래 서버 실행 절차를 완료합니다. 이후 PC에서는 **실행.bat**으로 서버를 켤 수 있습니다.
2. 같은 PC 브라우저에서 http://127.0.0.1:8765 에 접속합니다. 아직 공개 배포 주소는 없습니다.
3. AI 전송 동의를 확인하고 생활 이야기를 입력합니다. 이해한 어려움을 확인하고 필요한 도움을 선택합니다.
4. 질문에 답하고 후보의 조건·혜택·공식 출처를 확인합니다. 모르는 답은 건너뜁니다.
5. 상담·신청 준비 화면에서 신청 경로·서류·문의처를 확인하고 필요하면 메모를 저장합니다.

서버 창을 닫거나 Ctrl+C를 누르면 종료됩니다. 새로고침 시 답변·대화가 초기화되므로 필요한 메모는 먼저 저장하세요.

## 앱 사용 방법 (PWA)

현재 APK·IPA나 앱스토어 배포판은 없습니다. **휴대폰에서 접속할 수 있는 HTTPS 주소로 배포한 뒤** 홈 화면에 설치합니다. 휴대폰의 127.0.0.1은 PC 서버를 가리키지 않습니다.

- Android: Chrome에서 배포 주소 접속 → 메뉴 → 앱 설치/홈 화면에 추가 → 이음온 아이콘 실행.
- iPhone: Safari에서 배포 주소 접속 → 공유 → 홈 화면에 추가 → 이음온 아이콘 실행.
- PC: 지원 브라우저에서 배포 주소 접속 → 주소창/메뉴의 설치 기능 사용.

메뉴·지원 여부는 브라우저마다 다릅니다. 설치 후 문답·정책 확인·신청 준비는 웹과 같습니다. 글자·음성 입력과 선택 버튼을 함께 사용할 수 있습니다. 정책 조회·AI 분석에는 인터넷과 실행 중인 서버가 필요하며 설치만으로 오프라인 추천이 되지는 않습니다.

## 음성으로 사용하기

- 질문·정책 상세·신청 준비 화면의 **화면 읽어주기**를 누르면 한국어로 읽습니다. **음성 멈추기**로 중단합니다.
- **다음 질문 자동으로 듣기**는 이번 실행에서만 적용됩니다. 기기 음성 설치·브라우저 정책에 따라 재생이 제한될 수 있습니다.
- 이야기 입력란의 **말로 답하기**를 누르고 전송 안내에 동의한 뒤 마이크를 허용합니다. 선택형 질문은 선택지 문구 그대로 말하거나, ‘말하거나 직접 입력하고 싶어요’를 열어 자유롭게 답할 수 있습니다.
- 인식된 글·선택을 확인하고 수정한 뒤 다음으로 진행합니다. 자동 제출하지 않으며 기존 AI 전송 동의도 별도로 필요합니다. 나이가 숫자로 인식되지 않으면 직접 입력합니다.
- 음성 입력은 HTTPS/localhost와 지원 브라우저·마이크가 필요합니다. 미지원·권한 거부·인식 실패 시 기존 입력을 계속 사용할 수 있습니다. 브라우저별 지원과 품질은 다릅니다.
- Web Speech API를 사용합니다. 브라우저 제공업체가 음성을 외부 서비스로 보낼 수 있고, 읽어주기도 기기·브라우저 음성 서비스를 사용합니다. 이음온 서버는 음성 파일을 받거나 저장하지 않습니다. 외부 음성 API 키는 필요하지 않습니다.

## 서버 실행

Python 3.12 이상과 인터넷 연결이 필요합니다. 저장소 루트에서 실행합니다.

~~~powershell
Copy-Item app/.env.example app/.env
# app/.env에 본인의 키 입력
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/iumon.ps1 refresh
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/iumon.ps1 start
~~~

스크립트는 루트 .venv를 만들고 패키지를 설치합니다. 실행 위치에 관계없이 동작하며 설정 선택 순서는 APP_ENV_FILE → app/.env → 기존 기기의 .config.env입니다. 새 복제본에는 키·수집 자료가 없으므로 설정 후 refresh로 수집해야 합니다.

### 환경 변수

| 변수 | 설명 |
| --- | --- |
| DATA_GO_KR_KEY | 공공데이터포털 인증키 |
| LLM_BASE_URL | 연결 예: https://copa.codyssey.kr/v1 |
| LLM_MODEL | 기본 gpt-5.4-mini |
| LLM_API_KEY | Codyssey 키 |
| AUTO_REFRESH | 24시간 지난 자료 자동 갱신, 0으로 중지 |
| NATIONAL_DETAIL_DAILY_BUDGET | 중앙 상세 호출 일일 예산, 기본 20 |
| LOCAL_DETAIL_DAILY_BUDGET | 지자체 상세 호출 일일 예산, 기본 90 |
| APP_ENV_FILE | 별도 설정 파일 |
| IUMON_DATA_DIR | 데이터 폴더, 기본 app/data |

### 관리 명령

~~~powershell
# 데이터 갱신
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/iumon.ps1 refresh
# 정책 48개 사전 분석 (LLM 토큰 사용)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/iumon.ps1 analyze -Limit 48
# 가상 자료 테스트·저장소 검사
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/iumon.ps1 test
# 포트 변경
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/iumon.ps1 start -Port 8766
~~~

analyze -Limit 0은 전체 분석으로 시간·토큰 사용량이 커질 수 있습니다. 테스트는 별도 가상 자료로 실제 데이터를 보존합니다. Node.js가 있으면 JavaScript 문법도 검사하며 CI에서는 항상 검사합니다.

macOS/Linux는 가상환경을 만든 뒤 모듈을 직접 실행합니다.

~~~sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
cp app/.env.example app/.env
# 설정 후
python app/collect.py
python app/server.py
~~~

## 데이터와 추천 방식

| 데이터 | 활용 |
| --- | --- |
| 행정안전부 대한민국 공공서비스(혜택) 정보 | 정부24 목록·지원조건·상세 내용과 공식 서류 |
| 한국사회보장정보원 중앙부처복지서비스 | 중앙부처 복지 목록·상세 조건 |
| 한국사회보장정보원 지자체복지서비스 | 충남·청양 관련 복지 목록·상세 조건 |

지역·필요 분야로 검색하고 LLM이 추출한 조건·혜택·신청 경로의 원문 인용을 검증합니다. AND/OR 조건을 보존하며 **충족·미충족·미확인**으로 평가합니다. 동일 사업은 연결하되 원문·ID를 보존하고 별도 추가지원·조건 충돌은 구분합니다.

직접 관련된 정책을 우선 안내하고 같은 주기의 현금 지원처럼 비교 가능한 혜택만 검증한 금액으로 비교합니다. 월 지원·일회 지원·대출·돌봄을 임의 환산하지 않습니다. **선정확률·신청 편의성 가중치는 없습니다.** 방문·디지털 이용 가능 여부는 신청 준비 단계의 경로 안내에 사용하며 자격·순위를 바꾸지 않습니다.

우선 원문 18개를 분석하고 더 보기로 36/48개까지 확대합니다. 검색 누락·의미 해석 오류가 가능하며 인용 검증만으로 의미의 정확성까지 보장하지는 않습니다. 수집 일부 실패 시 기존 자료와 실패 표시를 유지합니다. 상세 캐시의 목록 수정일·수집 시각을 확인하며 호출 예산은 이 앱의 사용량만 관리합니다.

## 코드 구조

~~~text
app/
  server.py           API·문답·추천 작업
  journey.py          생활 이야기·질문 순서·신청 준비
  collect.py          공공 API 수집
  analysis.py         조건 추출·원문 검증·분석 캐시
  engine.py           검색·중복 검토·조건 판정·추천 순서
  llm.py              OpenAI 호환 LLM 연결
  config.py           환경 변수·데이터 경로
  warm_analysis.py    공개 정책 사전 분석
  static/             화면·PWA
  test_app.py         앱 회귀 테스트
scripts/
  iumon.ps1           실행·갱신·사전 분석·테스트 진입점
  check_repo.py       키 형식·금지 경로 검사
tests/                저장소 검사·가상 정책 자료
.github/              CI·Dependabot·PR 템플릿
~~~

## 개발·커밋 규칙

최신 main에서 작업 브랜치를 만듭니다. 현재 PR·다른 사람 승인은 필수가 아닙니다. main에는 Repository hygiene·App tests 통과, 최신 main 반영과 대화 해결 규칙을 유지합니다. 관리자에게도 보호 규칙이 적용됩니다. 작업 브랜치의 CI가 통과한 커밋을 main으로 반영합니다. PR을 사용하면 Squash 병합 후 작업 브랜치를 자동 삭제합니다.

PR을 사용할 때도 커밋 메시지와 PR 제목은 **Conventional Commits** 형식입니다. type(scope): 설명에서 scope는 선택입니다.

~~~text
feat(journey): 생활 이야기 확인 질문 추가
fix(engine): 무릎 관련 정책 우선순위 수정
docs: README로 실행 안내 통합
ci: 오프라인 테스트 설정 수정
chore: 저장소 초기 설정 정리
~~~

종류는 feat, fix, docs, refactor, test, ci, build, perf, style, chore, revert를 사용합니다. 호환성이 깨지는 변경은 feat(api)!: ...와 본문의 BREAKING CHANGE:로 설명합니다. PR에는 문제·변경 후 동작·검증 결과를 적습니다.

CI는 앱 회귀 테스트 56개, 저장소 검사 테스트 5개, 음성 기능 테스트 10개와 JavaScript 문법을 검사합니다. 음성 테스트는 인식·합성 API를 모의하여 동의·중단·오류·화면 이동을 확인합니다. 실제 기기의 마이크 인식률·음질이나 API·LLM 정확성, 고령자 현장 사용성을 보장하는 검사는 아닙니다.

## 보안·개인정보

실제 키·토큰, 사용자 건강·소득·상담 내용·화면은 코드·이슈·PR·로그에 올리지 않습니다. .env·.config.env, 수집 자료·분석 캐시·상담 메모는 Git에서 제외합니다. 예제에는 자리표시자만 사용합니다. 알려진 일부 키 형식을 검사하지만 모든 비밀·이미지·과거 이력까지 탐지하지는 않습니다.

대화·답변은 브라우저 메모리에, 서버 작업은 메모리에 두고 15분 뒤 정리합니다. 개인 답변·맞춤 결과는 JSON·SQLite에 저장하지 않으며 저장한 공개 정책 ID만 기기 localStorage에 남습니다. AI 자유입력과 상황 정보 기반 설명은 각각 동의를 받습니다. 이미 외부에 전송한 요청을 소급 취소할 수는 없습니다.

민감한 문제는 공개 이슈 대신 관리자와 비공개로 공유합니다. 노출된 키는 제공업체에서 폐기·재발급해야 하며 파일·이력 삭제만으로 안전해지지는 않습니다. 외부 공개 배포·본인 인증·실제 접수·고령자 현장 평가는 아직 진행하지 않았습니다. 라이선스는 팀 합의 후 결정합니다.
