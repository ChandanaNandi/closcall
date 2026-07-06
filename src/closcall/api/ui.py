"""Gate 14 browser UI router — a face on the EXISTING gated approval flow (Bible §13).

Three server-rendered views (Jinja2 + HTMX, no SPA): incident list -> case file -> approve/reject.
Wired to the existing auth (httpOnly JWT cookie per ADR-005, roles, CSRF double-submit, IDOR) and to
the existing executor via `UIRepo.approve_and_execute` — never a new mutation path. The H07 banner
renders sticky, in the same viewport as the approve button, on every case file (honest labeling).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from closcall.api.approval import SideDoorRejected
from closcall.api.auth import Principal
from closcall.api.charts import gray_recovery_svg, grouped_auroc_svg
from closcall.api.dashboard import DISPLAY, load_dashboard
from closcall.api.gates import GATES, PHASES
from closcall.api.ui_repo import CaseFile, UIRepo

_HERE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))

# The one honest label, rendered adjacent to every approve button (H07 / ADR-004).
H07_NOTICE = (
    "This executor enforces approval-binding, allowlist, and management-interface checks. "
    "The full fail-closed suite (last-path, capacity headroom, stale-telemetry, drift) is NOT "
    "wired to this live path — see LIMITATIONS / ADR-004."
)


def mount_ui(app: FastAPI, *, ui_repo: UIRepo, principal_dep, require, csrf) -> None:  # type: ignore[no-untyped-def]
    """Attach the UI routes + static assets to an app built by create_app, reusing its auth deps."""
    app.mount("/ui/static", StaticFiles(directory=str(_HERE / "static")), name="ui-static")

    @app.exception_handler(StarletteHTTPException)
    async def _ui_auth_redirect(request: Request, exc: StarletteHTTPException) -> Response:
        """A browser navigating a /ui page with no/expired session gets the login page, not raw
        JSON. API clients (and non-HTML requests) keep the 401 JSON contract unchanged."""
        if (
            exc.status_code == status.HTTP_401_UNAUTHORIZED
            and request.url.path.startswith("/ui")
            and "text/html" in request.headers.get("accept", "")
        ):
            return RedirectResponse(url="/ui/login", status_code=status.HTTP_303_SEE_OTHER)
        return await http_exception_handler(request, exc)

    require_reader = require("viewer", "operator", "approver")
    require_approver = require("approver")

    def _authz(incident_id: str, user_id: str) -> None:
        # IDOR: hide existence if not authorized (role-scoped in the single-tenant lab).
        if not ui_repo.is_authorized(incident_id, user_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    @app.get("/ui/login", response_class=HTMLResponse)
    def ui_login(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "login.html", {})

    @app.get("/ui", include_in_schema=False)
    def ui_root() -> RedirectResponse:
        return RedirectResponse(url="/ui/", status_code=status.HTTP_302_FOUND)

    @app.get("/ui/", response_class=HTMLResponse)
    async def ui_dashboard(
        request: Request, p: Principal = Depends(require_reader)
    ) -> HTMLResponse:
        """Front door: the study's results, parsed live from the immutable artifacts (J07)."""
        d = load_dashboard()
        return TEMPLATES.TemplateResponse(
            request,
            "dashboard.html",
            {
                "d": d,
                "me": p,
                "display": DISPLAY,
                "auroc_svg": grouped_auroc_svg(d.rule, d.mlp, d.gnn),
                "recovery_svg": gray_recovery_svg(d.rule, d.mlp_v1_gray, d.mlp),
            },
        )

    @app.get("/ui/journey", response_class=HTMLResponse)
    async def ui_journey(request: Request, p: Principal = Depends(require_reader)) -> HTMLResponse:
        """The build journey: the pipeline + every gate with its evidence pointers."""
        return TEMPLATES.TemplateResponse(
            request, "gates.html", {"gates": GATES, "phases": PHASES, "me": p}
        )

    @app.get("/ui/incidents", response_class=HTMLResponse)
    async def ui_incidents(
        request: Request, p: Principal = Depends(require_reader)
    ) -> HTMLResponse:
        incidents = await ui_repo.list_incidents(p.user_id)
        return TEMPLATES.TemplateResponse(
            request, "incidents.html", {"incidents": incidents, "me": p}
        )

    @app.get("/ui/incidents/{incident_id}", response_class=HTMLResponse)
    async def ui_case_file(
        request: Request, incident_id: str, p: Principal = Depends(require_reader)
    ) -> HTMLResponse:
        _authz(incident_id, p.user_id)
        case = await ui_repo.get_case_file(incident_id)
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        return TEMPLATES.TemplateResponse(
            request,
            "case_file.html",
            {"case": case, "me": p, "h07_notice": H07_NOTICE},
        )

    def _panel(
        request: Request, case: CaseFile | None, p: Principal, msg: str = ""
    ) -> HTMLResponse:
        # Full case-file partial: approve/edit/reject swap EVERYTHING dynamic (plan JSON, audit
        # trail included), so no section goes stale after an action.
        return TEMPLATES.TemplateResponse(
            request,
            "_casefile.html",
            {"case": case, "me": p, "h07_notice": H07_NOTICE, "flash": msg},
        )

    @app.post("/ui/incidents/{incident_id}/approve", response_class=HTMLResponse)
    async def ui_approve(
        request: Request,
        incident_id: str,
        p: Principal = Depends(require_approver),
        _csrf: None = Depends(csrf),
    ) -> HTMLResponse:
        _authz(incident_id, p.user_id)
        try:
            outcome = await ui_repo.approve_and_execute(incident_id, p.user_id)
        except SideDoorRejected as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
        case = await ui_repo.get_case_file(incident_id)
        return _panel(request, case, p, f"approved → executor: {outcome}")

    @app.post("/ui/incidents/{incident_id}/reject", response_class=HTMLResponse)
    async def ui_reject(
        request: Request,
        incident_id: str,
        p: Principal = Depends(require_approver),
        _csrf: None = Depends(csrf),
    ) -> HTMLResponse:
        _authz(incident_id, p.user_id)
        await ui_repo.reject(incident_id, p.user_id)
        case = await ui_repo.get_case_file(incident_id)
        return _panel(request, case, p, "rejected — no execution")

    @app.post("/ui/incidents/{incident_id}/edit", response_class=HTMLResponse)
    async def ui_edit(
        request: Request,
        incident_id: str,
        p: Principal = Depends(require_approver),
        _csrf: None = Depends(csrf),
    ) -> HTMLResponse:
        _authz(incident_id, p.user_id)
        new_digest = await ui_repo.edit_plan(incident_id, p.user_id)
        case = await ui_repo.get_case_file(incident_id)
        return _panel(
            request, case, p, f"edited → new plan digest {new_digest[:12]} needs approval"
        )


__all__ = ["H07_NOTICE", "mount_ui"]
