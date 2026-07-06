"""Server-rendered SVG charts for the dashboard (dataviz mark specs, validated dark palette).

Deterministic: geometry computed here, colors referenced as CSS variables so the token set lives in
one place (base.html). Marks follow the spec — bars <=24px with a 4px rounded data-end and square
baseline, 2px surface gaps between adjacent bars, hairline solid gridlines, >=8px markers with a 2px
surface ring, sparse direct labels (the gray classes are the story; the tooltip carries the rest).
"""

from __future__ import annotations

from closcall.api.dashboard import CLASS_ORDER, DISPLAY, GRAY, ClassResult

# series -> CSS variable (defined in base.html; palette validated with the dataviz six checks)
SERIES = (
    ("RULE", "var(--s-rule)"),
    ("MLP", "var(--s-mlp)"),
    ("GNN", "var(--s-gnn)"),
)


def _bar(x: float, y: float, w: float, h: float, fill: str, r: float = 4.0) -> str:
    """Column with a 4px rounded data-end (top), square at the baseline."""
    r = min(r, h, w / 2)
    if h <= 0:
        return ""
    return (
        f'<path d="M{x:.1f},{y + r:.1f} a{r},{r} 0 0 1 {r},{-r} h{w - 2 * r:.1f} '
        f'a{r},{r} 0 0 1 {r},{r} v{h - r:.1f} h{-w:.1f} z" fill="{fill}"/>'
    )


def grouped_auroc_svg(
    rule: dict[str, ClassResult],
    mlp: dict[str, ClassResult],
    gnn: dict[str, ClassResult],
) -> str:
    """Grouped columns: AUROC per fault class x (RULE, MLP, GNN), with 95% CI whiskers."""
    W, H = 960.0, 320.0
    ml, mr, mt, mb = 40.0, 74.0, 16.0, 44.0
    pw, ph = W - ml - mr, H - mt - mb
    y0 = mt + ph  # baseline

    def sy(v: float) -> float:  # value -> y
        return mt + ph * (1.0 - v)

    bw, gap = 20.0, 2.0
    band = pw / len(CLASS_ORDER)
    group_w = 3 * bw + 2 * gap

    parts: list[str] = [
        f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
        f'aria-label="Localization AUROC per fault class: rule vs MLP vs GNN, with 95% CIs" '
        f'style="width:100%;height:auto;display:block;font:11px system-ui,sans-serif;">'
    ]
    # gridlines + y ticks (hairline, solid, recessive)
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(v)
        parts.append(
            f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + pw}" y2="{y:.1f}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ml - 8}" y="{y + 3.5:.1f}" text-anchor="end" fill="var(--ink-muted)">'
            f"{v:.2f}</text>"
        )
    # chance reference (0.5) — annotated, muted
    parts.append(
        f'<text x="{ml + pw + 8}" y="{sy(0.5) + 3.5:.1f}" fill="var(--ink-muted)">chance</text>'
    )

    models = (("RULE", rule), ("MLP", mlp), ("GNN", gnn))
    for gi, cls in enumerate(CLASS_ORDER):
        gx = ml + gi * band + (band - group_w) / 2
        for si, ((sname, svar), (_, data)) in enumerate(zip(SERIES, models, strict=True)):
            r = data.get(cls)
            if r is None:
                continue
            x = gx + si * (bw + gap)
            y = sy(r.auroc)
            parts.append(_bar(x, y, bw, y0 - y, svar))
            # 95% CI whisker (secondary ink, thin, capped)
            cx = x + bw / 2
            ylo, yhi = sy(r.lo), sy(r.hi)
            if r.hi > r.lo:
                parts.append(
                    f'<g stroke="var(--ink-secondary)" stroke-width="1.5">'
                    f'<line x1="{cx:.1f}" y1="{yhi:.1f}" x2="{cx:.1f}" y2="{ylo:.1f}"/>'
                    f'<line x1="{cx - 3:.1f}" y1="{yhi:.1f}" x2="{cx + 3:.1f}" y2="{yhi:.1f}"/>'
                    f'<line x1="{cx - 3:.1f}" y1="{ylo:.1f}" x2="{cx + 3:.1f}" y2="{ylo:.1f}"/></g>'
                )
            # sparse direct labels: the gray classes are the story
            if cls in GRAY:
                parts.append(
                    f'<text x="{cx:.1f}" y="{min(y, yhi) - 5:.1f}" text-anchor="middle" '
                    f'fill="var(--ink-secondary)">{r.auroc:.2f}</text>'
                )
            # hover hit target (full column band) + tooltip data
            parts.append(
                f'<rect class="hit" x="{x - 2:.1f}" y="{mt}" width="{bw + 4:.1f}" height="{ph}" '
                f'fill="transparent" data-tip="{DISPLAY[cls]} · {sname} · AUROC {r.auroc:.3f} '
                f'[{r.lo:.3f},{r.hi:.3f}] · top-1 {r.top1:.2f} · n={r.n}"/>'
            )
        # class label (two-word, muted)
        parts.append(
            f'<text x="{ml + gi * band + band / 2:.1f}" y="{y0 + 18:.1f}" text-anchor="middle" '
            f'fill="var(--ink-secondary)">{DISPLAY[cls]}</text>'
        )
    # baseline
    parts.append(
        f'<line x1="{ml}" y1="{y0:.1f}" x2="{ml + pw}" y2="{y0:.1f}" '
        f'stroke="var(--axis)" stroke-width="1"/>'
    )
    parts.append("</svg>")
    return "".join(parts)


