# 이음온 (IumOn)

팀 **이음새**의 고령자 AI 복지 길잡이입니다. 충남 청양군 만 70세 이상 사용자가 생활 이야기로 필요한 지원을 찾고 상담·신청을 준비하도록 돕습니다.

생활 이야기 → 어려움 확인 → 가장 필요한 도움 → 관련 상황 질문 → 나이·지역 → 정책 후보·추가 조건 → 상담·신청 준비.

## 실행

Python 3.12 이상이 필요합니다. Windows에서는 `실행.bat`을 열고, 서버 시작 후 `앱 열기.url`을 엽니다.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r app/requirements.txt
cp app/.env.example app/.env
# app/.env에 본인의 API 연결 정보를 입력
python app/collect.py
python app/server.py
```

앱 주소: http://127.0.0.1:8765

실제 키, 공공 API 스냅샷, 분석 캐시와 사용자 상담 메모는 Git에 포함하지 않습니다. 소스만 복제한 경우 본인의 키를 설정하고 데이터를 수집해야 합니다. 로컬의 `.config.env`는 기기 전용 설정입니다.

## 검사

```sh
python scripts/check_repo.py
python -m unittest discover -s tests -p "test_repo_policy.py" -v
python -m unittest discover -s app -p test_app.py -v
```

CI에서는 `tests/fixtures/snapshot.json`의 **가상 테스트 자료**를 별도 임시 폴더에 복사해 앱 테스트를 실행합니다. 실제 인증키나 네트워크 요청을 사용하지 않습니다.

## 협업과 보안

`feat/설명`, `fix/설명`, `chore/설명` 브랜치에서 PR을 작성합니다. main은 승인 1명, 필수 검사, 대화 해결과 선형 이력을 기준으로 보호합니다. [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md)를 참고하세요.

## 현재 범위

텍스트 입력 PWA입니다. TTS/음성 입력과 네이티브 앱 패키징은 후속 단계입니다. 추천은 수급 자격 확정이 아니며 실제 신청을 자동 접수하지 않습니다. 라이선스는 팀 합의 후 결정합니다.
