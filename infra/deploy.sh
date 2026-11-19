#!/bin/bash
# 소스 업로드 + 키 설정 + 서버 설치.  ./infra/deploy.sh [setup|code|deps]
#   setup : 처음 1회 (패키지·파이썬 라이브러리·모델·서비스 설치, 10~15분, 백그라운드 실행)
#   code  : 코드·nginx 설정만 다시 올리고 서비스 재시작 (기본값)
#   deps  : code + 라이브러리(requirements.txt)·화면 분석 모델 갱신 (몇 분, 끝날 때까지 기다림)
set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ROOT="$(dirname "$HERE")"
. "$HERE/state.env"
MODE="${1:-code}"
SSH="ssh -i $ROOT/secrets/whosaid_ed25519 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$ROOT/secrets/known_hosts -o ConnectTimeout=15"
T="root@$PUBLIC_IP"

# 웹 로그인 비밀번호·세션 서명 키 (처음 한 번 생성, secrets/web_login.txt 에 보관)
PASS_FILE="$ROOT/secrets/web_login.txt"
if [ ! -f "$PASS_FILE" ]; then
  umask 077; printf 'id=whosaid\npassword=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(9))')" > "$PASS_FILE"
fi
grep -q '^session_secret=' "$PASS_FILE" || printf 'session_secret=%s\n' "$(python3 -c 'import secrets;print(secrets.token_hex(32))')" >> "$PASS_FILE"
WEB_PASS="$(grep '^password=' "$PASS_FILE" | cut -d= -f2-)"
WEB_SECRET="$(grep '^session_secret=' "$PASS_FILE" | cut -d= -f2-)"

echo "[1] 소스 업로드 → $PUBLIC_IP:/opt/whosaid/app"
$SSH "$T" "mkdir -p /opt/whosaid/app"
tar -C "$ROOT/app" --exclude='__pycache__' --exclude='.pytest_cache' -czf - . | $SSH "$T" "tar -C /opt/whosaid/app -xzf - && chmod +x /opt/whosaid/app/deploy/*.sh"

echo "[2] /etc/whosaid.env (키 값은 화면에 출력하지 않음)"
{
  grep -E '^(CLOVA_SPEECH_INVOKE_URL|CLOVA_SPEECH_SECRET|HF_TOKEN|CLOVASTUDIO_API_KEY)=' "$ROOT/secrets/keys.env" | sed 's/[[:space:]]*$//'
  echo "WHOSAID_WEB_PASSWORD=$WEB_PASS"
  echo "WHOSAID_SECRET=$WEB_SECRET"
  echo "WHOSAID_DATA_DIR=/srv/whosaid/data"
  echo "WHOSAID_MODEL_DIR=/srv/whosaid/models"
  echo "HF_HOME=/srv/whosaid/models/hf"
  echo "WHOSAID_THREADS=8"
  echo "OMP_NUM_THREADS=8"
} | $SSH "$T" "umask 027; cat > /etc/whosaid.env; chgrp whosaid /etc/whosaid.env 2>/dev/null || true; echo ok"

if [ "$MODE" = "setup" ]; then
  echo "[3] 서버 설치 시작 (백그라운드, 로그: /root/whosaid-setup.log)"
  $SSH "$T" "nohup bash /opt/whosaid/app/deploy/setup_server.sh > /root/whosaid-setup.log 2>&1 &"
else
  if [ "$MODE" = "deps" ]; then
    echo "[3a] 라이브러리·화면 분석 모델 갱신"
    $SSH "$T" "cd /opt/whosaid && UV_CACHE_DIR=/tmp/whosaid-uv uv pip install -q --python /opt/whosaid/venv/bin/python -r app/requirements.txt --constraint <(printf 'torch==2.9.1+cpu\\ntorchaudio==2.9.1+cpu\\n') --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match && rm -rf /tmp/whosaid-uv && bash app/deploy/fetch_models.sh /srv/whosaid/models/vision"
  fi
  echo "[3] nginx 설정 갱신 + 서비스 재시작"
  $SSH "$T" "install -m 644 /opt/whosaid/app/deploy/nginx-whosaid.conf /etc/nginx/sites-available/whosaid && rm -f /etc/nginx/whosaid.htpasswd && nginx -t -q && systemctl reload nginx && chown -R whosaid:whosaid /opt/whosaid/app && systemctl restart whosaid-web whosaid-worker && systemctl is-active whosaid-web whosaid-worker nginx"
fi
echo "웹 주소: http://$PUBLIC_IP  (로그인 정보: secrets/web_login.txt)"
