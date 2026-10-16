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
GA_ID = ""  # e.g. G-XXXXXXX; empty = no analytics tag

NAV = [("firms", "Firm reviews"), ("compare", "Compare"), ("best", "Best of"),
       ("promo-codes", "Promo codes"), ("tools", "Tools"), ("guides", "Guides")]
SECTION_TITLES = {"firms": "Firm reviews", "compare": "Compare", "best": "Best prop firms",
                  "promo-codes": "Promo codes", "tools": "Tools", "guides": "Guides"}
MARKET_LABEL = {"futures": "Futures", "forex": "Forex & CFDs", "multi": "Futures & forex"}
DD_LABEL = {"eod": "End-of-day trailing", "intraday": "Intraday trailing", "static": "Static",
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
    grid = "".join(f'<line x1="{x(i*5):.1f}" x2="{x(i*5):.1f}" y1="{T}" y2="{H-B}" stroke="#DCE1E7" stroke-dasharray="2 3"/>'
                   for i in range(1, 5))
    labels = "".join(f'<text x="{(x(i*5)+x(min(i*5+4, n-1)))/2:.1f}" y="{H-6}" font-size="10" fill="#6E7A89" text-anchor="middle">Day {i+1}</text>'
                     for i in range(5))
    start = f'<line x1="{L}" x2="{W-R}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="#C5CCD5"/>'
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(DD_LABEL.get(kind, ""))} drawdown illustration">'
            f'{grid}{start}<path d="{th}" fill="none" stroke="#C2362F" stroke-width="2.2"/>'
            f'<path d="{eq}" fill="none" stroke="#18212C" stroke-width="1.6"/>{labels}</svg>')


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
            f'<p class="key"><i style="background:#18212C"></i>Account balance '
            f'<i style="background:#C2362F;margin-left:12px"></i>Loss limit<br>'
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
    out = ['<section class="faq"><h2>Questions traders ask</h2>']
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


def sources_html(firm):
    srcs = firm.get("sources") or []
    if not srcs:
        return ""
    lis = "".join(f'<li><a href="{esc(s["url"])}" rel="nofollow noopener" target="_blank">{esc(domain(s["url"]) + "/" + s["url"].split("/", 3)[-1] if s["url"].count("/") > 2 else s["url"])}</a>'
                  f'{(" — " + esc(s.get("supports", ""))) if s.get("supports") else ""}</li>' for s in srcs)
    return (f'<section class="sources"><h2>Sources</h2><p>Checked {fmt_date(firm["checked"])}. '
            f'We link the firm\'s own pages wherever we can. If something changed, '
            f'<a href="/contact/">tell us</a>.</p><ol>{lis}</ol></section>')


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
        '<path d="M1 20 L9 20 L9 17 L17 17 L17 13 L25 13" fill="none" stroke="#C2362F" stroke-width="2.4"/></svg>'
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
<meta name="theme-color" content="#18212C">{ga}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap" rel="stylesheet">
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
{scripts}
<script>
(function(){{var b=document.querySelector('.menu-btn'),n=document.getElementById('nav');
b&&b.addEventListener('click',function(){{var o=n.classList.toggle('open');b.setAttribute('aria-expanded',o)}});
document.querySelectorAll('[data-copy]').forEach(function(btn){{btn.addEventListener('click',function(){{
var t=btn.getAttribute('data-copy');(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){{btn.textContent='Copied'}},function(){{btn.textContent=t}});}})}});}})();
</script>
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
            scripts="".join(f'<script src="/assets/js/{s}?v={self.ver}"></script>' for s in scripts))
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
        return f'<code>{esc(p["code"])}</code>'
    return '<span class="muted">—</span>'


