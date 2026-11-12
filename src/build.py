#!/usr/bin/env python3
"""Static site builder for propfirmnerd.com.

Sources
  src/data/firms/<slug>.json   one file per firm: facts + sources + facets (see FIRM FIELDS)
  src/editorial/<slug>.html    optional per-firm writing: META header + review body HTML
  src/data/lists.json          "best X" lists (filters over facets)
  src/data/compares.json       head-to-head pages
  src/data/contracts.json      futures contract specs (tick value tool)
  src/pages/<slug>.html        hand-written pages (guides, tools, about...) with a META header;
                               a slug may contain "__" for nesting: tools__mnq-tick-value -> /tools/mnq-tick-value/

Run:  python3 src/build.py      -> writes public/ (plus sitemap.xml, robots.txt, _redirects)

FIRM FIELDS used here (beyond the research schema)
  checked     YYYY-MM-DD the facts were last verified
  link        official URL that /go/<slug>/ redirects to (swap for an affiliate link later)
  facets      normalized values for filters:
              market futures|forex|multi, price50 number (cheapest main 50K program, USD),
              target50, maxloss50, dd eod|intraday|static|mixed, consistency_eval bool,
              consistency_funded bool, split text, payouts text, instant bool, news allowed|restricted,
              ea bool|null, copy bool|null, us bool, tp number|null (Trustpilot), ccy USD|EUR
"""
import json, re, shutil, html, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
STATIC = ROOT / "static"
OUT = ROOT / "public"
SITE = "https://propfirmnerd.com"
NAME = "PropFirmNerd"
TODAY = datetime.date.today().isoformat()
GA_ID = "G-MVG0D1N0KZ"

NAV = [("firms", "Firm reviews"), ("compare", "Compare"), ("best", "Best of"),
       ("promo-codes", "Promo codes"), ("tools", "Tools"), ("guides", "Guides")]
SECTION_TITLES = {"firms": "Firm reviews", "compare": "Compare", "best": "Best prop firms",
                  "promo-codes": "Promo codes", "tools": "Tools", "guides": "Guides"}
MARKET_LABEL = {"futures": "Futures", "forex": "Forex & CFDs", "multi": "Futures & forex"}
DD_LABEL = {"eod": "End-of-day trailing", "intraday": "Intraday trailing", "static": "Static", "closed": "Trailing on closed balance",
            "mixed": "Depends on plan", None: "—"}

esc = html.escape


# ---------------------------------------------------------------- helpers
def fmt_date(d):
    return datetime.date.fromisoformat(d).strftime("%B %-d, %Y")


def month_year(d):
    return datetime.date.fromisoformat(d).strftime("%B %Y")


def money(v, ccy="USD", dec=False):
    if v is None or v == "":
        return "—"
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(ccy, "")
    if isinstance(v, str):
        return esc(v)
    if dec or (v != int(v)):
        return f"{sym}{v:,.2f}"
    return f"{sym}{int(v):,}"


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "")


def read_meta_file(path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"\s*<!--META(.*?)META-->", raw, re.S)
    if not m:
        raise SystemExit(f"{path.name}: missing META header")
    try:
        meta = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path.name}: bad META JSON: {e}")
    return meta, raw[m.end():].strip()


def fit_title(*cands, limit=60):
    """First candidate that fits in a search result title; the last one is the fallback."""
    for c in cands:
        if len(c) <= limit:
            return c
    return cands[-1]


def avatar(f, lg=False):
    """Firm mark next to its name: the firm's own site icon from static/assets/logos/<slug>.webp,
    or an initials tile (coloured by market) when there is no file for that firm yet."""
    size = 60 if lg else 34
    if (STATIC / "assets" / "logos" / f"{f['slug']}.webp").exists():
        return (f'<img class="av{" lg" if lg else ""}" src="/assets/logos/{f["slug"]}.webp" alt="" width="{size}" height="{size}"'
                f'{"" if lg else " loading=\"lazy\""} decoding="async">')
    words = re.findall(r"[A-Za-z0-9]+", f["name"])
    ini = (words[0][0] + (words[1][0] if len(words) > 1 else words[0][1:2])).upper()
    m = (f.get("facets") or {}).get("market") or ""
    return f'<span class="av {m}{" lg" if lg else ""}" aria-hidden="true">{esc(ini)}</span>'


def go_link(f, label=None, cls="btn", place=""):
    return (f'<a class="{cls}" href="/go/{f["slug"]}/" rel="nofollow sponsored"{" data-place=" + place if place else ""}>'
            f'{esc(label or "Visit " + f["name"])}</a>')


DISCLOSE = 'Some links earn us a commission. <a href="/affiliate-disclosure/">Disclosure</a>'


def domain(url):
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]


# ---------------------------------------------------------------- data
def load_firms():
    firms = {}
    for f in sorted((SRC / "data" / "firms").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("hidden"):
            continue
        ed = SRC / "editorial" / f"{f.stem}.html"
        d["_ed_meta"], d["_ed_body"] = read_meta_file(ed) if ed.exists() else ({}, "")
        firms[f.stem] = d
    return firms


def load_json(name, default):
    p = SRC / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


# ---------------------------------------------------------------- drawdown diagram
def dd_svg(kind):
    """Illustration of how a max-loss rule moves. Same equity path for every kind."""
    # intraday equity samples for 5 days (start balance 50,000 -> plotted in $ units)
    days = [[0, 600, 1300, 900, 1100], [1100, 1900, 2600, 2100, 2300], [2300, 2000, 1500, 1800, 1700],
            [1700, 2400, 3100, 2700, 2900], [2900, 2500, 1600, 1100, 1200]]
    pts = [v for d in days for v in d]
    n = len(pts)
    W, H, L, R, T, B = 340, 170, 8, 8, 14, 22
    lo, hi = -2400, 3400
    x = lambda i: L + i * (W - L - R) / (n - 1)
    y = lambda v: T + (hi - v) * (H - T - B) / (hi - lo)
    limit = 2000
    thr = []
    if kind == "static":
        thr = [-limit] * n
    elif kind == "intraday":
        peak = 0
        for v in pts:
            peak = max(peak, v)
            thr.append(peak - limit)
    else:  # eod (and mixed shown as eod)
        floor = -limit
        i = 0
        for d in days:
            for v in d:
                thr.append(floor)
                i += 1
            floor = max(floor, d[-1] - limit)
    eq = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(pts))
    if kind in ("eod", "mixed"):
        segs = []
        for i, v in enumerate(thr):
            if i == 0:
                segs.append(f"M{x(i):.1f},{y(v):.1f}")
            elif v != thr[i - 1]:
                segs.append(f"L{x(i):.1f},{y(thr[i-1]):.1f} L{x(i):.1f},{y(v):.1f}")
            else:
                segs.append(f"L{x(i):.1f},{y(v):.1f}")
        th = " ".join(segs)
    else:
        th = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(thr))
    grid = "".join(f'<line x1="{x(i*5):.1f}" x2="{x(i*5):.1f}" y1="{T}" y2="{H-B}" stroke="#C1CBDB" stroke-dasharray="2 3"/>'
                   for i in range(1, 5))
    labels = "".join(f'<text x="{(x(i*5)+x(min(i*5+4, n-1)))/2:.1f}" y="{H-6}" font-size="10.5" fill="#64728B" text-anchor="middle">Day {i+1}</text>'
                     for i in range(5))
    start = f'<line x1="{L}" x2="{W-R}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="#64728B" stroke-dasharray="1 3"/>'
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(DD_LABEL.get(kind, ""))} drawdown illustration">'
            f'{grid}{start}<path d="{th}" fill="none" stroke="#CE3329" stroke-width="2.4" stroke-linejoin="round"/>'
            f'<path d="{eq}" fill="none" stroke="#0B1B3A" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>{labels}</svg>')


def hero_svg():
    """Home page figure: one 50K evaluation drawn to scale. Reach the green line before touching the red one."""
    days = [[350, 150, 700, 600], [250, -150, 100, 300], [800, 1250, 1100, 1400], [1050, 700, 900, 1100],
            [1500, 1900, 1750, 2000], [1650, 1300, 1450, 1500], [1900, 2250, 2150, 2400], [2700, 2550, 3000]]
    target, limit = 3000, 2000
    pts = [0] + [v for d in days for v in d]
    n = len(pts) - 1
    W, H, L, R, T, B = 540, 372, 66, 528, 30, 322
    lo, hi = -2500, 3500
    x = lambda i: L + i * (R - L) / 32
    y = lambda v: T + (hi - v) * (B - T) / (hi - lo)
    # end-of-day trailing limit that stops at the starting balance
    floor, steps, i = -limit, [(0, -limit)], 0
    for d in days:
        i += len(d)
        nf = min(0, max(floor, d[-1] - limit))
        if nf != floor and i <= 28:
            steps += [(i, floor), (i, nf)]
            floor = nf
    steps.append((32, floor))
    lim = " ".join(f"{'M' if k == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for k, (i, v) in enumerate(steps))
    eq = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(pts))
    grid = "".join(f'<line x1="{x(d*4):.1f}" x2="{x(d*4):.1f}" y1="{T}" y2="{B}" stroke="#C1CBDB" stroke-dasharray="2 4"/>' for d in range(1, 8))
    dlab = "".join(f'<text x="{(x(d*4)+x(d*4+4))/2:.1f}" y="{B+20}" class="t-ax" font-size="12.5" fill="#64728B" text-anchor="middle">Day {d+1}</text>' for d in range(8))
    ylab = "".join(f'<text x="{L-10}" y="{y(v)+4.5:.1f}" class="t-ax" font-size="12.5" fill="{c}" text-anchor="end" font-weight="600">{t}</text>'
                   for v, t, c in [(target, "$53,000", "#0E8457"), (0, "$50,000", "#64728B"), (-limit, "$48,000", "#CE3329")])
    hx, hy = x(n), y(target)
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="A 50K evaluation over eight days: the balance climbs from $50,000 to the '
            f'$53,000 profit target while the max loss limit trails up from $48,000 to $50,000 at each higher daily close.">'
            f'<rect x="{L}" y="{T}" width="{R-L}" height="{y(target)-T:.1f}" fill="#0E8457" opacity=".1"/>'
            f'<path d="{lim} L{R},{B} L{L},{B} Z" fill="#CE3329" opacity=".1"/>'
            f'{grid}<line x1="{L}" x2="{R}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="#64728B" stroke-dasharray="1 4"/>'
            f'<line x1="{L}" x2="{R}" y1="{y(target):.1f}" y2="{y(target):.1f}" stroke="#0E8457" stroke-width="2.5"/>'
            f'<path d="{lim}" fill="none" stroke="#CE3329" stroke-width="2.5" stroke-linejoin="round"/>'
            f'<path class="eq" pathLength="1" d="{eq}" fill="none" stroke="#0B1B3A" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<text x="{L+10}" y="{y(target)-9:.1f}" class="t-lab" font-size="14" font-weight="700" fill="#0E8457">Profit target: reach it and you pass</text>'
            f'<text x="{L+10}" y="{y(-limit)+19:.1f}" class="t-lab" font-size="14" font-weight="700" fill="#CE3329">Max loss limit: touch it and the account closes</text>'
            f'<text x="{x(12)+8:.1f}" y="{y(-600)+18:.1f}" class="t-note" font-size="12.5" fill="#B02A21">It moves up when a day closes at a new high</text>'
            f'<g class="hit"><circle cx="{hx:.1f}" cy="{hy:.1f}" r="7" fill="#FFD23F" stroke="#0B1B3A" stroke-width="2.5"/></g>'
            f'{ylab}{dlab}</svg>')


