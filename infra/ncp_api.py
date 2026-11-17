#!/usr/bin/env python3
"""CLI가 지원하지 않는 NCP API(요금 조회 등)를 서명(Signature v2)해서 호출하는 작은 도우미.
키는 ~/.ncloud/configure 에서 읽습니다.  예) python3 infra/ncp_api.py GET billingapi '/billing/v1/product/getProductPriceList?regionCode=KR&responseFormatType=json'
"""
import base64
import configparser
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request

HOSTS = {"billingapi": "https://billingapi.apigw.ntruss.com", "ncloud": "https://ncloud.apigw.ntruss.com"}


def call(method: str, host: str, uri: str) -> dict:
    cfg = configparser.ConfigParser()
    cfg.read(os.path.expanduser("~/.ncloud/configure"))
    ak = cfg["DEFAULT"]["ncloud_access_key_id"].strip()
    sk = cfg["DEFAULT"]["ncloud_secret_access_key"].strip()
    ts = str(int(time.time() * 1000))
    msg = f"{method} {uri}\n{ts}\n{ak}"
    sig = base64.b64encode(hmac.new(sk.encode(), msg.encode(), hashlib.sha256).digest()).decode()
    req = urllib.request.Request(HOSTS.get(host, host) + uri, method=method, headers={
        "x-ncp-apigw-timestamp": ts, "x-ncp-iam-access-key": ak, "x-ncp-apigw-signature-v2": sig})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:500]}


if __name__ == "__main__":
    print(json.dumps(call(sys.argv[1], sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=1))
