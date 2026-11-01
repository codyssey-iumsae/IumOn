# 사설망 서버 자동 배포

`main` 병합 → GitHub Actions **Repository hygiene** 성공 → 서버 timer가 약 2분마다 확인 → 검사한 SHA의 앱 빌드·교체 → healthcheck 확인 순서로 동작한다. PR 검사나 실패한 CI로는 배포하지 않는다. 더 최신 main이 있으면 오래된 배포를 건너뛴다.

서버에서 GitHub HTTPS로 나가는 통신만 사용한다. 공개 저장소 API이므로 GitHub 토큰·Secrets·외부 SSH 개방이 필요 없다. API 오류나 호출 제한 시 배포하지 않고 다음 주기에 재시도한다.

## 최초 설정

VPN으로 서버에 접속한 뒤 진행한다. Dockerfile·Compose는 서버에서 확인한 운영 파일을 저장소에 반영했다. 소스가 Git checkout이 아닌 경우 기존 소스를 로컬 Git 커밋으로 먼저 보존하고 origin을 연결해야 한다. 파일이 충돌하면 비교해서 일치시키며 강제 reset이나 삭제를 하지 않는다.

필수 조건:

- `/home1/ncloud/iumon`은 이 저장소의 Git checkout이고 origin이 이 저장소를 가리킨다.
- Compose 프로젝트 이름 `iumon`, 서비스 이름 `app`·`tunnel`, 앱 Docker healthcheck가 기존 설정과 일치한다.
- 데이터는 `/home1/ncloud/iumon-data`, 설정은 `/home1/ncloud/iumon-secrets/app.env`를 사용한다. 데이터·설정을 이미지에 넣지 않도록 Dockerfile과 `.dockerignore`를 검토한다.
- `ncloud`는 소스 쓰기, origin 읽기, 비대화형 `sudo -n docker ...` 실행이 가능해야 한다. Docker 권한은 관리자 권한에 준하므로 main 변경 권한을 제한한다.
- Python 3, bash, git, flock, curl, Compose와 GitHub·패키지 저장소·이미지 레지스트리로의 외부 통신이 필요하다.

PR 병합 후 운영 파일을 정리하고 서버 main을 갱신한 다음 실행한다. Compose 파일명은 실제 이름으로 바꾼다.

```sh
cd /home1/ncloud/iumon
git status --short
git remote get-url origin
# 추적 파일 수정과 운영 설정을 보존·정리한 뒤 실행
git fetch origin main
git checkout --detach origin/main
printf '%s\n' /home1/ncloud/iumon/compose.yaml > .deploy-compose-path
sudo -n docker compose -p iumon --profile demo config --quiet
sudo -n docker compose -p iumon ps

sudo install -d -m 755 /opt/iumon-deploy
sudo install -m 644 scripts/poll-deployment.py /opt/iumon-deploy/poll-deployment.py
sudo install -m 644 deploy/iumon-deploy.service /etc/systemd/system/
sudo install -m 644 deploy/iumon-deploy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start iumon-deploy.service
sudo journalctl -u iumon-deploy.service -n 100 --no-pager
cat /home1/ncloud/iumon-deployed-sha
# 첫 배포 성공과 앱·터널 상태를 확인한 뒤 활성화
sudo systemctl enable --now iumon-deploy.timer
```

Compose가 여러 파일이나 별도 `--env-file`을 요구하면 스크립트를 실제 운영 명령에 맞춰 수정한다. `.deploy-compose-path`는 Compose 파일 하나의 절대 경로이다. 설치한 poller·systemd 파일은 자동 교체하지 않으므로 변경 시 서버에도 다시 설치한다.

## 운영과 복구

```sh
systemctl list-timers iumon-deploy.timer
sudo journalctl -u iumon-deploy.service -n 100 --no-pager
# 자동 배포 중지
sudo systemctl stop iumon-deploy.timer
```

서버 flock으로 배포를 직렬화한다. 기존 이미지를 `iumon-app:rollback-...`으로 보존하고 빌드 후 앱만 교체한다. healthcheck·로컬 `/api/status` 실패 시 이전 checkout·이전 이미지로 복구를 시도하고 실패 로그를 남긴다. 다음 timer 주기에 재시도하므로 반복 실패 시 timer를 중지하고 수정한다. 성공한 SHA는 `/home1/ncloud/iumon-deployed-sha`에 기록한다.

tunnel을 재생성하거나 `compose down`을 실행하지 않는다. 앱 교체 중 짧은 접속 중단은 생길 수 있다. 배포 후 detached HEAD가 되므로 이후 갱신은 자동 배포로 수행한다.

이미지 복구는 JSON·SQLite 변경을 되돌리지 않는다. 데이터 형식 변경 전 별도 백업이 필요하다. 이전 이미지 태그는 자동 삭제하지 않으므로 보존 기간을 정해 관리한다. 외부 HTTPS·휴대폰 음성·실제 LLM 요청은 자동 검사에 포함되지 않는다. 정상 배포 후 과거 버전으로 돌아갈 때는 main에 revert PR을 병합한다.
