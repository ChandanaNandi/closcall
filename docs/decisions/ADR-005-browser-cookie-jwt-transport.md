# ADR-005 — Browser UI carries the JWT in an httpOnly cookie (Gate 14)

Status: accepted
Date: 2026-07-05 (Gate 14)

## Context
The Gate 11 auth core issues a short-lived JWT. The pure contract (Contracts §API) describes a Bearer
token. The Gate 14 browser approval UI needs the token somewhere the browser attaches automatically
on navigation and HTMX requests.

## Decision
The browser UI carries the **existing** JWT in an httpOnly + Secure + SameSite=Strict cookie; the
existing CSRF double-submit protects state-changing requests. This is **transport-only** — the same
token, the same claims, the same `verify_token`, the same roles as the Bearer path. The Bearer path
(`Authorization: Bearer …`) is retained unchanged for programmatic/API clients.

Rationale: for a browser session this is more secure than a Bearer token in JS-reachable storage —
httpOnly keeps it out of reach of XSS, SameSite=Strict + CSRF cover cross-site forgery. It is the
standard pattern for exactly this case. Not scope creep: no new auth, no new roles, no new token.

## Consequences
- Secure cookies require HTTPS; the UI is served on loopback HTTPS with the lab PKI (I02a — a Secure
  cookie is never issued over plain HTTP).
- No change to token minting/verification or the acceptance matrix's auth rows (I02/I02a hold).
