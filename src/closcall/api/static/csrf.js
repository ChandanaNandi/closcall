// Attach the CSRF double-submit token to every HTMX state-changing request.
// The token lives in the non-httpOnly `closcall_csrf` cookie (set at login); we echo it in the
// X-CSRF-Token header, which the server constant-time compares against the cookie (Gate 11).
(function () {
  function csrfCookie() {
    const m = document.cookie.match(/(?:^|;\s*)closcall_csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  document.body.addEventListener("htmx:configRequest", function (e) {
    e.detail.headers["X-CSRF-Token"] = csrfCookie();
  });
})();
