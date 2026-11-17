#!/bin/bash
# VoxPrism 서버 설치 스크립트 (내부 코드명 whosaid) (Ubuntu 22.04, root로 실행)
#   전제: /opt/whosaid/app 에 소스, /etc/whosaid.env 에 키가 올라와 있어야 합니다.
#   사용: bash /opt/whosaid/app/deploy/setup_server.sh   (웹 비밀번호는 /etc/whosaid.env 의 WHOSAID_WEB_PASSWORD)
set -euo pipefail
APP=/opt/whosaid/app
VENV=/opt/whosaid/venv
export DEBIAN_FRONTEND=noninteractive

echo "[1/6] 패키지 설치"
PKGS="ffmpeg nginx apache2-utils fonts-noto-cjk libsndfile1 git curl ca-certificates rsync"
apt-get update -y -q
# NCP 서버는 IPv6가 꺼져 있어 nginx 기본 사이트의 'listen [::]:80' 때문에 설치 마무리가 실패할 수 있음 → 고친 뒤 마무리
apt-get install -y -q $PKGS || true
[ -f /etc/nginx/sites-available/default ] && sed -i '/listen \[::\]/d' /etc/nginx/sites-available/default
dpkg --configure -a
apt-get install -y -q $PKGS

echo "[2/6] 서비스 계정·폴더"
id whosaid >/dev/null 2>&1 || useradd --system --home-dir /opt/whosaid --shell /usr/sbin/nologin whosaid
mkdir -p /srv/whosaid/data/jobs /srv/whosaid/models/hf
chown -R whosaid:whosaid /srv/whosaid
chmod 755 /srv/whosaid /srv/whosaid/data /srv/whosaid/data/jobs
chown root:whosaid /etc/whosaid.env && chmod 640 /etc/whosaid.env

echo "[3/6] Python 3.12 가상환경 (uv)"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh
fi
export UV_PYTHON_INSTALL_DIR=/opt/whosaid/python UV_CACHE_DIR=/opt/whosaid/.uv-cache
[ -x "$VENV/bin/python" ] || uv venv --python 3.12 "$VENV"

echo "[4/6] 라이브러리 설치 (CPU 전용 PyTorch로 고정)"
# 고정하지 않으면 pytorch-metric-learning 3.x가 CUDA용 최신 torch(수 GB)를 끌어옵니다.
printf 'torch==2.9.1+cpu\ntorchaudio==2.9.1+cpu\n' > /tmp/whosaid-constraints.txt
uv pip install --python "$VENV/bin/python" -r "$APP/requirements.txt" "torchcodec==0.8.*" pyarrow \
  --constraint /tmp/whosaid-constraints.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
rm -rf "$UV_CACHE_DIR"
chown -R whosaid:whosaid /opt/whosaid

echo "[5/6] systemd 서비스"
install -m 644 "$APP/deploy/whosaid-web.service" /etc/systemd/system/whosaid-web.service
install -m 644 "$APP/deploy/whosaid-worker.service" /etc/systemd/system/whosaid-worker.service
systemctl daemon-reload
systemctl enable --now whosaid-web whosaid-worker
systemctl restart whosaid-web whosaid-worker

echo "[6/6] nginx (앱 로그인 확인 후 미디어 직접 전송)"
rm -f /etc/nginx/whosaid.htpasswd
install -m 644 "$APP/deploy/nginx-whosaid.conf" /etc/nginx/sites-available/whosaid
ln -sf /etc/nginx/sites-available/whosaid /etc/nginx/sites-enabled/whosaid
rm -f /etc/nginx/sites-enabled/default
# 1차시 Init Script처럼 apache2가 80번을 쓰고 있으면 끕니다
systemctl disable --now apache2 2>/dev/null || true
nginx -t && systemctl enable nginx && systemctl restart nginx
echo "설치 완료"
