---
spec: SPEC-005
updated: 2026-11-18
---

# SPEC-005 작업

- [x] T-01 서명 쿠키 세션과 로그인·로그아웃 (FR-AUTH-01, FR-AUTH-05)
  - 파일: app/whosaid/web/main.py, web/static/login.html
  - 확인: tests/test_web.py::test_login_required
- [x] T-02 로그인 미들웨어와 공개 경로 (FR-AUTH-02, FR-AUTH-06)
  - 파일: app/whosaid/web/main.py (require_login)
- [x] T-03 nginx auth_request와 미디어 화이트리스트 (FR-AUTH-03, NFR-SEC-03)
  - 파일: app/deploy/nginx-whosaid.conf, web/main.py (auth_check, MEDIA_RE)
- [x] T-04 Basic 인증 허용 (FR-AUTH-04)
  - 파일: app/whosaid/web/main.py (_basic_ok)
- [x] T-05 SSH는 관리자 IP만 (NFR-SEC-02)
  - 파일: infra/create_infra.sh (ACG)