DD_TEXT = {
    "eod": ("End-of-day trailing drawdown",
            "Your loss limit moves up only when a trading day closes at a new high balance. Open profits during the day do not drag it up, so a winning trade you give back intraday does not tighten the limit until the close."),
    "intraday": ("Intraday trailing drawdown",
                 "Your loss limit follows your highest balance in real time, including open profit. If a trade is up $800 and you let it come back, the limit has already moved up $800. This is the strictest common version."),
    "static": ("Static max loss",
               "Your loss limit sits at a fixed level below the starting balance and never moves. Profits widen your cushion instead of tightening it."),
    "mixed": ("Drawdown depends on the plan",
              "This firm sells plans with different drawdown types. The picture shows end-of-day trailing; check the plan table below for each plan's rule."),
}


def dd_block(kind):
    if kind not in DD_TEXT:
        return ""
    t, p = DD_TEXT[kind]
    return (f'<div class="dd">{dd_svg(kind)}<div><h3>{t}</h3><p>{p}</p>'
            f'<p class="key"><i style="background:#0B1B3A"></i>Account balance '
            f'<i style="background:#CE3329;margin-left:12px"></i>Loss limit<br>'
            f'Illustration with a $2,000 limit, not this firm\'s exact numbers.</p></div></div>')


# ---------------------------------------------------------------- page pieces
def nav_html(active):
    return "\n".join(f'<a href="/{s}/"{" aria-current=\"page\"" if s == active else ""}>{n}</a>' for s, n in NAV)


def crumbs_html(trail):
    parts = ['<a href="/">Home</a>']
    for name, href in trail[:-1]:
        parts.append(f'<a href="{href}">{esc(name)}</a>')
    parts.append(esc(trail[-1][0]))
    return '<div class="crumbs">' + " › ".join(parts) + "</div>"


def faq_html(faq):
    if not faq:
        return ""
    out = ['<section class="faq" id="faq"><h2>Questions traders ask</h2>']
    for q, a in faq:
        out.append(f"<details><summary>{esc(q)}</summary><div><p>{a}</p></div></details>")
    out.append("</section>")
    return "\n".join(out)


def rows_html(items):
    """items: [(href, title, blurb)]"""
    if not items:
        return '<p class="empty">Nothing here yet.</p>'
    return '<ul class="rows">' + "".join(
        f'<li><a href="{h}"><strong>{esc(t)}</strong><span>{esc(b)}</span></a></li>' for h, t, b in items) + "</ul>"


def related_html(items):
    if not items:
        return ""
    return '<section class="related"><h2>Keep reading</h2>' + rows_html(items) + "</section>"


def clean_supports(t):
    t = re.sub(r"\s*\((?:checked in (?:a )?browser|search snippet|seen [^)]*)\)", "", t, flags=re.I)
    t = re.sub(r";?\s*Serbia[^;,)]*", "", t)
    return t.strip(" ;,")


def sources_html(firm):
    srcs = firm.get("sources") or []
    if not srcs:
        return ""
    lis = "".join(f'<li><a href="{esc(s["url"])}" rel="nofollow noopener" target="_blank">{esc(domain(s["url"]) + "/" + s["url"].split("/", 3)[-1] if s["url"].count("/") > 2 else s["url"])}</a>'
                  f'{(" — " + esc(clean_supports(s.get("supports", "")))) if s.get("supports") else ""}</li>' for s in srcs)
    return (f'<section class="sources" id="sources"><h2>Sources</h2><p>Checked {fmt_date(firm["checked"])}. '
            f'We link the firm\'s own pages wherever we can. If something changed, '
            f'<a href="/contact/">tell us</a>.</p><details><summary>Show all {len(srcs)} sources</summary><ol>{lis}</ol></details></section>')


def schema_json(graph):
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


def article_schema(h1, desc, url, published, modified):
    return {"@type": "Article", "headline": h1, "description": desc, "url": url,
            "datePublished": published, "dateModified": modified,
            "author": {"@type": "Organization", "name": "PropFirmNerd editorial team", "url": SITE + "/about/"},
            "publisher": {"@type": "Organization", "name": NAME, "url": SITE + "/"}}


def crumb_schema(trail):
    items = [{"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"}]
    for i, (name, href) in enumerate(trail, start=2):
        items.append({"@type": "ListItem", "position": i, "name": name, "item": SITE + href})
    return {"@type": "BreadcrumbList", "itemListElement": items}


