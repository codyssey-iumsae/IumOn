# 사설망 GPU 임베딩 검색

모델은 [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)(MIT), dense 1024차원, 최대 2048 토큰 설정을 사용한다. 모델 revision을 고정하고 클라이언트·서버가 동일한 model identity를 확인한다. GPU 서버는 `10.1.2.25`, 기존 웹앱은 `10.1.1.25`에서 실행한다. 모델·CUDA 라이브러리는 웹앱 이미지에 넣지 않는다. 모델/API 사용료는 없지만 GPU 서버 비용은 별도이다.

## GPU 서버 설치

GPU 서버의 전용 디렉터리는 `/home1/ncloud/iumon-embedding`이다. Python 3.12 가상환경에 `gpu/requirements.txt`를 설치한다. PyTorch는 GPU 드라이버에 맞는 공식 CUDA wheel을 사용한다. 검증 환경은 NVIDIA L4, driver 580.159.04, torch 2.8.0 CUDA 12.8이다.

`gpu/server.py`를 전용 디렉터리에 복사하고 아래 항목을 `service.env`에 저장한다. 키는 충분히 긴 난수로 만들고 파일 권한은 600으로 제한한다. 키를 저장소나 이미지에 넣지 않는다.

```text
EMBEDDING_REVISION=<검증한 Hugging Face 모델 커밋 SHA>
EMBEDDING_API_KEY=<생성한 임베딩 서비스 전용 키>
```

`model-cache` 디렉터리를 만든 뒤 `gpu/iumon-embedding.service`를 `/etc/systemd/system/`에 설치하고 daemon-reload, enable --now를 실행한다. 모델은 최초 실행 시 내려받아 캐시한다. 서비스는 사설 IP 8790 포트에만 바인딩하고 Bearer 인증과 클라이언트 IP 제한을 사용한다(기본값: 앱 서버, GPU 서버 자체, loopback). 클라우드 방화벽에서도 앱 서버의 접근만 허용한다. 공용 터널로 이 포트를 공개하지 않는다. 사설망 HTTP이므로 망 외부로 연결할 때는 TLS 또는 암호화 터널이 필요하다.

## 앱 설정

기존 서버 전용 `/home1/ncloud/iumon-secrets/app.env`에 다음을 추가한다.

```text
EMBEDDING_URL=http://10.1.2.25:8790
EMBEDDING_API_KEY=<GPU 서버와 같은 키>
EMBEDDING_MODEL=BAAI/bge-m3@<GPU 서버의 revision>:dense:2048
```

코드 배포와 설정 후 앱만 재생성한다. 앱 시작 뒤 maintenance가 게시된 정책 카탈로그를 읽어 벡터를 만들고, 이후에는 바뀐 텍스트만 다시 생성한다. 요청 처리 중 정책 벡터를 생성하지 않는다. 수동 실행도 가능하다.

```sh
cd /home1/ncloud/iumon
sudo docker compose up -d --no-deps --force-recreate app
sudo docker compose exec app python embeddings.py
```

벡터는 기존 영속 데이터 폴더의 `policy-vectors.sqlite3`에 별도로 저장한다. 모델 identity와 정책 텍스트 해시가 키이므로 모델·원문이 다르면 이전 벡터를 사용하지 않는다. 일부 색인만 준비되면 전체 기존 검색으로 처리한다. 오래된 모델/텍스트 벡터는 자동 삭제하지 않으므로 운영자가 보존 기간을 정해 정리한다.

## 검색 동작과 개인정보

생활 이야기에서 확인한 어려움 요약과 정책 검색어만 GPU 서버에 전송한다. 나이·주소·수급 여부 등 프로필 전체는 보내지 않는다. 이야기 요약에도 건강 등 민감한 내용이 있을 수 있으므로 자체 GPU 서버를 앱의 처리 인프라로 관리한다. 입력과 질문 벡터는 저장하거나 요청 로그에 기록하지 않는다. 공개 정책 벡터만 SQLite에 저장한다.

기존 검색 상위 60개와 dense 검색 상위 60개를 RRF로 합쳐 LLM 분석 후보를 찾는다. 기존 자격 판단·원문 인용 검증·최종 추천 순서 규칙은 유지한다. GPU 장애·2초 쿼리 타임아웃·모델 불일치·벡터 누락 시 기존 검색으로 돌아간다. 임베딩 점수는 자격 충족 여부나 선정확률이 아니다.

끄려면 앱 환경에서 `EMBEDDING_URL`을 비우고 앱만 재생성한다. 정책 원본·분석 DB는 삭제할 필요가 없다. GPU 서비스 변경은 앱 자동 배포가 설치하지 않으므로 GPU 서버에 별도로 배포하고 모델 identity를 함께 맞춘다.

## 소규모 실제 정책 평가 (2026-11-01)

게시된 공개 정책 1,338건과 가상 생활 이야기 10개를 사용했다. 실제 생활이야기 이해·검색어 확장 코드를 먼저 실행한 동일 프로필로 두 검색을 비교했다. 사례별 예상 관련 정책 ID 19개 중 상위 18건 안에 들어온 수는 기존 검색 13개, GPU 결합 검색 19개였다. GPU 서버 내부 측정에서 벡터 요청과 결합 검색은 0.408~0.457초, 중앙값 약 0.418초였다. 웹앱 전체 응답 시간이나 동시 접속 성능 측정은 아니다.

이 결과는 10개 고정 사례에 대한 후보 회수 비교이며 전체 정확도·지원 자격 판정 평가가 아니다. 더 넓은 사례와 실제 이용자 표현으로 추가 확인해야 한다. `scripts/evaluate_embeddings.py`에 사례와 관련 정책 ID를 명시했다. 동일 기준으로 재평가하려면 공개 카탈로그 JSON과 실제 이야기 정리 단계에서 얻은 가상 프로필 JSON을 전달한다. 임베딩 모델 학습·미세조정은 하지 않았다.
