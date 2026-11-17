#!/bin/bash
# VoxPrism 인프라 생성 (자원 이름은 내부 코드명 whosaid-*) (ncloud CLI). 1차시에 만든 ai-vpc / ai-public-subnet 을 재사용합니다.
#   ./infra/create_infra.sh [내 공인IP]   — 결과는 infra/state.env 에 저장
# 이미 만든 자원은 state.env 를 보고 건너뜁니다.
set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ROOT="$(dirname "$HERE")"
N="$HERE/ncloud.sh"
STATE="$HERE/state.env"
touch "$STATE"; . "$STATE"
save() { grep -v "^$1=" "$STATE" > "$STATE.tmp" || true; echo "$1=$2" >> "$STATE.tmp"; mv "$STATE.tmp" "$STATE"; export "$1=$2"; }
js() { python3 -c "import sys,json; raw=sys.stdin.read(); d=json.loads(raw[raw.find('{'):]); print(eval(sys.argv[1]))" "$1"; }

MYIP="${1:-$(curl -s https://api.ipify.org)}"
VPC_NO="${VPC_NO:-151814}"            # ai-vpc
SUBNET_NO="${SUBNET_NO:-332954}"      # ai-public-subnet (KR-2, Public)
IMAGE_NO="${IMAGE_NO:-23214590}"      # ubuntu-22.04-base (KVM)
SPEC="${SPEC:-c8-g3}"                 # vCPU 8 / 16GB, 시간 요금제
LOGIN_KEY="${LOGIN_KEY:-ncpai20261030}"
NAME="${NAME:-whosaid-001}"
save VPC_NO "$VPC_NO"; save SUBNET_NO "$SUBNET_NO"; save MYIP "$MYIP"

# 1) SSH 키 (Init Script로 서버에 넣어 비밀번호 없이 접속)
KEY="$ROOT/secrets/whosaid_ed25519"
[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "whosaid-deploy" -f "$KEY"
PUB="$(cat "$KEY.pub")"

# 2) ACG: SSH는 내 IP만, 웹(80)은 전체 공개(앱에서 로그인), ping 허용, 나가는 통신 전체 허용
if [ -z "${ACG_NO:-}" ]; then
  ACG_NO=$($N vserver createAccessControlGroup --regionCode KR --vpcNo "$VPC_NO" --accessControlGroupName whosaid-acg \
    --accessControlGroupDescription "VoxPrism: ssh(my ip) + http" --output json | js "d['createAccessControlGroupResponse']['accessControlGroupList'][0]['accessControlGroupNo']")
  save ACG_NO "$ACG_NO"
  sleep 3
  add_in() { $N vserver addAccessControlGroupInboundRule --regionCode KR --vpcNo "$VPC_NO" --accessControlGroupNo "$ACG_NO" \
    --accessControlGroupRuleList "$1" --output json | js "d['addAccessControlGroupInboundRuleResponse']['returnMessage']"; sleep 2; }
  add_out() { $N vserver addAccessControlGroupOutboundRule --regionCode KR --vpcNo "$VPC_NO" --accessControlGroupNo "$ACG_NO" \
    --accessControlGroupRuleList "$1" --output json | js "d['addAccessControlGroupOutboundRuleResponse']['returnMessage']"; sleep 2; }
  add_in "protocolTypeCode='TCP', ipBlock='$MYIP/32', portRange='22', accessControlGroupRuleDescription='ssh-my-ip'"
  add_in "protocolTypeCode='TCP', ipBlock='0.0.0.0/0', portRange='80', accessControlGroupRuleDescription='web'"
  add_in "protocolTypeCode='ICMP', ipBlock='0.0.0.0/0', accessControlGroupRuleDescription='ping'"
  add_out "protocolTypeCode='TCP', ipBlock='0.0.0.0/0', portRange='1-65535', accessControlGroupRuleDescription='all-tcp'"
  add_out "protocolTypeCode='UDP', ipBlock='0.0.0.0/0', portRange='1-65535', accessControlGroupRuleDescription='all-udp'"
  add_out "protocolTypeCode='ICMP', ipBlock='0.0.0.0/0', accessControlGroupRuleDescription='ping'"
fi
echo "ACG_NO=$ACG_NO"

# 3) Init Script: 배포용 SSH 공개키 등록
if [ -z "${INIT_NO:-}" ]; then
  SCRIPT=$(printf '#!/bin/bash\nmkdir -p /root/.ssh && chmod 700 /root/.ssh\necho "%s" >> /root/.ssh/authorized_keys\nchmod 600 /root/.ssh/authorized_keys\ntouch /root/.whosaid-init-done\n' "$PUB")
  INIT_NO=$($N vserver createInitScript --regionCode KR --initScriptName whosaid-init --osTypeCode LNX \
    --initScriptContent "$SCRIPT" --initScriptDescription "VoxPrism deploy key" --output json \
    | js "d['createInitScriptResponse']['initScriptList'][0]['initScriptNo']")
  save INIT_NO "$INIT_NO"
fi
echo "INIT_NO=$INIT_NO"

# 4) 서버 생성 (공인 IP 자동 할당, 기본 스토리지 100GB SSD)
if [ -z "${SERVER_NO:-}" ]; then
  SERVER_NO=$($N vserver createServerInstances --regionCode KR --vpcNo "$VPC_NO" --subnetNo "$SUBNET_NO" \
    --serverImageNo "$IMAGE_NO" --serverSpecCode "$SPEC" \
    --networkInterfaceList "networkInterfaceOrder='0', accessControlGroupNoList=['$ACG_NO']" \
    --blockStorageMappingList "order='0', blockStorageSize='100', blockStorageVolumeTypeCode='CB1'" \
    --serverName "$NAME" --serverDescription "VoxPrism caption service" --loginKeyName "$LOGIN_KEY" \
    --initScriptNo "$INIT_NO" --associateWithPublicIp true --feeSystemTypeCode MTRAT --output json \
    | js "d['createServerInstancesResponse']['serverInstanceList'][0]['serverInstanceNo']")
  save SERVER_NO "$SERVER_NO"
fi
echo "SERVER_NO=$SERVER_NO"

# 5) 운영중(RUN)까지 대기 → 공인 IP 기록
for i in $(seq 1 60); do
  OUT=$($N vserver getServerInstanceDetail --regionCode KR --serverInstanceNo "$SERVER_NO" --output json)
  ST=$(echo "$OUT" | js "d['getServerInstanceDetailResponse']['serverInstanceList'][0]['serverInstanceStatus']['code']")
  IP=$(echo "$OUT" | js "d['getServerInstanceDetailResponse']['serverInstanceList'][0].get('publicIp') or ''")
  echo "$(date +%H:%M:%S) 상태=$ST 공인IP=${IP:-없음}"
  if [ "$ST" = "RUN" ] && [ -n "$IP" ]; then save PUBLIC_IP "$IP"; break; fi
  sleep 20
done
echo "완료: $(cat "$STATE" | tr '\n' ' ')"