def faq_schema(faq):
    return {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": strip_tags(a)}} for q, a in faq]}


LOGO = ('<a class="logo" href="/" aria-label="PropFirmNerd home">'
        '<svg width="26" height="22" viewBox="0 0 26 22" aria-hidden="true">'
        '<path d="M1 15 L7 9 L11 12 L18 4 L25 7" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/>'
        '<path d="M1 20 L9 20 L9 17 L17 17 L17 13 L25 13" fill="none" stroke="#FF6B5E" stroke-width="2.4"/></svg>'
        '<span>PropFirm<b>Nerd</b></span></a>')

LAYOUT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{url}">{robots}
<meta property="og:type" content="{ogtype}">
<meta property="og:site_name" content="PropFirmNerd">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site}/assets/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0B1B3A">{ga}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Funnel+Display:wght@600..800&family=Funnel+Sans:ital,wght@0,400..800;1,400..800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css?v={ver}">
<script type="application/ld+json">{schema}</script>
</head>
<body>
<header class="site-head"><div class="wrap">
{logo}
<button class="menu-btn" aria-expanded="false" aria-controls="nav">Menu</button>
<nav class="nav" id="nav">
{nav}
</nav>
</div></header>
<main class="{mainclass}"><div class="wrap">
{crumbs}
{body}
</div></main>
<footer class="site-foot"><div class="wrap">
<div class="cols">
<div class="about">{logo}<p>Prop firm rules, prices and codes in one place, checked against each firm's own pages and dated so you know how fresh they are.</p></div>
<div><strong>Browse</strong><ul><li><a href="/firms/">Firm reviews</a></li><li><a href="/compare/">Compare all firms</a></li><li><a href="/best/">Best of lists</a></li><li><a href="/promo-codes/">Promo codes</a></li></ul></div>
<div><strong>Learn</strong><ul><li><a href="/tools/">Calculators</a></li><li><a href="/guides/">Guides</a></li><li><a href="/methodology/">How we check firms</a></li><li><a href="/risks/">Risks of prop trading</a></li></ul></div>
<div><strong>Site</strong><ul><li><a href="/about/">About</a></li><li><a href="/contact/">Contact</a></li><li><a href="/affiliate-disclosure/">Affiliate disclosure</a></li><li><a href="/privacy/">Privacy</a></li></ul></div>
</div>
<p class="disclaimer">PropFirmNerd is independent and is not owned by any prop firm. Some links earn us a commission, which never changes the facts we publish; see our <a href="/affiliate-disclosure/">disclosure</a>. Prop firm evaluations are paid products, most traders do not pass them, and the fee is not refunded when you fail. Funded accounts at most firms are simulated. Nothing here is financial advice. Rules and prices change often, so check the firm's site before you buy.</p>
</div></footer>
<script src="/assets/js/site.js?v={ver}" defer></script>{scripts}
</body>
</html>
"""


class Site:
    def __init__(self):
        self.pages = []   # (path, html, priority, lastmod, indexable)
        self.ver = TODAY.replace("-", "")

    def add(self, path, *, title, description, body, section=None, trail=None, graph=None,
            kind="page", scripts=(), priority="0.7", lastmod=None, noindex=False):
        url = SITE + path
        g = list(graph or [])
        if trail:
            g.append(crumb_schema(trail))
        ga = ""
        if GA_ID:
            ga = (f'\n<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>'
                  f"\n<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}"
                  f"gtag('js',new Date());gtag('config','{GA_ID}');</script>")
        page = LAYOUT.format(
            title=esc(title), description=esc(description), url=url, site=SITE, ga=ga,
            robots='\n<meta name="robots" content="noindex">' if noindex else "",
            ogtype="article" if kind == "article" else "website", ver=self.ver,
            schema=schema_json(g), logo=LOGO, nav=nav_html(section), mainclass=f"kind-{kind}",
            crumbs=crumbs_html(trail) if trail else "", body=body,
            scripts="".join(f'<script src="/assets/js/{s}?v={self.ver}" defer></script>' for s in scripts))
        self.pages.append((path, page, priority, lastmod or TODAY, not noindex))

    def write(self):
        for path, page, *_ in self.pages:
            dest = OUT / ("index.html" if path == "/" else ("404.html" if path == "/404/" else path.strip("/") + "/index.html"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(page, encoding="utf-8")
        sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for path, _, pr, lm, idx in sorted(self.pages, key=lambda p: (p[0] != "/", p[0])):
            if idx and path != "/404/":
                sm.append(f"  <url><loc>{SITE}{path}</loc><lastmod>{lm}</lastmod><priority>{pr}</priority></url>")
        sm.append("</urlset>")
        (OUT / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
        (OUT / "robots.txt").write_text(f"User-agent: *\nDisallow: /go/\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
        return sum(1 for p in self.pages if p[4] and p[0] != "/404/")


# ---------------------------------------------------------------- firm helpers
def fac(f, k, default=None):
    return (f.get("facets") or {}).get(k, default)


def main_program(f):
    progs = f.get("programs") or []
    return progs[0] if progs else {}


def yn(v, yes="Yes", no="No"):
    if v is None:
        return "—"
    return yes if v else no


def cons_label(f):
    e, fu = fac(f, "consistency_eval"), fac(f, "consistency_funded")
    if e is None and fu is None:
        return "—"
    if not e and not fu:
        return "None"
    if e and fu:
        return "Eval + funded"
    return "Funded only" if fu else "Eval only"


def code_cell(f):
    p = f.get("current_public_promo") or {}
    if p.get("code"):
        return (f'<button class="codebtn" type="button" data-copy="{esc(p["code"])}" '
                f'title="Copy code {esc(p["code"])}">{esc(p["code"])}</button>')
    return '<span class="muted">—</span>'


def num(v):
    return v if isinstance(v, (int, float)) else ""


def room_span(f):
    t, m = fac(f, "target50"), fac(f, "maxloss50")
    if not t or not m:
        return "—"
    ccy = fac(f, "acc_ccy", fac(f, "ccy", "USD"))
    label = f"Max loss {strip_tags(money(m, ccy))} against a {strip_tags(money(t, ccy))} target"
    return (f'<span class="rm" role="img" aria-label="{label}" title="{label}" '
            f'style="--l:{min(m / 50, 100):.0f}%;--g:{min(t / 50, 100):.0f}%"><i class="l"></i><i class="z"></i><i class="g"></i></span>')


def room_bar(f):
    """Loss room against target as a small two-sided bar. Scale: $5,000 fills a side."""
    t, m = fac(f, "target50"), fac(f, "maxloss50")
    if not t or not m:
        return '<td class="room" data-l="Loss vs target"><span class="muted">—</span></td>'
    return f'<td class="room" data-l="Loss vs target" data-v="{m / t:.3f}">{room_span(f)}</td>'


def firm_row(f, cols):
    s = f["slug"]
    ccy = fac(f, "ccy", "USD")
    market = "" if "market" in cols else f'<small>{esc(MARKET_LABEL.get(fac(f, "market"), ""))}</small>'
    L = lambda c: f' data-l="{esc(strip_tags(COLS[c]))}"'
    cells = {
        "firm": (f'<th scope="row" data-v="{esc(f["name"].lower())}"><a href="/firms/{s}/">{avatar(f)}'
                 f'<span class="fn"><span>{esc(f["name"])}</span>{market}</span></a></th>'),
        "market": f'<td{L("market")}>{esc(MARKET_LABEL.get(fac(f, "market"), "—"))}</td>',
        "price": f'<td class="n"{L("price")} data-v="{num(fac(f, "price50"))}">{money(fac(f, "price50"), ccy)}{"<small>/mo</small>" if fac(f, "monthly") else ""}</td>',
        "target": f'<td class="n gain"{L("target")} data-v="{num(fac(f, "target50"))}">{money(fac(f, "target50"), fac(f, "acc_ccy", ccy))}</td>',
        "maxloss": f'<td class="n loss"{L("maxloss")} data-v="{num(fac(f, "maxloss50"))}">{money(fac(f, "maxloss50"), fac(f, "acc_ccy", ccy))}</td>',
        "room": room_bar(f),
        "dd": f'<td{L("dd")}>{esc(DD_LABEL.get(fac(f, "dd"), "—"))}</td>',
        "cons": f'<td{L("cons")}>{esc(cons_label(f))}</td>',
        "split": f'<td{L("split")}>{esc(fac(f, "split") or "—")}</td>',
        "payouts": f'<td{L("payouts")}>{esc(fac(f, "payouts") or "—")}</td>',
        "news": f'<td{L("news")}>{esc((fac(f, "news") or "—").capitalize())}</td>',
        "ea": f'<td{L("ea")}>{esc(fac(f, "ea") if isinstance(fac(f, "ea"), str) else yn(fac(f, "ea"), "Allowed", "Not allowed"))}</td>',
        "us": f'<td{L("us")}>{yn(fac(f, "us"))}</td>',
        "tp": f'<td class="n"{L("tp")} data-v="{num(fac(f, "tp"))}">{fac(f, "tp") or "—"}</td>',
        "code": f'<td{L("code")}>{code_cell(f)}</td>',
        "go": f'<td class="go">{go_link(f, "Visit", "btn sm", "table")}</td>',
        "deal": (f'<td class="deal"><div>{code_cell(f) if (f.get("current_public_promo") or {}).get("code") else ""}'
                 f'{go_link(f, "Visit", "btn sm", "table")}</div></td>'),
    }
    attrs = (f'data-market="{fac(f, "market", "")}" data-dd="{fac(f, "dd", "")}" '
             f'data-cons="{"none" if cons_label(f) == "None" else "some"}" data-us="{1 if fac(f, "us") else 0}"')
    return f"<tr {attrs}>" + "".join(cells[c] for c in cols) + "</tr>"


COLS = {"firm": "Firm", "market": "Market", "price": "50K price", "target": "Profit target",
        "maxloss": "Max loss", "room": "Loss vs target", "dd": "Drawdown", "cons": "Consistency rule", "split": "Profit split",
        "payouts": "Payouts", "news": "News trading", "ea": "Bots/EAs", "us": "US traders",
        "tp": "Trustpilot", "code": "Public code", "go": '<span class="sr">Visit site</span>', "deal": '<span class="sr">Code and site</span>'}
NUMCOLS = {"price", "target", "maxloss", "tp"}
SORT_TITLE = {"room": "Sort by max loss relative to the profit target"}
SORTCOLS = {"firm": "text", "price": "num", "target": "num", "maxloss": "num", "room": "num", "tp": "num"}


def th_html(c):
    cls = ' class="n"' if c in NUMCOLS else ""
    if c in SORTCOLS:
        return (f'<th scope="col"{cls} data-sort="{SORTCOLS[c]}"><button type="button" class="sort" '
                f'title="{SORT_TITLE.get(c) or "Sort by " + COLS[c].lower()}">{COLS[c]}</button></th>')
    return f'<th scope="col"{cls}>{COLS[c]}</th>'


def firm_table(firms, cols, cls="cmp data cards rows-mid"):
    head = "".join(th_html(c) for c in cols)
    body = "".join(firm_row(f, cols) for f in firms)
    return f'<div class="tbl-wrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


FILTERS = """<div class="filters" data-filter-for="{tid}">
<fieldset><legend>Market</legend>
<button class="chip-btn" type="button" data-f="market" data-v="" aria-pressed="true">All</button>
<button class="chip-btn" type="button" data-f="market" data-v="futures" aria-pressed="false">Futures</button>
<button class="chip-btn" type="button" data-f="market" data-v="forex" aria-pressed="false">Forex &amp; CFDs</button></fieldset>
<fieldset><legend>Drawdown</legend>
<button class="chip-btn" type="button" data-f="dd" data-v="" aria-pressed="true">Any</button>
<button class="chip-btn" type="button" data-f="dd" data-v="eod" aria-pressed="false">End of day</button>
<button class="chip-btn" type="button" data-f="dd" data-v="static" aria-pressed="false">Static</button></fieldset>
<fieldset><legend>Consistency rule</legend>
<button class="chip-btn" type="button" data-f="cons" data-v="" aria-pressed="true">Any</button>
<button class="chip-btn" type="button" data-f="cons" data-v="none" aria-pressed="false">None</button></fieldset>
<span class="count" aria-live="polite"></span>
</div>"""


def filtered_table(firms, cols, tid, extra=""):
    t = firm_table(firms, cols, "cmp data cards rows-mid" + (" " + extra if extra else "")).replace("<table ", f'<table id="{tid}" ', 1)
    return FILTERS.format(tid=tid) + t


# ---------------------------------------------------------------- firm pages
def program_table(f):
    progs = f.get("programs") or []
    if not progs:
        return ""
    ccy = fac(f, "ccy", "USD")
    rows = [
        ("Steps", lambda p: esc(p.get("steps") or "—")),
        ("Price (50K, list)", lambda p: money(p.get("price_50k_list"), p.get("price_50k_currency") or ccy)
         + (" per month" if (p.get("billing") == "monthly") else (" one-time" if p.get("billing") == "one-time" else ""))),
        ("Activation fee", lambda p: money(p.get("activation_fee_50k"), p.get("price_50k_currency") or ccy)),
        ("Reset fee", lambda p: money(p.get("reset_fee_50k"), p.get("price_50k_currency") or ccy)),
        ("Profit target", lambda p: money(p.get("profit_target_50k"), fac(f, "acc_ccy") or p.get("price_50k_currency") or ccy)),
        ("Max loss", lambda p: money(p.get("max_loss_50k"), fac(f, "acc_ccy") or p.get("price_50k_currency") or ccy)),
        ("Drawdown type", lambda p: esc(p.get("drawdown_type") or "—")),
        ("Daily loss limit", lambda p: money(p.get("daily_loss_limit_50k"), fac(f, "acc_ccy") or p.get("price_50k_currency") or ccy) if p.get("daily_loss_limit_50k") not in (None, "") else "None"),
        ("Consistency rule", lambda p: esc(p.get("consistency_rule") or "—")),
        ("Minimum trading days", lambda p: esc(str(p.get("min_trading_days"))) if p.get("min_trading_days") not in (None, "") else "—"),
        ("Max contracts / size", lambda p: esc(str(p.get("max_contracts_50k"))) if p.get("max_contracts_50k") not in (None, "") else "—"),
        ("Profit split", lambda p: esc(p.get("profit_split") or "—")),
        ("Payouts", lambda p: esc(p.get("payout_frequency") or "—")),
        ("Payout rules", lambda p: esc(p.get("payout_rules_note") or "—")),
    ]
    head = '<th scope="col">50K account</th>' + "".join(f'<th scope="col">{esc(p["name"])}</th>' for p in progs)
    body = ""
    for label, fn in rows:
        vals = [fn(p) for p in progs]
        if all(v in ("—",) for v in vals):
            continue
        body += f'<tr><th scope="row">{label}</th>' + "".join(f"<td>{v}</td>" for v in vals) + "</tr>"
    size_note = ""
    sizes = f.get("account_sizes") or []
    if sizes:
        size_note = "<p class=\"muted\">Account sizes offered: " + ", ".join(
            f"{int(s/1000)}K" if isinstance(s, (int, float)) else esc(str(s)) for s in sizes) + ".</p>"
    return (f'<h2 id="plans">{esc(f["name"])} plans compared (50K)</h2>'
            f'<div class="tbl-wrap"><table class="data kv-multi"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{size_note}')


def alloc_largest(f):
    a = f.get("allocation") or {}
    if not a.get("largest_account"):
        return None
    t = strip_tags(money(a["largest_account"], a.get("currency") or "USD"))
    return t + (f" ({a['largest_account_program']})" if a.get("largest_account_program") else "")


def alloc_capacity(f):
    """(amount, basis) only when the firm itself states a maximum capital figure."""
    a = f.get("allocation") or {}
    if a.get("max_allocation"):
        return a["max_allocation"], "stated limit"
    return None, None


def alloc_table(firms):
    rows = []
    for f in firms.values():
        a = f.get("allocation") or {}
        cap, basis = alloc_capacity(f)
        if not (cap or a.get("largest_account") or a.get("scaling_max")):
            continue
        rows.append((cap or 0, f, a, basis))
    rows.sort(key=lambda r: (-r[0], -((r[2].get("largest_account") or 0))))
    out = ""
    for cap, f, a, basis in rows:
        ccy = a.get("currency") or "USD"
        capcell = strip_tags(money(cap, ccy)) if cap else "No firm-wide cap stated"
        out += (f'<tr><td><a href="/firms/{f["slug"]}/">{esc(f["name"])}</a></td>'
                f'<td class="n">{strip_tags(money(a["largest_account"], ccy)) if a.get("largest_account") else "—"}</td>'
                f'<td class="n">{capcell}</td>'
                f'<td>{esc(a.get("max_allocation_text") or a.get("max_accounts") or "—")}</td>'
                f'<td>{esc(a.get("scaling_text") or "Not confirmed")}</td></tr>')
    return ('<div class="tbl-wrap"><table class="data"><thead><tr><th scope="col">Firm</th><th scope="col">Largest account</th>'
            '<th scope="col">Max capital stated by firm</th><th scope="col">Allocation rule</th><th scope="col">Scaling</th></tr></thead>'
            f'<tbody>{out}</tbody></table></div>')


def rules_kv(f):
    items = [
        ("News trading", f.get("news_trading")),
        ("Bots and EAs", f.get("ea_bots_allowed")),
        ("Copy trading", f.get("copy_trading")),
        ("Overnight and weekend", f.get("overnight_weekend_holding")),
        ("Platforms", ", ".join(f.get("platforms") or []) or None),
        ("Instruments", f.get("instruments")),
        ("US traders", yn(f.get("us_residents_accepted"), "Accepted", "Not accepted") if f.get("us_residents_accepted") is not None else None),
        ("Restricted countries", f.get("restricted_countries_note")),
        ("Payout methods", ", ".join(f.get("payout_methods") or []) or None),
        ("Largest account", alloc_largest(f)),
        ("Max capital per trader", (f.get("allocation") or {}).get("max_allocation_text")),
        ("Account limit", (f.get("allocation") or {}).get("max_accounts")),
        ("Scaling plan", (f.get("allocation") or {}).get("scaling_text")),
        ("Path to a live account", f.get("path_to_live")),
        ("Company", f.get("legal_entity_and_hq")),
        ("Founded", str(f["founded_year"]) if f.get("founded_year") else None),
    ]
    rows = "".join(f'<tr><th scope="row">{k}</th><td>{esc(str(v))}</td></tr>' for k, v in items if v not in (None, "", "—"))
    return f'<div class="tbl-wrap"><table class="kv"><tbody>{rows}</tbody></table></div>' if rows else ""


def strip_html(f):
    ccy = fac(f, "ccy", "USD")
    cells = [("50K price", money(fac(f, "price50"), ccy), "per month" if fac(f, "monthly") else "main plan", ""),
             ("Profit target", money(fac(f, "target50"), fac(f, "acc_ccy", ccy)), "on 50K", "gain"),
             ("Max loss", money(fac(f, "maxloss50"), fac(f, "acc_ccy", ccy)), DD_LABEL.get(fac(f, "dd"), "").lower(), "loss"),
             ("Consistency rule", cons_label(f), "" if cons_label(f) in ("None", "—") else "where it applies", ""),
             ("Profit split", fac(f, "split") or "—", "to the trader", ""),
             ("Payouts", fac(f, "payouts") or "—", "", "")]
    return '<dl class="strip">' + "".join(
        f'<div class="{c}"><dt>{a}</dt><dd>{esc(b) if not b.startswith(("$", "€")) else b}<small>{esc(s)}</small></dd></div>'
        for a, b, s, c in cells) + "</dl>"


def ticket_html(f, big=True):
    p = f.get("current_public_promo") or {}
    seen = p.get("seen") or f.get("checked")
    if p.get("code"):
        return (f'<div class="ticket"><span class="code">{esc(p["code"])}</span>'
                f'<div class="what"><strong>{esc(p.get("discount") or "Discount")}</strong>'
                f'{esc(p.get("applies_to") or "")}<div class="seen">'
                + (f'Our partner code for {esc(f["name"])}, checked {fmt_date(seen)}. We earn a commission when you use it. '
                   if p.get("partner") else f'Published by {esc(f["name"])}, seen {fmt_date(seen)}. ')
                + 'Codes change often; the price at checkout is what counts.</div></div>'
                f'<button class="copy" type="button" data-copy="{esc(p["code"])}">Copy code</button></div>')
    if p.get("discount"):
        return (f'<div class="ticket"><span class="code">SALE</span><div class="what"><strong>{esc(p["discount"])}</strong>'
                f'{esc(p.get("applies_to") or "")}<div class="seen">Shown on {esc(f["name"])}\'s site, seen {fmt_date(seen)}. No code needed.</div></div>'
                f'<a class="copy" href="/go/{f["slug"]}/" rel="nofollow sponsored">Open site</a></div>')
    return (f'<div class="ticket none"><div class="what"><strong>No public {esc(f["name"])} code right now</strong>'
            f'We did not find a discount published by {esc(f["name"])} when we checked on {fmt_date(seen)}. '
            f'Firms run sales often, usually announced on their own site first.</div>'
            f'<a class="copy" href="/go/{f["slug"]}/" rel="nofollow sponsored">Check the site</a></div>')


def pros_cons(f):
    pr, co = f.get("pros") or [], f.get("cons") or []
    if not pr and not co:
        return ""
    li = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)
    return (f'<div class="pc"><div class="pro"><h3>What works</h3><ul>{li(pr)}</ul></div>'
            f'<div class="con"><h3>What to watch</h3><ul>{li(co)}</ul></div></div>')


def changes_html(f):
    ch = f.get("recent_changes_2026") or []
    if not ch:
        return ""
    rows = "".join(f'<tr><td class="n">{esc(c.get("date", ""))}</td><td>{esc(c.get("change", ""))}'
                   f'{" <a href=\"" + esc(c["source"]) + "\" rel=\"nofollow noopener\" target=\"_blank\">source</a>" if c.get("source") else ""}</td></tr>'
                   for c in sorted(ch, key=lambda c: c.get("date", ""), reverse=True))
    return (f'<h2 id="changes">Rule and price changes in 2026</h2><div class="tbl-wrap"><table class="data">'
            f'<thead><tr><th scope="col">When</th><th scope="col">What changed</th></tr></thead><tbody>{rows}</tbody></table></div>')


def status_note(f):
    if f.get("status_note"):
        return f'<div class="note warn"><p>{esc(f["status_note"])}</p></div>'
    return ""


def firm_head(f, h1, sub):
    tag = f'<span class="tag {fac(f, "market", "")}">{esc(MARKET_LABEL.get(fac(f, "market"), ""))}</span>'
    nsrc = len(f.get("sources") or [])
    by = (f'<p class="byline">Checked {fmt_date(f["checked"])} against {nsrc} official and public pages. '
          f'<a href="/methodology/">How we check</a></p>')
    p = f.get("current_public_promo") or {}
    code = p.get("code")
    price = ""
    if fac(f, "price50") is not None:
        price = (f'<div class="price"><span>50K evaluation, list price</span><b>{money(fac(f, "price50"), fac(f, "ccy", "USD"))}'
                 f'{"<small>/mo</small>" if fac(f, "monthly") else ""}</b></div>')
    deal = ""
    if code:
        deal = (f'<div class="deal"><button class="codebtn" type="button" data-copy="{esc(code)}" title="Copy code {esc(code)}">{esc(code)}</button>'
                f'<span>{esc(p.get("discount") or "Discount code")}</span>'
                f'{"<small>Our partner code. We earn a commission when you use it.</small>" if p.get("partner") else ""}</div>')
    cta = (f'<div class="cta-col">{price}{deal}{go_link(f, place="head")}'
           f'<p class="btn-note">Opens {esc(domain(f.get("website") or f.get("link")))}</p></div>')
    left = (f'<span>Code <button class="codebtn" type="button" data-copy="{esc(code)}">{esc(code)}</button></span>' if code
            else f'<span>{esc(f["name"])}</span>')
    sticky = f'<div class="sticky-cta">{left}{go_link(f, place="sticky")}</div>'
    return (f'<div class="firm-head"><div><div class="who">{avatar(f, lg=True)}{tag}</div>'
            f'<h1>{esc(h1)}</h1>{by}{sub}</div>{cta}</div>{sticky}')


def firm_faq(f):
    n = f["name"]
    ed = f["_ed_meta"].get("faq") or []
    base = []
    p = main_program(f)
    ccy = fac(f, "ccy", "USD")
    if fac(f, "dd"):
        base.append([f"What drawdown does {n} use?",
                     f"{n}'s main 50K plan uses {DD_LABEL[fac(f, 'dd')].lower()} drawdown with a max loss of "
                     f"{strip_tags(money(fac(f, 'maxloss50'), fac(f, 'acc_ccy', ccy)))}, as of {fmt_date(f['checked'])}."])
    if fac(f, "price50") is not None:
        base.append([f"How much does a {n} 50K account cost?",
                     f"The list price of {n}'s cheapest main 50K plan was {strip_tags(money(fac(f, 'price50'), ccy))}"
                     f"{' per month' if fac(f, 'monthly') else ''} when we checked on {fmt_date(f['checked'])}. "
                     f"Discounts often lower this; see the <a href=\"/firms/{f['slug']}/promo-code/\">{n} promo code</a> page."])
    if f.get("us_residents_accepted") is not None:
        base.append([f"Does {n} accept US traders?",
                     f"{'Yes' if f['us_residents_accepted'] else 'No'}, according to {n}'s own pages as of {fmt_date(f['checked'])}."])
    return ed + base


def lists_with(firm_slug, lists, firms):
    return [l for l in lists if firm_slug in [f["slug"] for f in pick_list(l, firms)]]


def build_firm_pages(site, firms, lists, compares):
    for s, f in firms.items():
        ed, body_ed = f["_ed_meta"], f["_ed_body"]
        n = f["name"]
        mod = f["checked"]
        pub = ed.get("published", mod)
        # ----- hub
        path = f"/firms/{s}/"
        trail = [("Firm reviews", "/firms/"), (f"{n} review", path)]
        h1 = ed.get("h1", f"{n} review")
        title = ed.get("title") or fit_title(f"{n} Review ({month_year(mod)}): Rules, Prices, Payouts",
                                             f"{n} Review ({month_year(mod)}): Rules & Prices",
                                             f"{n} Review ({month_year(mod)}): Rules, Prices", limit=59)
        desc = ed.get("description", f"{n} rules, 50K prices, drawdown, consistency and payout rules, checked {fmt_date(mod)} against {n}'s own pages.")
        verdict = f'<p class="lede">{ed["verdict"]}</p>' if ed.get("verdict") else ""
        promo_link = (f'<p class="cta-row">{go_link(f, place="end")} '
                      f'<a class="btn ghost" href="/firms/{s}/promo-code/">{esc(n)} promo code</a></p>')
        mid_cta = (f'<p class="cta-row">{go_link(f, f"See plans at {n}", place="plans")} '
                   f'<span class="btn-note">Opens {esc(domain(f.get("website") or f.get("link")))}. {DISCLOSE}</span></p>')
        rules_link = f'<p><a href="/firms/{s}/rules/">Every {n} rule explained</a></p>' if ed.get("rules_page") else ""
        pnote = f'<p class="muted" style="margin-top:-18px">{esc(f["price_note"])}</p>' if f.get("price_note") else ""
        jumps = [("plans", "Plans", bool(f.get("programs"))), ("sizes", "Prices by size", bool(size_table(f))),
                 ("rules", "Rules and fine print", True), ("changes", "Changes in 2026", bool(f.get("recent_changes_2026"))),
                 ("faq", "Questions", bool(firm_faq(f))), ("sources", "Sources", bool(f.get("sources")))]
        toc = ('<nav class="jump" aria-label="On this page"><span>On this page</span>'
               + "".join(f'<a href="#{i}">{t}</a>' for i, t, ok in jumps if ok) + "</nav>")
        body = (firm_head(f, h1, verdict) + status_note(f) + strip_html(f) + pnote + toc + dd_block(fac(f, "dd"))
                + f'<div class="split"><aside class="side">{ticket_html(f)}</aside><div class="content">'
                + (body_ed.split("<!--RULES-->")[0] if body_ed else "")
                + "</div></div>" + program_table(f) + mid_cta + size_table(f)
                + f'<h2 id="rules">Trading rules and fine print</h2>{rules_kv(f)}{rules_link}'
                + pros_cons(f) + changes_html(f) + promo_link + faq_html(firm_faq(f)) + sources_html(f))
        rel = [(f"/firms/{s}/promo-code/", f"{n} promo code", "Current discount and what it covers")]
        if ed.get("rules_page"):
            rel.append((f"/firms/{s}/rules/", f"{n} rules explained", "Drawdown, consistency, payouts, banned strategies"))
        for c in compares:
            if s in (c["a"], c["b"]):
                o = firms.get(c["b"] if c["a"] == s else c["a"])
                if o:
                    rel.append((f"/compare/{c['a']}-vs-{c['b']}/", f"{firms[c['a']]['name']} vs {firms[c['b']]['name']}", "Side-by-side rules and prices"))
        for l in lists_with(s, lists, firms)[:3]:
            rel.append((f"/best/{l['slug']}/", l["h1"], l["blurb"]))
        faq = firm_faq(f)
        graph = [article_schema(h1, desc, SITE + path, pub, mod)] + ([faq_schema(faq)] if faq else [])
        site.add(path, title=title, description=desc, body=body + related_html(rel), section="firms", trail=trail,
                 graph=graph, kind="article", priority="0.9", lastmod=mod)

        # ----- promo code
        path = f"/firms/{s}/promo-code/"
        trail = [("Promo codes", "/promo-codes/"), (f"{n} promo code", path)]
        p = f.get("current_public_promo") or {}
        h1 = f"{n} promo code and discount"
        title = f"{n} Promo Code & Discount ({month_year(p.get('seen') or mod)})"
        desc = (f"{n if n.startswith('The') else 'The ' + n} discount {('code ' + p['code'] + ' ') if p.get('code') else ''}"
                f"{'we checked' if p.get('partner') else 'we found'} on {fmt_date(p.get('seen') or mod)}, "
                f"what it covers, and the real 50K price after fees.")
        pt = price_table(f)
        body = (firm_head(f, h1, "") + status_note(f) + ticket_html(f)
                + '<div class="content">' + promo_text(f)
                + (f'<p>{esc(p["code"])} is our own partner code for {esc(n)}: it gives you {esc(p.get("discount") or "a discount")}, '
                   f'and we earn a commission on the purchase. {esc(n)} had no larger public code when we checked.</p>' if p.get("partner") and p.get("code") else "")
                + "</div>" + pt + size_table(f)
                + f'<div class="content"><h2>How to use a {esc(n)} code</h2><ol>'
                f'<li>Open <a href="/go/{s}/" rel="nofollow sponsored">{esc(domain(f.get("website") or f.get("link")))}</a> and pick the plan and account size.</li>'
                f'<li>At checkout, paste the code into the coupon or promo field and apply it before paying.</li>'
                f'<li>Check that the total dropped. If it did not, the code has expired or does not cover that plan.</li></ol>'
                f'<h2>What a discount does not change</h2><p>A code lowers the evaluation fee only. It does not change the profit target, '
                f'the max loss or the payout rules, and at most firms it does not cover activation or reset fees. '
                f'Most traders who buy an evaluation do not pass it, so the fee is best treated as money you can afford to lose. '
                f'<a href="/risks/">Read the risks</a>.</p>'
                f'<p><a href="/firms/{s}/">Full {esc(n)} review with every rule</a></p></div>' + sources_html(f))
        faq = [[f"Is there a {n} promo code right now?",
                (f"Yes. Our partner code {p['code']} gives {p.get('discount') or 'a discount'} at {n}, checked on {fmt_date(p.get('seen') or mod)}. We earn a commission when you use it."
                 if p.get("code") and p.get("partner") else
                 f"Yes. {n} published the code {p['code']} ({p.get('discount') or 'discount'}), seen on {fmt_date(p.get('seen') or mod)}." if p.get("code")
                 else f"We did not find a code published by {n} when we checked on {fmt_date(p.get('seen') or mod)}.")],
               [f"Does the {n} code work on resets and activation fees?",
                "Usually not. Codes normally apply to the evaluation fee only. Check the checkout total before paying."],
               [f"Can I stack two {n} codes?", "No firm we track lets you stack codes. Only one code applies per order."]]
        graph = [article_schema(h1, desc, SITE + path, pub, p.get("seen") or mod), faq_schema(faq)]
        site.add(path, title=title, description=desc, body=body + faq_html(faq) + related_html(
            [(f"/firms/{s}/", f"{n} review", "Every rule and price"), ("/promo-codes/", "All prop firm promo codes", "Every firm we track"),
             ("/tools/challenge-cost-calculator/", "True cost calculator", "Fee, activation and resets in one number")]),
                 section="promo-codes", trail=trail, graph=graph, kind="article", priority="0.9", lastmod=p.get("seen") or mod)

        # ----- rules (only when editorial says so)
        if ed.get("rules_page"):
            path = f"/firms/{s}/rules/"
            trail = [("Firm reviews", "/firms/"), (f"{n} review", f"/firms/{s}/"), (f"{n} rules", path)]
            h1 = f"{n} rules explained"
            title = fit_title(f"{n} Rules Explained ({month_year(mod)}): Drawdown, Consistency, Payouts",
                              f"{n} Rules Explained ({month_year(mod)}): Drawdown, Payouts",
                              f"{n} Rules ({month_year(mod)}): Drawdown, Payouts",
                              f"{n} Rules Explained ({month_year(mod)})")
            desc = f"Every {n} rule in plain English: drawdown, daily loss, consistency, payout rules and banned strategies, checked {fmt_date(mod)}."
            rules_body = body_ed.split("<!--RULES-->")[1] if "<!--RULES-->" in body_ed else ""
            body = (firm_head(f, h1, "") + status_note(f) + strip_html(f) + dd_block(fac(f, "dd"))
                    + program_table(f) + f'<div class="content">{rules_body}</div>'
                    + f'<h2>Other rules</h2>{rules_kv(f)}' + changes_html(f) + sources_html(f))
            site.add(path, title=title, description=desc, body=body + related_html(
                [(f"/firms/{s}/", f"{n} review", "Prices, pros and cons"), (f"/firms/{s}/promo-code/", f"{n} promo code", "Current discount"),
                 ("/tools/drawdown-simulator/", "Drawdown simulator", "See how trailing and static limits move")]),
                     section="firms", trail=trail, graph=[article_schema(h1, desc, SITE + path, pub, mod)],
                     kind="article", priority="0.8", lastmod=mod)


def size_program(f):
    for pr in f.get("programs") or []:
        if pr.get("prices_by_size"):
            return pr
    return None


def size_label(n):
    n = int(n)
    return f"{n // 1000:g}K" if n % 1000 == 0 else f"{n / 1000:g}K"


def size_price(f, size):
    pr = size_program(f)
    if not pr:
        return None
    return (pr["prices_by_size"] or {}).get(str(size))


def size_table(f):
    """Price of one plan at every account size, from the firm's own pages."""
    pr = size_program(f)
    if not pr:
        return ""
    ccy = pr.get("prices_by_size_ccy") or fac(f, "ccy", "USD")
    mo = " /mo" if pr.get("prices_by_size_monthly") else ""
    resets = pr.get("resets_by_size") or {}
    head = '<th scope="col">Account size</th><th scope="col" class="n">Price</th>' + (
        '<th scope="col" class="n">Reset</th>' if resets else "")
    rows = "".join(
        f'<tr><th scope="row">{size_label(k)}</th><td class="n">{money(v, ccy)}{mo}</td>'
        + (f'<td class="n">{money(resets[k], ccy) if k in resets else "—"}</td>' if resets else "") + "</tr>"
        for k, v in pr["prices_by_size"].items())
    plan = re.split(r"\s*\(|\s*->", pr["name"])[0]
    note = f'{esc(pr["prices_by_size_note"])} ' if pr.get("prices_by_size_note") else ""
    return (f'<h2 id="sizes">{esc(f["name"])} prices by account size</h2>'
            f'<p class="muted">{esc(plan)}, list prices before discounts. {note}From '
            f'<a href="{esc(pr["prices_by_size_source"])}" rel="nofollow noopener" target="_blank">{esc(domain(pr["prices_by_size_source"]))}</a>, '
            f'checked {fmt_date(pr["prices_by_size_seen"])}.</p>'
            f'<div class="tbl-wrap"><table class="data cmp sizes"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>')