def firm_row(f, cols):
    s = f["slug"]
    ccy = fac(f, "ccy", "USD")
    cells = {
        "firm": f'<th scope="row"><a href="/firms/{s}/">{esc(f["name"])}</a></th>',
        "market": f'<td>{esc(MARKET_LABEL.get(fac(f, "market"), "—"))}</td>',
        "price": f'<td class="n">{money(fac(f, "price50"), ccy)}{"<small>/mo</small>" if fac(f, "monthly") else ""}</td>',
        "target": f'<td class="n gain">{money(fac(f, "target50"), ccy)}</td>',
        "maxloss": f'<td class="n loss">{money(fac(f, "maxloss50"), ccy)}</td>',
        "dd": f'<td>{esc(DD_LABEL.get(fac(f, "dd"), "—"))}</td>',
        "cons": f'<td>{esc(cons_label(f))}</td>',
        "split": f'<td>{esc(fac(f, "split") or "—")}</td>',
        "payouts": f'<td>{esc(fac(f, "payouts") or "—")}</td>',
        "news": f'<td>{esc((fac(f, "news") or "—").capitalize())}</td>',
        "ea": f'<td>{yn(fac(f, "ea"), "Allowed", "Not allowed")}</td>',
        "us": f'<td>{yn(fac(f, "us"))}</td>',
        "tp": f'<td class="n">{fac(f, "tp") or "—"}</td>',
        "code": f'<td>{code_cell(f)}</td>',
    }
    attrs = (f'data-market="{fac(f, "market", "")}" data-dd="{fac(f, "dd", "")}" '
             f'data-cons="{"none" if cons_label(f) == "None" else "some"}" data-us="{1 if fac(f, "us") else 0}"')
    return f"<tr {attrs}>" + "".join(cells[c] for c in cols) + "</tr>"


COLS = {"firm": "Firm", "market": "Market", "price": "50K price", "target": "Profit target",
        "maxloss": "Max loss", "dd": "Drawdown", "cons": "Consistency rule", "split": "Profit split",
        "payouts": "Payouts", "news": "News trading", "ea": "Bots/EAs", "us": "US traders",
        "tp": "Trustpilot", "code": "Public code"}
NUMCOLS = {"price", "target", "maxloss", "tp"}


def firm_table(firms, cols, cls="cmp data"):
    head = "".join(f'<th scope="col"{" class=n" if c in NUMCOLS else ""}>{COLS[c]}</th>' for c in cols)
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


def filtered_table(firms, cols, tid):
    t = firm_table(firms, cols).replace("<table ", f'<table id="{tid}" ', 1)
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
        ("Profit target", lambda p: money(p.get("profit_target_50k"), p.get("price_50k_currency") or ccy)),
        ("Max loss", lambda p: money(p.get("max_loss_50k"), p.get("price_50k_currency") or ccy)),
        ("Drawdown type", lambda p: esc(p.get("drawdown_type") or "—")),
        ("Daily loss limit", lambda p: money(p.get("daily_loss_limit_50k"), p.get("price_50k_currency") or ccy) if p.get("daily_loss_limit_50k") not in (None, "") else "None"),
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
        ("Path to a live account", f.get("path_to_live")),
        ("Company", f.get("legal_entity_and_hq")),
        ("Founded", str(f["founded_year"]) if f.get("founded_year") else None),
    ]
    rows = "".join(f'<tr><th scope="row">{k}</th><td>{esc(str(v))}</td></tr>' for k, v in items if v not in (None, "", "—"))
    return f'<div class="tbl-wrap"><table class="kv"><tbody>{rows}</tbody></table></div>' if rows else ""


