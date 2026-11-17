#!/bin/bash
# 서버 상태 확인·정지·시작 (비용 관리용).  ./infra/server.sh status|stop|start|ssh
#   정지하면 서버 요금이 줄어듭니다(스토리지·공인 IP 요금은 계속 발생).
set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ROOT="$(dirname "$HERE")"
. "$HERE/state.env"
N="$HERE/ncloud.sh"
status() {
  $N vserver getServerInstanceDetail --regionCode KR --serverInstanceNo "$SERVER_NO" --output json | python3 -c "
import sys, json
raw = sys.stdin.read(); d = json.loads(raw[raw.find('{'):])['getServerInstanceDetailResponse']['serverInstanceList'][0]
print(d['serverName'], d['serverInstanceStatus']['code'], d.get('serverInstanceOperation', {}).get('code'), d.get('publicIp'), d.get('serverSpecCode'))"
}
case "${1:-status}" in
  status) status ;;
  stop)   $N vserver stopServerInstances --regionCode KR --serverInstanceNoList "$SERVER_NO" --output json >/dev/null && echo "정지 요청됨"; status ;;
  start)  $N vserver startServerInstances --regionCode KR --serverInstanceNoList "$SERVER_NO" --output json >/dev/null && echo "시작 요청됨 (1~2분 뒤 접속 가능)"; status ;;
  ssh)    exec ssh -i "$ROOT/secrets/whosaid_ed25519" -o UserKnownHostsFile="$ROOT/secrets/known_hosts" "root@$PUBLIC_IP" ;;
  *) echo "사용법: $0 status|stop|start|ssh"; exit 1 ;;
esac