SIZE_COLS = [25000, 50000, 100000, 150000, 200000]


def sizes_overview(firms):
    """All firms with published size prices, sorted by 100K price (USD first)."""
    rows = []
    for f in firms.values():
        pr = size_program(f)
        if not pr:
            continue
        rows.append(f)
    def key(f):
        pr = size_program(f)
        v = (pr["prices_by_size"] or {}).get("100000")
        return (pr.get("prices_by_size_ccy", "USD") != "USD", v is None, v or 0)
    rows.sort(key=key)
    head = ('<th scope="col" data-sort="text"><button type="button" class="sort" title="Sort by firm">Firm</button></th>'
            '<th scope="col">Plan</th>'
            + "".join(f'<th scope="col" class="n" data-sort="num"><button type="button" class="sort" title="Sort by {size_label(c)} price">{size_label(c)}</button></th>' for c in SIZE_COLS))
    body = ""
    for f in rows:
        pr = size_program(f)
        ccy = pr.get("prices_by_size_ccy") or "USD"
        mo = "<small>/mo</small>" if pr.get("prices_by_size_monthly") else ""
        plan = re.split(r"\s*\(|\s*->", pr["name"])[0]
        cells = ""
        for c in SIZE_COLS:
            v = pr["prices_by_size"].get(str(c))
            dv = v if (v is not None and ccy == "USD") else ""
            cells += f'<td class="n" data-v="{dv}">{money(v, ccy) + mo if v is not None else "—"}</td>'
        body += (f'<tr><th scope="row" data-v="{esc(f["name"].lower())}"><a href="/firms/{f["slug"]}/#sizes">{avatar(f)}{esc(f["name"])}</a></th>'
                 f'<td>{esc(plan)}</td>{cells}</tr>')
    return (f'<div class="tbl-wrap"><table class="cmp data sizes-all"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')


