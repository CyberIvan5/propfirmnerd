# Weekly fact check (propfirmnerd.com)

This site publishes prices, rules and discount codes for prop firms. They change often, and a wrong number
embarrasses the owner. Once a week a scheduled session runs this procedure. Accuracy over coverage:
**change a value only when the firm's own page clearly shows a different value. If anything is unclear,
leave it as is and report it.**

## Where the data lives
- `src/data/firms/<slug>.json`: one file per firm. This is the source of truth.
  - `facets`: the numbers used in tables (`price50`, `monthly`, `target50`, `maxloss50`, `dd`, `split`, ...).
  - `programs[]`: per-program 50K rules (price, activation fee, target, max loss, drawdown, consistency, payouts).
  - `current_public_promo`: `{code, discount, applies_to, source_url, seen}`. Only codes the firm itself publishes.
  - `checked`: ISO date of the last full verification. **Page titles show this month**, so only bump it after
    re-verifying the firm's core numbers.
  - `sources[]`, `recent_changes_2026[]`, `status`, `status_note`, `price_note`.
- `src/editorial/<slug>.html`: hand-written review text (META JSON header + body + optional `<!--RULES-->` rules page).
  It repeats some numbers, so update it when a number changes.
- `src/data/lists.json`, `src/data/compares.json`, `src/pages/*.html`: lists, comparisons and guides that may
  quote numbers too. Search them (`grep -rn '<old value>' src/`) after any change.
- Do NOT run `research/*.py` (local-only, not in the repo).

## Steps
1. For every firm in `src/data/firms/` (skip `"hidden": true`), open its own pricing page, rules/help pages
   and homepage banner (WebFetch; the URLs are in `sources[]` and `website`). Check:
   - 50K price of each program in `programs[]` (list price, before discounts) and activation fee;
   - profit target, max loss, drawdown type, daily loss limit, consistency rule, profit split, payout cadence;
   - the published discount code: is it still shown? did it change? Codes from coupon/affiliate sites do not count.
   - status: shut down, renamed, stopped selling, new restrictions.
2. Apply only confirmed changes:
   - update `programs[]`, the matching `facets`, and any number repeated in editorial, lists, compares and pages;
   - expired or removed code: set `code`/`discount`/`applies_to` to null (keep `seen` = today);
   - add a dated line to `recent_changes_2026` for real rule or price changes (`{"date": "YYYY-MM", "change": "...", "source": "url"}`);
   - set `checked` to today's date **only** for firms whose core numbers (price, target, max loss, drawdown)
     you actually confirmed today. If a firm's pages could not be read (blocked, 429), leave `checked` alone.
3. `python3 src/build.py`. It must finish without errors.
4. Commit with a message listing each change (`Weekly check YYYY-MM-DD: ...`) and push to `main`.
   Cloudflare Pages deploys automatically.
5. Report in Serbian, short: what changed (firm, old → new, source), which firms could not be verified and why,
   and anything that needs the owner (e.g. a firm closed, a code he should ask the firm about).

## Never
- Never invent or estimate a value, and never fill one from memory.
- Never add coupon-site codes or affiliate codes from third parties.
- Never change the design, templates or URLs during the weekly check.
