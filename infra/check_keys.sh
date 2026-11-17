#!/bin/bash
# keys.env에 값이 채워졌는지만 확인합니다. (값 자체는 출력하지 않음)
F="$(dirname "$(readlink -f "$0")")/../secrets/keys.env"
for k in NCLOUD_ACCESS_KEY NCLOUD_SECRET_KEY CLOVA_SPEECH_INVOKE_URL CLOVA_SPEECH_SECRET HF_TOKEN CLOVASTUDIO_API_KEY; do
  v=$(grep -E "^${k}=" "$F" | head -1 | cut -d= -f2- | tr -d '[:space:]"'"'")
  if [ -n "$v" ]; then echo "$k: 입력됨 (${#v}자)"; else echo "$k: 비어 있음"; fi
done