def price_table(f):
    progs = f.get("programs") or []
    p = f.get("current_public_promo") or {}
    pct = None
    m = re.search(r"(\d{1,2})\s*%", p.get("discount") or "")
    if m and (p.get("code") or p.get("discount")) and not p.get("applies_to_note_excludes"):
        pct = int(m.group(1))
    rows = ""
    for pr in progs:
        lp = pr.get("price_50k_list")
        if lp in (None, ""):
            continue
        ccy = pr.get("price_50k_currency") or fac(f, "ccy", "USD")
        act = pr.get("activation_fee_50k") or 0
        disc = round(lp * (100 - pct) / 100, 2) if pct and (not p.get("programs") or pr["name"] in p["programs"]) else None
        rows += (f'<tr><th scope="row">{esc(pr["name"])}</th><td class="n">{money(lp, ccy)}'
                 f'{" /mo" if pr.get("billing") == "monthly" else ""}</td>'
                 + ((f'<td class="n">{money(disc, ccy, dec=True)}</td>' if disc else '<td class="n">—</td>') if pct else "")
                 + f'<td class="n">{money(act, ccy) if act else "None"}</td></tr>')
    if not rows:
        return ""
    head = ('<th scope="col">50K plan</th><th scope="col" class="n">List price</th>'
            + (f'<th scope="col" class="n">With {pct}% off</th>' if pct else "") + '<th scope="col" class="n">Activation fee</th>')
    note = (f'<p class="muted">The discounted column assumes the {pct}% applies to that plan. Check the checkout total; some codes exclude plans or sizes.</p>'
            if pct else "")
    return (f'<h2>{esc(f["name"])} 50K prices</h2><div class="tbl-wrap"><table class="data cmp"><thead><tr>{head}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>{note}')


