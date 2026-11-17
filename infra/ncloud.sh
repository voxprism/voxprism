#!/bin/bash
# ncloud CLI 래퍼: 어느 폴더에서 실행해도 동작하도록 CLI 폴더로 이동해 실행합니다.
# 사용 예) ./infra/ncloud.sh vserver getServerInstanceList --output json
CLI_DIR="$(cd "$(dirname "$(readlink -f "$0")")/../tools/ncloud-cli" && pwd)"
cd "$CLI_DIR" || exit 1
exec ./jre8/bin/java -jar ./lib/ncloud-api-cli-1.1.30-SNAPSHOT-jar-with-dependencies.jar "$@"