def strip_html(f):
    ccy = fac(f, "ccy", "USD")
    cells = [("50K price", money(fac(f, "price50"), ccy), "per month" if fac(f, "monthly") else "cheapest main plan", ""),
             ("Profit target", money(fac(f, "target50"), ccy), "on 50K", "gain"),
             ("Max loss", money(fac(f, "maxloss50"), ccy), DD_LABEL.get(fac(f, "dd"), "").lower(), "loss"),
             ("Consistency", cons_label(f), "rule applies to", ""),
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
                f'{esc(p.get("applies_to") or "")}<div class="seen">Published by {esc(f["name"])}, seen {fmt_date(seen)}. '
                f'Codes change often; the price at checkout is what counts.</div></div>'
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
    cta = (f'<div class="cta-col"><a class="btn" href="/go/{f["slug"]}/" rel="nofollow sponsored">Visit {esc(f["name"])}</a>'
           f'<p class="btn-note">Opens {esc(domain(f.get("link") or f.get("website")))}</p></div>')
    return f'<div class="firm-head"><div>{tag}<h1>{esc(h1)}</h1>{by}{sub}</div>{cta}</div>'


def firm_faq(f):
    n = f["name"]
    ed = f["_ed_meta"].get("faq") or []
    base = []
    p = main_program(f)
    ccy = fac(f, "ccy", "USD")
    if fac(f, "dd"):
        base.append([f"What drawdown does {n} use?",
                     f"{n}'s main 50K plan uses {DD_LABEL[fac(f, 'dd')].lower()} drawdown with a max loss of "
                     f"{strip_tags(money(fac(f, 'maxloss50'), ccy))}, as of {fmt_date(f['checked'])}."])
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
        title = ed.get("title", f"{n} Review ({month_year(mod)}): Rules, Prices, Payouts")
        desc = ed.get("description", f"{n} rules, 50K prices, drawdown, consistency and payout rules, checked {fmt_date(mod)} against {n}'s own pages.")
        verdict = f'<p class="lede">{ed["verdict"]}</p>' if ed.get("verdict") else ""
        promo_link = f'<p><a href="/firms/{s}/promo-code/">{n} promo code and current discount</a></p>'
        rules_link = f'<p><a href="/firms/{s}/rules/">Every {n} rule explained</a></p>' if ed.get("rules_page") else ""
        body = (firm_head(f, h1, verdict) + status_note(f) + strip_html(f) + dd_block(fac(f, "dd"))
                + f'<div class="content">{ticket_html(f)}' + (body_ed.split("<!--RULES-->")[0] if body_ed else "")
                + "</div>" + program_table(f)
                + f'<h2 id="rules">Trading rules and fine print</h2>{rules_kv(f)}{rules_link}'
                + pros_cons(f) + changes_html(f) + promo_link + sources_html(f) + faq_html(firm_faq(f)))
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
        desc = (f"The {n} discount {('code ' + p['code'] + ' ') if p.get('code') else ''}we found on {fmt_date(p.get('seen') or mod)}, "
                f"what it covers, and the real 50K price after fees.")
        pt = price_table(f)
        body = (firm_head(f, h1, "") + status_note(f) + ticket_html(f)
                + '<div class="content">' + promo_text(f) + "</div>" + pt
                + f'<div class="content"><h2>How to use a {esc(n)} code</h2><ol>'
                f'<li>Open <a href="/go/{s}/" rel="nofollow sponsored">{esc(domain(f.get("link") or f.get("website")))}</a> and pick the plan and account size.</li>'
                f'<li>At checkout, paste the code into the coupon or promo field and apply it before paying.</li>'
                f'<li>Check that the total dropped. If it did not, the code has expired or does not cover that plan.</li></ol>'
                f'<h2>What a discount does not change</h2><p>A code lowers the evaluation fee only. It does not change the profit target, '
                f'the max loss or the payout rules, and at most firms it does not cover activation or reset fees. '
                f'Most traders who buy an evaluation do not pass it, so the fee is best treated as money you can afford to lose. '
                f'<a href="/risks/">Read the risks</a>.</p>'
                f'<p><a href="/firms/{s}/">Full {esc(n)} review with every rule</a></p></div>' + sources_html(f))
        faq = [[f"Is there a {n} promo code right now?",
                (f"Yes. {n} published the code {p['code']} ({p.get('discount') or 'discount'}), seen on {fmt_date(p.get('seen') or mod)}." if p.get("code")
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
            title = f"{n} Rules Explained ({month_year(mod)}): Drawdown, Consistency, Payouts"
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
        disc = round(lp * (100 - pct) / 100, 2) if pct else None
        rows += (f'<tr><th scope="row">{esc(pr["name"])}</th><td class="n">{money(lp, ccy)}'
                 f'{" /mo" if pr.get("billing") == "monthly" else ""}</td>'
                 + (f'<td class="n">{money(disc, ccy, dec=True)}</td>' if pct else "")
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
        out.sort(key=lambda f: (fac(f, key) is None, fac(f, key) or 0))
    return out[: l.get("limit", 10)]


def build_lists(site, firms, lists):
    for l in lists:
        picks = pick_list(l, firms)
        path = f"/best/{l['slug']}/"
        trail = [("Best prop firms", "/best/"), (l["h1"], path)]
        mod = max([f["checked"] for f in picks] or [TODAY])
        items = ""
        for f in picks:
            why = (l.get("why") or {}).get(f["slug"]) or (f["_ed_meta"].get("one_liner") or f.get("best_for") or "")
            ccy = fac(f, "ccy", "USD")
            facts = (f"50K for {strip_tags(money(fac(f, 'price50'), ccy))}{'/mo' if fac(f, 'monthly') else ''}, "
                     f"target {strip_tags(money(fac(f, 'target50'), ccy))}, max loss {strip_tags(money(fac(f, 'maxloss50'), ccy))}, "
                     f"{DD_LABEL.get(fac(f, 'dd'), '').lower()} drawdown")
            items += (f'<li><div><h3><a href="/firms/{f["slug"]}/">{esc(f["name"])}</a></h3><p>{esc(why)}</p></div>'
                      f'<a class="btn ghost" href="/firms/{f["slug"]}/">Read review</a>'
                      f'<div class="facts">{esc(facts)}</div></li>')
        cols = l.get("cols", ["firm", "price", "target", "maxloss", "dd", "cons", "split", "payouts"])
        body = (f'<header class="art-head"><h1>{esc(l["h1"])}</h1><p class="byline">Updated {fmt_date(mod)}. '
                f'Facts checked against each firm\'s own pages. <a href="/methodology/">How we rank</a></p></header>'
                f'<div class="content"><p class="lede">{l["intro"]}</p></div>'
                f'<ol class="rank">{items}</ol><h2>Side by side</h2>{firm_table(picks, cols)}'
                f'<div class="content">{l.get("body", "")}</div>')
        faq = l.get("faq") or []
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

        def row(label, fn):
            return f'<tr><th scope="row">{label}</th><td>{fn(a)}</td><td>{fn(b)}</td></tr>'
        rows = "".join([
            row("Market", lambda f: esc(MARKET_LABEL.get(fac(f, "market"), "—"))),
            row("Cheapest main 50K plan", lambda f: money(fac(f, "price50"), fac(f, "ccy", "USD")) + (" /mo" if fac(f, "monthly") else "")),
            row("Profit target (50K)", lambda f: money(fac(f, "target50"), fac(f, "ccy", "USD"))),
            row("Max loss (50K)", lambda f: money(fac(f, "maxloss50"), fac(f, "ccy", "USD"))),
            row("Drawdown", lambda f: esc(DD_LABEL.get(fac(f, "dd"), "—"))),
            row("Consistency rule", lambda f: esc(cons_label(f))),
            row("Profit split", lambda f: esc(fac(f, "split") or "—")),
            row("Payouts", lambda f: esc(fac(f, "payouts") or "—")),
            row("News trading", lambda f: esc(f.get("news_trading") or "—")),
            row("Bots and EAs", lambda f: esc(f.get("ea_bots_allowed") or "—")),
            row("US traders", lambda f: yn(f.get("us_residents_accepted"))),
            row("Platforms", lambda f: esc(", ".join(f.get("platforms") or []) or "—")),
            row("Public code", lambda f: code_cell(f)),
        ])
        tbl = (f'<div class="tbl-wrap"><table class="kv data"><thead><tr><th scope="col"></th>'
               f'<th scope="col"><a href="/firms/{a["slug"]}/">{esc(a["name"])}</a></th>'
               f'<th scope="col"><a href="/firms/{b["slug"]}/">{esc(b["name"])}</a></th></tr></thead><tbody>{rows}</tbody></table></div>')
        desc = c.get("description", f"{a['name']} vs {b['name']}: 50K prices, drawdown, consistency rules and payouts side by side, checked {fmt_date(mod)}.")
        body = (f'<header class="art-head"><h1>{esc(h1)}</h1><p class="byline">Checked {fmt_date(mod)} against both firms\' own pages.</p></header>'
                f'<div class="content"><p class="lede">{c["verdict"]}</p></div>{tbl}<div class="content">{c.get("body", "")}</div>'
                f'<p><a class="btn" href="/go/{a["slug"]}/" rel="nofollow sponsored">Visit {esc(a["name"])}</a> '
                f'<a class="btn ghost" href="/go/{b["slug"]}/" rel="nofollow sponsored">Visit {esc(b["name"])}</a></p>')
        faq = c.get("faq") or []
        site.add(path, title=c.get("title", f"{h1} ({month_year(mod)}): Rules & Prices Compared"), description=desc,
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
        "{{HOME_TABLE}}": filtered_table(allf, ["firm", "market", "price", "target", "maxloss", "dd", "cons", "split", "payouts", "code"], "t-home"),
        "{{COMPARE_TABLE}}": filtered_table(allf, ["firm", "market", "price", "target", "maxloss", "dd", "cons", "split", "payouts", "news", "ea", "us", "tp", "code"], "t-all"),
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


def promo_table(allf):
    rows = ""
    for f in allf:
        p = f.get("current_public_promo") or {}
        rows += (f'<tr><th scope="row"><a href="/firms/{f["slug"]}/promo-code/">{esc(f["name"])}</a></th>'
                 f'<td>{code_cell(f)}</td><td>{esc(p.get("discount") or "No public discount found")}</td>'
                 f'<td class="n">{fmt_date(p.get("seen") or f["checked"])}</td></tr>')
    return (f'<div class="tbl-wrap"><table class="cmp data"><thead><tr><th scope="col">Firm</th><th scope="col">Code</th>'
            f'<th scope="col">Discount</th><th scope="col" class="n">Seen</th></tr></thead><tbody>{rows}</tbody></table></div>')


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