def promo_text(f):
    ed = f["_ed_meta"]
    if ed.get("promo_text"):
        return ed["promo_text"]
    n = f["name"]
    return (f"<p>This page lists the discount {esc(n)} itself publishes, the date we saw it, and what the 50K plans cost before and after it. "
            f"We do not copy codes from coupon sites, because many of them are expired or belong to someone else.</p>")


# ---------------------------------------------------------------- lists
def pick_list(l, firms):
    out = []
    for f in firms.values():
        ok = True
        for k, v in (l.get("where") or {}).items():
            fv = fac(f, k)
            if isinstance(v, list):
                ok = ok and fv in v
            else:
                ok = ok and fv == v
        if l.get("max_price") is not None:
            ok = ok and fac(f, "price50") is not None and fac(f, "price50") <= l["max_price"]
        if l.get("only"):
            ok = ok and f["slug"] in l["only"]
        if ok:
            out.append(f)
    order = l.get("order")
    if order:
        out.sort(key=lambda f: order.index(f["slug"]) if f["slug"] in order else 999)
    else:
        key = l.get("sort", "price50")
        val = ((lambda f: (biggest_maxloss(f) or (None,))[0]) if key == "maxloss_max"
               else (lambda f: alloc_capacity(f)[0]) if key == "alloc"
               else (lambda f: size_price(f, 100000) if (size_program(f) or {}).get("prices_by_size_ccy", "USD") == "USD" else None) if key == "p100k"
               else (lambda f: fac(f, key)))
        if key in ("maxloss_max", "alloc", "p100k"):
            out = [f for f in out if val(f) is not None]
        sign = -1 if l.get("desc") else 1
        out.sort(key=lambda f: (val(f) is None, sign * (val(f) or 0),
                                -((f.get("allocation") or {}).get("scaling_max") or 0) if key == "alloc" else 0))
    return out[: l.get("limit", 10)]


def biggest_maxloss(f):
    """(amount, program) for the program with the largest numeric 50K max loss."""
    best = None
    for p in f.get("programs") or []:
        v = p.get("max_loss_50k")
        if isinstance(v, (int, float)) and (best is None or v > best[0]):
            best = (v, p)
    return best


def names_join(fs):
    ns = [f["name"] for f in fs]
    if not ns:
        return "none"
    return ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " and " + ns[-1]


def price_txt(f):
    return strip_tags(money(fac(f, "price50"), fac(f, "ccy", "USD"))) + (" a month" if fac(f, "monthly") else "")


def list_faq_fill(a, picks, whys):
    """FAQ answers in lists.json may use placeholders that are filled from the current data, so they stay true
    when prices or the ranking change: {top1} {top1_why} {top2} {top3} {n} {names} {cheapest_once} {cheapest_month}
    {eod} {static} {nocons} {codes}."""
    if "{" not in a:
        return a
    usd = [f for f in picks if fac(f, "price50") is not None and fac(f, "ccy", "USD") == "USD"]
    once = sorted([f for f in usd if not fac(f, "monthly")], key=lambda f: fac(f, "price50"))
    monthly = sorted([f for f in usd if fac(f, "monthly")], key=lambda f: fac(f, "price50"))
    rep = {
        "{n}": str(len(picks)),
        "{names}": names_join(picks),
        "{top1}": picks[0]["name"] if picks else "",
        "{top1_why}": whys.get(picks[0]["slug"], "") if picks else "",
        "{top2}": picks[1]["name"] if len(picks) > 1 else "",
        "{top3}": picks[2]["name"] if len(picks) > 2 else "",
        "{cheapest_once}": f"{once[0]['name']} at {price_txt(once[0])}" if once else "none",
        "{cheapest_month}": f"{monthly[0]['name']} at {price_txt(monthly[0])}" if monthly else "none",
        "{eod}": names_join([f for f in picks if fac(f, "dd") == "eod"]),
        "{static}": names_join([f for f in picks if fac(f, "dd") == "static"]),
        "{nocons}": names_join([f for f in picks if cons_label(f) == "None"]),
        "{codes}": names_join([f for f in picks if (f.get("current_public_promo") or {}).get("code")]),
    }
    p100 = [(size_price(f, 100000), f) for f in picks if size_price(f, 100000) is not None
            and (size_program(f) or {}).get("prices_by_size_ccy", "USD") == "USD"]
    if p100:
        lo, hi = min(p100, key=lambda x: x[0]), max(p100, key=lambda x: x[0])
        per = lambda f: " a month" if (size_program(f) or {}).get("prices_by_size_monthly") else " one-time"
        rep["{p100_min}"] = f"{strip_tags(money(lo[0], 'USD'))}{per(lo[1])} ({lo[1]['name']})"
        rep["{p100_max}"] = f"{strip_tags(money(hi[0], 'USD'))}{per(hi[1])} ({hi[1]['name']})"
    for k, v in rep.items():
        a = a.replace(k, esc(v))
    return a


def poss(n):
    return n + ("'" if n.endswith("s") else "'s")


def compare_faq(a, b):
    """Data-driven questions for X vs Y pages."""
    da, db = fmt_date(a["checked"]), fmt_date(b["checked"])
    d = (f"as of {da}" if da == db else f"as checked on {da} and {db}")
    A, B = a["name"], b["name"]
    out = []
    pa, pb = fac(a, "price50"), fac(b, "price50")
    if pa is not None and pb is not None:
        txt = f"{poss(A)} main 50K plan lists at {price_txt(a)} and {poss(B)} at {price_txt(b)}, before discounts, {d}."
        same_ccy = fac(a, "ccy", "USD") == fac(b, "ccy", "USD")
        same_bill = bool(fac(a, "monthly")) == bool(fac(b, "monthly"))
        if same_ccy and same_bill and pa != pb:
            txt += f" {A if pa < pb else B} has the lower list price."
        elif not same_ccy:
            txt += " The prices are in different currencies, so convert before you compare."
        elif not same_bill:
            txt += " One is a monthly fee and the other a one-time fee, so the cheaper one depends on how long you take to pass."
        out.append([f"Is {A} or {B} cheaper?", txt + ' Use the <a href="/tools/challenge-cost-calculator/">true cost calculator</a> for the full cost.'])
    if fac(a, "dd") and fac(b, "dd") and fac(a, "maxloss50") and fac(b, "maxloss50"):
        def ddt(f):
            kind = ("a drawdown type that depends on the plan" if fac(f, "dd") == "mixed"
                    else DD_LABEL[fac(f, "dd")].lower() + " drawdown")
            return (f"{f['name']} uses {kind} with a 50K max loss of "
                    f"{strip_tags(money(fac(f, 'maxloss50'), fac(f, 'acc_ccy', fac(f, 'ccy', 'USD'))))} on its main plan")
        out.append([f"What is the difference between {A} and {B} drawdown?", f"{ddt(a)}. {ddt(b)}. Figures {d}."])
    ca, cb = cons_label(a), cons_label(b)
    if "—" not in (ca, cb):
        def ct(f, c):
            where = {"Eval only": "in the evaluation only", "Funded only": "on funded accounts only",
                     "Eval + funded": "in the evaluation and on funded accounts"}[c] if c != "None" else ""
            return (f"{f['name']} has no consistency rule on its main plan" if c == "None"
                    else f"{f['name']} applies a consistency rule {where}")
        out.append([f"Does {A} or {B} have a consistency rule?", f"{ct(a, ca)}. {ct(b, cb)}."])
    ua, ub = a.get("us_residents_accepted"), b.get("us_residents_accepted")
    if ua is not None and ub is not None:
        if ua and ub:
            t = f"Yes. Both {A} and {B} accept US residents, according to their own pages ({d})."
        elif not ua and not ub:
            t = f"No. Neither {A} nor {B} accepts US residents, according to their own pages ({d})."
        else:
            t = f"{A if ua else B} accepts US residents and {B if ua else A} does not, according to their own pages ({d})."
        out.append([f"Do {A} and {B} accept US traders?", t])
    return out