def gray_recovery_svg(
    rule: dict[str, ClassResult],
    mlp_v1: dict[str, float],
    mlp_v2: dict[str, ClassResult],
) -> str:
    """Dumbbell per gray class: rule (chance) -> +aggregate features (v1) -> +temporal (v2)."""
    W, H = 960.0, 170.0
    ml, mr = 130.0, 40.0
    pw = W - ml - mr
    lo_dom, hi_dom = 0.40, 1.0

    def sx(v: float) -> float:
        return ml + pw * (v - lo_dom) / (hi_dom - lo_dom)

    rows = [(c, 52.0 + 62.0 * i) for i, c in enumerate(GRAY)]
    parts = [
        f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
        f'aria-label="Gray-fault localization recovery: rule to aggregate to temporal features" '
        f'style="width:100%;height:auto;display:block;font:11px system-ui,sans-serif;">'
    ]
    for v in (0.4, 0.6, 0.8, 1.0):
        x = sx(v)
        parts.append(
            f'<line x1="{x:.1f}" y1="26" x2="{x:.1f}" y2="140" stroke="var(--grid)" '
            f'stroke-width="1"/>'
            f'<text x="{x:.1f}" y="156" text-anchor="middle" fill="var(--ink-muted)">{v:.1f}</text>'
        )
    for cls, y in rows:
        a = rule[cls].auroc
        b = mlp_v1.get(cls)
        c = mlp_v2[cls].auroc
        parts.append(
            f'<text x="{ml - 14}" y="{y + 4:.1f}" text-anchor="end" '
            f'fill="var(--ink-secondary)">{DISPLAY[cls]}</text>'
        )
        parts.append(
            f'<line x1="{sx(a):.1f}" y1="{y}" x2="{sx(c):.1f}" y2="{y}" '
            f'stroke="var(--s-mlp)" stroke-width="2" stroke-linecap="round" opacity="0.55"/>'
        )
        # markers >=8px with a 2px surface ring; one hue two shades for before -> after
        dots = [(a, "var(--s-rule)", f"rule {a:.3f}")]
        if b is not None:
            dots.append((b, "var(--s-mlp-lt)", f"+aggregate (v1) {b:.3f}"))
        dots.append((c, "var(--s-mlp)", f"+temporal (v2) {c:.3f}"))
        for v, fill, tip in dots:
            parts.append(
                f'<circle cx="{sx(v):.1f}" cy="{y}" r="6" fill="{fill}" '
                f'stroke="var(--surface)" stroke-width="2"/>'
                f'<circle class="hit" cx="{sx(v):.1f}" cy="{y}" r="12" fill="transparent" '
                f'data-tip="{DISPLAY[cls]} · {tip} AUROC"/>'
            )
        parts.append(
            f'<text x="{sx(a) - 10:.1f}" y="{y + 4:.1f}" text-anchor="end" '
            f'fill="var(--ink-muted)">{a:.2f}</text>'
            f'<text x="{sx(c) + 12:.1f}" y="{y + 4:.1f}" fill="var(--ink-primary)" '
            f'font-weight="600">{c:.2f}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["gray_recovery_svg", "grouped_auroc_svg"]
