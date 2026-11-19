#!/bin/bash
# 화면 속 화자 찾기(SPEC-009) 모델 3개를 /srv/whosaid/models/vision 에 준비합니다. 이미 있으면 건너뜁니다.
#   - YuNet 얼굴 찾기, SFace 얼굴 특징: OpenCV 공식 Hugging Face 저장소(Apache-2.0)
#   - YOLO11n-seg 사람 분할: Ultralytics 공식 가중치(AGPL-3.0)를 임시 가상환경에서 ONNX로 내보냄
# 사용: sudo bash fetch_models.sh [대상 폴더]
set -euo pipefail
DIR="${1:-/srv/whosaid/models/vision}"
mkdir -p "$DIR"
cd "$DIR"

get() {  # 이름 URL sha256
  if [ -f "$1" ] && echo "$3  $1" | sha256sum -c --quiet - 2>/dev/null; then echo "  있음: $1"; return; fi
  curl -fsSL -o "$1.part" "$2"
  echo "$3  $1.part" | sha256sum -c --quiet -
  mv "$1.part" "$1"
  echo "  받음: $1"
}

echo "[1/2] 얼굴 모델"
get face_detection_yunet_2023mar.onnx \
  https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx \
  8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4
get face_recognition_sface_2021dec.onnx \
  https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx \
  0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79

echo "[2/2] 사람 분할 모델(YOLO11n-seg → ONNX)"
if [ -f yolo11n-seg.onnx ]; then
  echo "  있음: yolo11n-seg.onnx"
else
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  export UV_CACHE_DIR="$TMP/cache"
  uv venv -q --python 3.12 "$TMP/venv"
  # CPU 전용 torch로 고정(CUDA 휠 수 GB 방지). 내보내기가 끝나면 임시 환경은 지웁니다.
  uv pip install -q --python "$TMP/venv/bin/python" "ultralytics==8.4.215" onnx onnxslim \
    "torch==2.9.1+cpu" "torchvision==0.24.1+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
  (cd "$TMP" && YOLO_OFFLINE=0 "$TMP/venv/bin/python" -c "
from ultralytics import YOLO
YOLO('yolo11n-seg.pt').export(format='onnx', imgsz=640, opset=17, simplify=True)
")
  mv "$TMP/yolo11n-seg.onnx" yolo11n-seg.onnx
  echo "  만듦: yolo11n-seg.onnx"
fi
chown -R whosaid:whosaid "$DIR" 2>/dev/null || true
ls -la "$DIR"