def build_lists(site, firms, lists):
    for l in lists:
        picks = pick_list(l, firms)
        path = f"/best/{l['slug']}/"
        trail = [("Best prop firms", "/best/"), (l["h1"], path)]
        mod = max([f["checked"] for f in picks] + ([(f.get("allocation") or {}).get("checked") or "" for f in picks]
                                                    if l.get("why_auto") == "alloc" else [])
                  + ([(size_program(f) or {}).get("prices_by_size_seen") or "" for f in picks] if l.get("why_auto") == "p100k" else []) or [TODAY])
        items, whys = "", {}
        for f in picks:
            why = (l.get("why") or {}).get(f["slug"]) or (f["_ed_meta"].get("one_liner") or f.get("best_for") or "")
            if l.get("why_auto") == "alloc" and alloc_capacity(f)[0]:
                cap, basis = alloc_capacity(f)
                a = f["allocation"]
                why = a.get("max_allocation_text") or f"Up to {strip_tags(money(cap, a.get('currency') or 'USD'))} at once."
            if l.get("why_auto") == "p100k" and size_price(f, 100000) is not None:
                pr = size_program(f)
                mo = " a month" if pr.get("prices_by_size_monthly") else " one-time"
                plan = re.split(r"\s*\(|\s*->", pr["name"])[0]
                bigger = [(c, pr["prices_by_size"].get(str(c))) for c in (150000, 200000) if pr["prices_by_size"].get(str(c)) is not None]
                why = (f"100K {plan} for {strip_tags(money(size_price(f, 100000), 'USD'))}{mo}"
                       + (f"; {size_label(bigger[0][0])} for {strip_tags(money(bigger[0][1], 'USD'))}{mo}" if bigger else "") + ".")
            if l.get("why_auto") == "maxloss" and biggest_maxloss(f):
                v, pr = biggest_maxloss(f)
                dd = re.split(r"[(;,]", pr.get("drawdown_type") or "")[0].strip()
                why = (f"Largest 50K max loss: {strip_tags(money(v, fac(f, 'acc_ccy', fac(f, 'ccy', 'USD'))))} "
                       f"({v / 500:g}% of the account) on {pr['name']}" + (f", {dd[0].lower() + dd[1:]}" if dd else "") + ".")
            ccy = fac(f, "ccy", "USD")
            lead = (f"50K for {strip_tags(money(fac(f, 'price50'), ccy))}{'/mo' if fac(f, 'monthly') else ''}, "
                    if fac(f, 'price50') is not None else "50K price not published, ")
            facts = (lead + f"target {strip_tags(money(fac(f, 'target50'), fac(f, 'acc_ccy', ccy)))}, max loss {strip_tags(money(fac(f, 'maxloss50'), fac(f, 'acc_ccy', ccy)))}, "
                     f"{DD_LABEL.get(fac(f, 'dd'), '').lower()} drawdown")
            chips = (f'<li><span>50K</span>{(strip_tags(money(fac(f, "price50"), ccy)) + ("/mo" if fac(f, "monthly") else "")) if fac(f, "price50") is not None else "price not published"}</li>'
                     f'<li class="gain"><span>Target</span>{strip_tags(money(fac(f, "target50"), fac(f, "acc_ccy", ccy)))}</li>'
                     f'<li class="loss"><span>Max loss</span>{strip_tags(money(fac(f, "maxloss50"), fac(f, "acc_ccy", ccy)))}</li>'
                     f'<li><span>Drawdown</span>{esc(DD_LABEL.get(fac(f, "dd"), "—"))}</li>')
            code = (f.get("current_public_promo") or {}).get("code")
            codeline = (f'<span class="codeline">Code <button class="codebtn" type="button" data-copy="{esc(code)}">{esc(code)}</button></span>'
                        if code else "")
            whys[f["slug"]] = why
            items += (f'<li><div><h3>{avatar(f)}<a href="/firms/{f["slug"]}/">{esc(f["name"])}</a></h3><p>{esc(why)}</p>'
                      f'<ul class="facts">{chips}</ul></div>'
                      f'<div class="acts">{go_link(f, place="list")}{codeline}'
                      f'<a class="rv" href="/firms/{f["slug"]}/">Read {esc(f["name"])} review</a></div></li>')
        cols = l.get("cols", ["firm", "price", "target", "maxloss", "dd", "cons", "split", "payouts"])
        body = (f'<header class="art-head"><h1>{esc(l["h1"])}</h1><p class="byline">Updated {fmt_date(mod)}. '
                f'Facts checked against each firm\'s own pages. <a href="/methodology/">How we rank</a>. {DISCLOSE}</p></header>'
                f'<div class="content"><p class="lede">{l["intro"]}</p></div>'
                f'<ol class="rank">{items}</ol><h2>Side by side</h2>{firm_table(picks, cols)}'
                f'<div class="content">{l.get("body", "").replace("{{ALLOC_TABLE}}", "</div>" + alloc_table(firms) + "<div class=\"content\">").replace("{{SIZE_TABLE}}", "</div>" + sizes_overview(firms) + "<div class=\"content\">")}</div>')
        faq = [[q, list_faq_fill(a, picks, whys)] for q, a in (l.get("faq") or [])]
        desc = l["description"]
        graph = [article_schema(l["h1"], desc, SITE + path, l.get("published", mod), mod),
                 {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": f["name"],
                  "url": f"{SITE}/firms/{f['slug']}/"} for i, f in enumerate(picks)]}] + ([faq_schema(faq)] if faq else [])
        site.add(path, title=l["title"].replace("{month}", month_year(mod)), description=desc, body=body + faq_html(faq)
                 + related_html([("/compare/", "Compare every firm", "Filter by market, drawdown and consistency rule"),
                                 ("/tools/challenge-cost-calculator/", "True cost calculator", "What an evaluation really costs")]),
                 section="best", trail=trail, graph=graph, kind="article", priority="0.9", lastmod=mod)


def build_compares(site, firms, compares):
    for c in compares:
        a, b = firms.get(c["a"]), firms.get(c["b"])
        if not a or not b:
            continue
        path = f"/compare/{c['a']}-vs-{c['b']}/"
        h1 = f"{a['name']} vs {b['name']}"
        mod = max(a["checked"], b["checked"])
        trail = [("Compare", "/compare/"), (h1, path)]

        def row(label, fn, cls=""):
            c = f' class="{cls}"' if cls else ""
            return f'<tr><th scope="row">{label}</th><td{c}>{fn(a)}</td><td{c}>{fn(b)}</td></tr>'
        rows = "".join([
            row("Market", lambda f: esc(MARKET_LABEL.get(fac(f, "market"), "—"))),
            row("Main 50K plan", lambda f: money(fac(f, "price50"), fac(f, "ccy", "USD")) + (" /mo" if fac(f, "monthly") else "")),
            row("Profit target (50K)", lambda f: money(fac(f, "target50"), fac(f, "acc_ccy", fac(f, "ccy", "USD"))), "gain"),
            row("Max loss (50K)", lambda f: money(fac(f, "maxloss50"), fac(f, "acc_ccy", fac(f, "ccy", "USD"))), "loss"),
            row("Max loss against target", room_span, "room"),
            row("Drawdown", lambda f: esc(DD_LABEL.get(fac(f, "dd"), "—"))),
            row("Consistency rule", lambda f: esc(cons_label(f))),
            row("Profit split", lambda f: esc(fac(f, "split") or "—")),
            row("Payouts", lambda f: esc(fac(f, "payouts") or "—")),
            row("News trading", lambda f: esc(f.get("news_trading") or "—")),
            row("Bots and EAs", lambda f: esc(f.get("ea_bots_allowed") or "—")),
            row("US traders", lambda f: yn(f.get("us_residents_accepted"))),
            row("Platforms", lambda f: esc(", ".join(f.get("platforms") or []) or "—")),
            row("Public code", lambda f: code_cell(f)),
            row("", lambda f: go_link(f, cls="btn sm", place="compare-table")),
        ])
        tbl = (f'<div class="tbl-wrap"><table class="kv data duel"><thead><tr><th scope="col"></th>'
               f'<th scope="col"><a href="/firms/{a["slug"]}/">{avatar(a)}{esc(a["name"])}</a></th>'
               f'<th scope="col"><a href="/firms/{b["slug"]}/">{avatar(b)}{esc(b["name"])}</a></th></tr></thead><tbody>{rows}</tbody></table></div>')
        desc = c.get("description", f"{a['name']} vs {b['name']}: 50K prices, drawdown, consistency rules and payouts side by side, checked {fmt_date(mod)}.")
        body = (f'<header class="art-head"><h1>{esc(h1)}</h1><p class="byline">Checked {fmt_date(mod)} against both firms\' own pages. {DISCLOSE}</p></header>'
                f'<div class="content"><p class="lede">{c["verdict"]}</p></div>{tbl}<div class="content">{c.get("body", "")}</div>'
                f'<p class="cta-row">{go_link(a, place="compare")} {go_link(b, place="compare")}</p>')
        have = {q.lower() for q, _ in (c.get("faq") or [])}
        faq = (c.get("faq") or []) + [qa for qa in compare_faq(a, b) if qa[0].lower() not in have]
        ctitle = c.get("title") or fit_title(f"{h1} ({month_year(mod)}): Rules & Prices Compared",
                                             f"{h1}: Rules & Prices ({month_year(mod)})", f"{h1} ({month_year(mod)})")
        site.add(path, title=ctitle, description=desc,
                 body=body + faq_html(faq) + related_html([(f"/firms/{a['slug']}/", f"{a['name']} review", "Full rules"),
                                                          (f"/firms/{b['slug']}/", f"{b['name']} review", "Full rules")]),
                 section="compare", trail=trail, kind="article", priority="0.8", lastmod=mod,
                 graph=[article_schema(h1, desc, SITE + path, c.get("published", mod), mod)] + ([faq_schema(faq)] if faq else []))


