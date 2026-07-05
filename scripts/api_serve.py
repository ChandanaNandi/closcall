"""Serve the Gate 14 HITL UI on loopback HTTPS with the lab PKI (I02a).

Binds 127.0.0.1 only, over TLS (a Secure cookie never goes over plain HTTP). Mints a UI server
cert signed by the lab CA (SAN localhost + 127.0.0.1) if missing. Wires the DB-backed adapters and
the real FabricDevice, so approvals drive the SAME executor the slice uses. Run: make api-up.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

PKI = REPO / "lab" / "pki"
CA_CRT, CA_KEY = PKI / "ca" / "ca.crt", PKI / "ca" / "ca.key"
UI_DIR = PKI / "ui"
UI_CRT, UI_KEY = UI_DIR / "ui.crt", UI_DIR / "ui.key"
HOST, PORT = "127.0.0.1", 8443


def ensure_ui_cert() -> None:
    if UI_CRT.exists() and UI_KEY.exists():
        return
    if not CA_CRT.exists() or not CA_KEY.exists():
        sys.exit("lab CA missing — run `make pki` first")
    UI_DIR.mkdir(parents=True, exist_ok=True)
    csr = UI_DIR / "ui.csr"
    san = "subjectAltName=DNS:localhost,IP:127.0.0.1"
    subprocess.run(
        [
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(UI_KEY),
            "-out",
            str(csr),
            "-subj",
            "/CN=closcall-ui",
            "-addext",
            san,
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(CA_CRT),
            "-CAkey",
            str(CA_KEY),
            "-CAcreateserial",
            "-out",
            str(UI_CRT),
            "-days",
            "365",
            "-copy_extensions",
            "copyall",
        ],
        check=True,
        capture_output=True,
    )
    UI_KEY.chmod(0o600)
    csr.unlink(missing_ok=True)
    print(f"minted UI server cert (SAN localhost,127.0.0.1) under {UI_DIR.relative_to(REPO)}")


def build_app():  # type: ignore[no-untyped-def]
    from closcall.api.adapters import DbUIRepo, DbUserStore
    from closcall.api.app import create_app

    class _NullRepo:  # UI uses ui_repo; the legacy JSON /incidents route is not part of Gate 14
        def get_incident(self, incident_id: str):  # type: ignore[no-untyped-def]
            return None

    secret = os.environ.get("CLOSCALL_JWT_SECRET", "closcall-dev-jwt-secret-change-me")
    return create_app(secret=secret, users=DbUserStore(), repo=_NullRepo(), ui_repo=DbUIRepo())


def main() -> int:
    ensure_ui_cert()
    import uvicorn

    print(f"ClosCall HITL UI → https://{HOST}:{PORT}/ui/login  (loopback HTTPS, lab PKI)")
    print("D1: this demo executor runs synchronously in-process; production would use the durable")
    print("    job queue (backlogged). H07: live path enforces the narrower precheck subset.")
    uvicorn.run(
        build_app(), host=HOST, port=PORT, ssl_certfile=str(UI_CRT), ssl_keyfile=str(UI_KEY)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