# ---------------------------------------------------------------- hand-written pages
def build_static_pages(site, firms, lists, compares, contracts):
    for p in sorted((SRC / "pages").glob("*.html")):
        meta, body = read_meta_file(p)
        for k in ("title", "description"):
            meta[k] = meta[k].replace("{{FIRM_COUNT}}", str(len(firms)))
        if len(meta["title"]) > 60 and meta["title"].endswith(" | PropFirmNerd"):
            meta["title"] = meta["title"][: -len(" | PropFirmNerd")]
        slug = p.stem
        path = "/" if slug == "home" else f"/{slug.replace('__', '/')}/"
        body = expand(body, firms, lists, compares, contracts)
        sec = meta.get("section")
        trail = None
        if slug not in ("home", "404"):
            trail = []
            if sec and sec in SECTION_TITLES and f"/{sec}/" != path:
                trail.append((SECTION_TITLES[sec], f"/{sec}/"))
            trail.append((meta["h1"], path))
        kind = meta.get("kind", "page")
        graph = []
        if kind == "article":
            mod = meta.get("modified", meta.get("published", TODAY))
            d = fmt_date(mod)
            body = (f'<header class="art-head"><h1>{esc(meta["h1"])}</h1><p class="byline">Updated {d}. '
                    f'<a href="/about/">PropFirmNerd editorial team</a></p></header><div class="content">{body}</div>')
            graph.append(article_schema(meta["h1"], meta["description"], SITE + path, meta.get("published", mod), mod))
        elif kind == "tool":
            graph.append({"@type": "WebApplication", "name": meta["h1"], "url": SITE + path, "applicationCategory": "FinanceApplication",
                          "operatingSystem": "Any", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}})
        if slug == "home":
            graph.append({"@type": "WebSite", "name": NAME, "url": SITE + "/"})
            graph.append({"@type": "Organization", "name": NAME, "url": SITE + "/", "logo": SITE + "/favicon-192.png"})
        if meta.get("faq"):
            graph.append(faq_schema(meta["faq"]))
        site.add(path, title=meta["title"], description=meta["description"],
                 body=body + faq_html(meta.get("faq")) + related_html([tuple(r) for r in meta.get("related", [])]),
                 section=sec, trail=trail, graph=graph, kind=kind, scripts=meta.get("scripts", []),
                 priority=meta.get("priority", "0.7"), lastmod=meta.get("modified", meta.get("published", TODAY)),
                 noindex=meta.get("noindex", False) or slug == "404")


def expand(body, firms, lists, compares, contracts):
    """Placeholders usable in hand-written pages."""
    allf = sorted(firms.values(), key=lambda f: f["name"].lower())
    rep = {
        "{{FIRM_COUNT}}": str(len(firms)),
        "{{HERO_CHART}}": hero_svg(),
        "{{SOURCE_COUNT}}": str(sum(len(f.get("sources") or []) for f in allf)),
        "{{LAST_CHECKED}}": fmt_date(max(f["checked"] for f in allf)),
        "{{PROMO_TILES}}": coupons_html(allf),
        "{{HOME_TABLE}}": filtered_table(allf, ["firm", "price", "target", "maxloss", "room", "dd", "cons", "split", "deal"], "t-home"),
        "{{COMPARE_TABLE}}": filtered_table(allf, ["firm", "price", "target", "maxloss", "dd", "cons", "split", "payouts", "news", "ea", "us", "tp", "deal"], "t-all", "big"),
        "{{FIRM_ROWS}}": rows_html([(f"/firms/{f['slug']}/", f"{f['name']} review", f["_ed_meta"].get("one_liner") or f.get("best_for") or "") for f in allf]),
        "{{FUTURES_ROWS}}": rows_html([(f"/firms/{f['slug']}/", f"{f['name']} review", f["_ed_meta"].get("one_liner") or f.get("best_for") or "") for f in allf if fac(f, "market") in ("futures", "multi")]),
        "{{FOREX_ROWS}}": rows_html([(f"/firms/{f['slug']}/", f"{f['name']} review", f["_ed_meta"].get("one_liner") or f.get("best_for") or "") for f in allf if fac(f, "market") in ("forex", "multi")]),
        "{{PROMO_TABLE}}": promo_table(allf),
        "{{PROMO_ROWS}}": rows_html([(f"/firms/{f['slug']}/promo-code/", f"{f['name']} promo code",
                                      (f"Code {f['current_public_promo']['code']}: {f['current_public_promo'].get('discount') or ''}" if (f.get('current_public_promo') or {}).get('code')
                                       else "Current discount and real price")) for f in allf]),
        "{{LIST_ROWS}}": rows_html([(f"/best/{l['slug']}/", l["h1"], l["blurb"]) for l in lists]),
        "{{COMPARE_ROWS}}": rows_html([(f"/compare/{c['a']}-vs-{c['b']}/", f"{firms[c['a']]['name']} vs {firms[c['b']]['name']}", c.get("blurb", "Rules and prices side by side"))
                                       for c in compares if c["a"] in firms and c["b"] in firms]),
        "{{CONTRACTS_JSON}}": json.dumps(contracts, ensure_ascii=False),
        "{{FIRMS_JSON}}": json.dumps([{"slug": f["slug"], "name": f["name"], "ccy": fac(f, "ccy", "USD"), "programs": [
            {k: p.get(k) for k in ("name", "billing", "price_50k_list", "activation_fee_50k", "reset_fee_50k", "profit_target_50k", "max_loss_50k", "profit_split")}
            for p in (f.get("programs") or [])]} for f in allf], ensure_ascii=False),
    }
    for k, v in rep.items():
        body = body.replace(k, v)
    body = re.sub(r"\{\{CONTRACT_TABLE:([A-Z0-9,]+)\}\}", lambda m: contract_table(contracts, m.group(1).split(",")), body)
    return body


def coupons_html(allf):
    """Home page: one tile per firm linking to its promo code page, with the code shown when there is one."""
    out = ""
    for f in allf:
        p = f.get("current_public_promo") or {}
        chip = f'<span class="codechip">{esc(p["code"])}</span>' if p.get("code") else ""
        out += (f'<li><a href="/firms/{f["slug"]}/promo-code/">{avatar(f)}<span><strong>{esc(f["name"])} promo code</strong>'
                f'<span class="d">{esc(p.get("discount") or ("No code needed" if p.get("discount") else "No public code right now"))}'
                f'{" (our partner code)" if p.get("partner") and p.get("code") else ""}</span></span>{chip}</a></li>')
    return f'<ul class="coupons">{out}</ul>'


def promo_table(allf):
    rows = ""
    for f in allf:
        p = f.get("current_public_promo") or {}
        seen = p.get("seen") or f["checked"]
        rows += (f'<tr><th scope="row" data-v="{esc(f["name"].lower())}"><a href="/firms/{f["slug"]}/promo-code/">{avatar(f)}{esc(f["name"])}</a></th>'
                 f'<td>{code_cell(f)}</td><td>{esc(p.get("discount") or "No public discount found")}'
                 f'{" <small>(our partner code)</small>" if p.get("partner") and p.get("code") else ""}</td>'
                 f'<td class="n" data-v="{seen}">{fmt_date(seen)}</td>'
                 f'<td class="go">{go_link(f, "Get deal" if p.get("code") or p.get("discount") else "Visit", "btn sm", "promo-table")}</td></tr>')
    return (f'<div class="tbl-wrap"><table class="cmp data promo"><thead><tr>'
            f'<th scope="col" data-sort="text"><button type="button" class="sort" title="Sort by firm">Firm</button></th><th scope="col">Code</th>'
            f'<th scope="col">Discount</th><th scope="col" class="n" data-sort="text"><button type="button" class="sort" title="Sort by date">Seen</button></th>'
            f'<th scope="col"><span class="sr">Visit site</span></th></tr></thead><tbody>{rows}</tbody></table></div>')


def contract_table(contracts, syms):
    by = {c["symbol"]: c for c in contracts}
    rows = ""
    for s in syms:
        c = by.get(s)
        if not c:
            continue
        rows += (f'<tr><th scope="row">{esc(c["symbol"])}</th><td>{esc(c["name"])}</td><td class="n">{esc(c.get("tick_size_text") or str(c["tick_size"]))}</td>'
                 f'<td class="n">${c["tick_value_usd"]:,.2f}</td><td class="n">${c["point_value_usd"]:,.2f}</td></tr>')
    return (f'<div class="tbl-wrap"><table class="data"><thead><tr><th scope="col">Symbol</th><th scope="col">Contract</th>'
            f'<th scope="col" class="n">Tick size</th><th scope="col" class="n">Tick value</th><th scope="col" class="n">Point value</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            + '<p class="muted" style="font-size:14px">Source: CME Group rulebook ' + ", ".join(
                f'<a href="{esc(by[s]["source_url"])}" rel="nofollow noopener" target="_blank">{esc(s)}</a>' for s in syms if s in by and by[s].get("source_url"))
            + '. Checked October 2026.</p>')


# ---------------------------------------------------------------- build
def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(STATIC, OUT)
    firms = load_firms()
    lists = load_json("lists.json", [])
    compares = load_json("compares.json", [])
    contracts = load_json("contracts.json", [])
    site = Site()
    build_firm_pages(site, firms, lists, compares)
    build_lists(site, firms, lists)
    build_compares(site, firms, compares)
    build_static_pages(site, firms, lists, compares, contracts)
    n = site.write()
    redirects = []
    for s, f in firms.items():
        target = f.get("link") or f.get("website")
        redirects += [f"/go/{s}/ {target} 302", f"/go/{s} {target} 302"]
    (OUT / "_redirects").write_text("\n".join(redirects) + "\n", encoding="utf-8")
    (OUT / "_headers").write_text("/go/*\n  X-Robots-Tag: noindex\n/assets/*\n  Cache-Control: public, max-age=86400\n", encoding="utf-8")
    print(f"built {n} indexable pages from {len(firms)} firms -> {OUT}")


if __name__ == "__main__":
    build()
