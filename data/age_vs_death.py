#!/usr/bin/env python3
"""Does registry-listing AGE predict endpoint death, INSIDE a single hosting platform?

Asked by @valentin_monteiro on dev.to, 2026-08-05, against the hosting-durability table
(railway 66% failing, vercel 8%). His argument: platform is already a good enough prior to
order a revalidation queue instead of sweeping all ~10.7k evenly, and if failure rate also
climbs with age WITHIN a platform, age is a second free input — and it separates the
platform effect from which platforms happened to be popular two years ago.

Three things decide whether this answer is honest, and each one is a correction of a
mistake this project has already made once:

1. UNIT OF ANALYSIS. Dedupe to server NAME, never URL. One vendor with 97 dataset subpaths
   inflated a published headline ~2x on 8/4. Every rate here is per server name.

2. WHAT publishedAt ACTUALLY MEANS. `_meta[...]/official.publishedAt` is the publish time
   of THAT VERSION RECORD, not of the server's first listing. A server that republished
   last week reads as new while having been listed a year. Age is therefore the MINIMUM
   publishedAt over every version record of a name, which needs the unfiltered walk.

3. THE DEFINITION OF DEAD must match the published table Valentin is citing, or the answer
   is not comparable to the thing he asked about. That table used
   failing = 404 / DNS / timeout / conn / 5xx, with auth-gated counting as ALIVE.

Survivorship caveat, stated rather than buried: the census is 2026-07-30 and the age walk
is 2026-08-05. A listing present on 7/30 and DELETED since cannot be joined and drops out.
Deletions skew toward dead listings, so this drops dead-and-old rows preferentially and
biases the age effect TOWARD the null. A positive finding here survives that bias; a null
one is partly explained by it.
"""
import json, math, datetime, collections, pathlib

D = pathlib.Path(__file__).parent
PROBE_DATE = datetime.datetime(2026, 7, 30, tzinfo=datetime.timezone.utc)

# Matches HOSTING-DURABILITY-20260730.md exactly. auth_required is ALIVE: the address works,
# it just wants a key. Redirects/429/402/405/odd are neither clean life nor clean death and
# are EXCLUDED from the denominator rather than silently assigned.
DEAD = {'not_found', 'dns_fail', 'conn_fail', 'tls_fail', 'timeout', 'server_error'}
ALIVE = {'up', 'auth_required'}

PLATFORMS = [
    ('trycloudflare.com', 'trycloudflare'), ('ngrok', 'ngrok'),
    ('smithery.ai', 'smithery'), ('railway.app', 'railway'),
    ('onrender.com', 'onrender'), ('fly.dev', 'fly.dev'),
    ('workers.dev', 'workers.dev'), ('vercel.app', 'vercel'),
    ('herokuapp.com', 'heroku'), ('replit', 'replit'),
]


def platform_of(url):
    h = url.split('//')[-1].split('/')[0].split(':')[0].lower()
    for needle, label in PLATFORMS:
        if needle in h:
            return label
    return None


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None


def cochran_armitage(rows):
    """Trend test across ordered age buckets. rows = [(score, n, dead)]."""
    N = sum(r[1] for r in rows)
    X = sum(r[2] for r in rows)
    if N == 0 or X == 0 or X == N:
        return None, None
    p = X / N
    T = sum(t * (x - n * p) for t, n, x in rows)
    v = p * (1 - p) * (sum(n * t * t for t, n, _ in rows)
                       - sum(n * t for t, n, _ in rows) ** 2 / N)
    if v <= 0:
        return None, None
    z = T / math.sqrt(v)
    pv = math.erfc(abs(z) / math.sqrt(2))
    return z, pv


def mantel_haenszel(strata):
    """strata = [(a,b,c,d)] : a=old&dead b=old&alive c=new&dead d=new&alive."""
    num = den = 0.0
    sa = se = sv = 0.0
    for a, b, c, d in strata:
        n = a + b + c + d
        if n == 0:
            continue
        num += a * d / n
        den += b * c / n
        sa += a
        se += (a + b) * (a + c) / n
        denom = n * n * (n - 1)
        if denom > 0:
            sv += (a + b) * (c + d) * (a + c) * (b + d) / denom
    if den == 0 or sv <= 0:
        return None, None, None
    orv = num / den
    chi = (abs(sa - se) - 0.5) ** 2 / sv
    pv = math.erfc(math.sqrt(chi / 2))
    return orv, chi, pv


def main():
    age = json.load(open(D / 'registry-age-20260805.json'))
    recs = age['records']
    census = json.load(open(D / 'census-2026-07-30.json'))['results']

    # Two different clocks, deliberately kept apart:
    #   first[] = earliest version record  -> LISTING AGE, "how long has this been listed"
    #   last[]  = latest version record    -> STALENESS,   "how long since anyone touched it"
    # They are not the same question and they do not give the same answer. 39% of servers
    # have more than one version record, and for those the latest record understates true
    # listing age by a median of 15 days (max 279).
    first, last = {}, {}
    for r in recs:
        nm, ts = r.get('name'), parse_ts(r.get('publishedAt'))
        if not nm or not ts:
            continue
        if nm not in first or ts < first[nm]:
            first[nm] = ts
        if nm not in last or ts > last[nm]:
            last[nm] = ts

    # url -> name, taking any version record that advertises it
    url2name = {}
    for r in recs:
        for u in r.get('urls') or []:
            url2name.setdefault(u, r.get('name'))

    cls = {c['url']: c['class'] for c in census}

    # collapse to one row per server name: dead only if EVERY probed url of that name is dead
    per = collections.defaultdict(lambda: {'dead': 0, 'alive': 0, 'plat': set()})
    unmatched = 0
    for url, k in cls.items():
        nm = url2name.get(url)
        if not nm:
            unmatched += 1
            continue
        if k in DEAD:
            per[nm]['dead'] += 1
        elif k in ALIVE:
            per[nm]['alive'] += 1
        else:
            continue
        p = platform_of(url)
        if p:
            per[nm]['plat'].add(p)

    rows = []
    for nm, v in per.items():
        if v['dead'] + v['alive'] == 0 or len(v['plat']) != 1:
            continue
        f = first.get(nm)
        if not f:
            continue
        days = (PROBE_DATE - f).days
        if days < 0:
            continue
        rows.append({'name': nm, 'plat': next(iter(v['plat'])),
                     'dead': 1 if v['alive'] == 0 else 0, 'age': days,
                     'stale': (PROBE_DATE - last[nm]).days})

    print(f'census urls: {len(cls)}   unmatched to a registry name: {unmatched}')
    print(f'server names with age + single platform + clean verdict: {len(rows)}\n')

    out = {'generated': '2026-08-05', 'probe_date': '2026-07-30',
           'n_servers': len(rows), 'unmatched_urls': unmatched, 'platforms': {}}

    # age buckets, fixed edges so every platform uses the same scale
    EDGES = [(0, 30), (30, 90), (90, 180), (180, 10000)]
    LBL = ['0-30d', '30-90d', '90-180d', '180d+']

    def bucket(a):
        for i, (lo, hi) in enumerate(EDGES):
            if lo <= a < hi:
                return i
        return len(EDGES) - 1

    byplat = collections.defaultdict(list)
    for r in rows:
        byplat[r['plat']].append(r)

    print(f"{'platform':<16}{'n':>5}{'dead%':>7}   " + '  '.join(f'{l:>12}' for l in LBL) + '   trend z    p')
    for plat, rs in sorted(byplat.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < 25:
            continue
        cells, ca = [], []
        for i in range(len(EDGES)):
            sub = [r for r in rs if bucket(r['age']) == i]
            d = sum(r['dead'] for r in sub)
            cells.append((len(sub), d))
            if sub:
                ca.append((i, len(sub), d))
        z, pv = cochran_armitage(ca)
        tot = len(rs)
        totd = sum(r['dead'] for r in rs)
        cellstr = '  '.join(
            (f'{d}/{n} {100*d/n:4.0f}%' if n else f'{"—":>12}').rjust(12)
            for n, d in cells)
        zs = f'{z:8.2f} {pv:6.3f}' if z is not None else f'{"n/a":>8} {"":>6}'
        print(f'{plat:<16}{tot:>5}{100*totd/tot:6.0f}%   {cellstr}   {zs}')
        out['platforms'][plat] = {
            'n': tot, 'dead': totd,
            'buckets': [{'label': LBL[i], 'n': cells[i][0], 'dead': cells[i][1]}
                        for i in range(len(cells))],
            'trend_z': z, 'trend_p': pv}

    # stratified: is the clock predictive AFTER holding platform fixed? Run BOTH clocks.
    out['mh'] = {}
    print('\nMantel-Haenszel, stratified by platform (holds the platform effect fixed)')
    for key, label in (('age', 'listing age  (first publish -> probe)'),
                       ('stale', 'staleness    (last publish  -> probe)')):
        med = sorted(r[key] for r in rows)[len(rows) // 2]
        strata = []
        for plat, rs in byplat.items():
            if len(rs) < 25:
                continue
            strata.append((
                sum(1 for r in rs if r[key] >= med and r['dead']),
                sum(1 for r in rs if r[key] >= med and not r['dead']),
                sum(1 for r in rs if r[key] < med and r['dead']),
                sum(1 for r in rs if r[key] < med and not r['dead'])))
        orv, chi, pv = mantel_haenszel(strata)
        if orv:
            print(f'  {label:38} split at {med:4}d   OR = {orv:.2f}   p = {pv:.3g}   '
                  f'({len(strata)} strata)')
        out['mh'][key] = {'median_days': med, 'or': orv, 'chi2': chi, 'p': pv,
                          'n_strata': len(strata)}

    # How much does the min-vs-latest distinction actually matter?
    multi = [r for r in rows if r['age'] != r['stale']]
    if multi:
        gaps = sorted(r['age'] - r['stale'] for r in multi)
        # Day-level gap, so same-day republishes are excluded by construction. Counting
        # version RECORDS instead gives 428/1092 (39%); the extra 86 republished within a
        # day of first listing and so move neither clock. Both numbers are true of
        # different things — this one is "servers where the two clocks disagree".
        print(f'\n  {len(multi)} of {len(rows)} servers ({100*len(multi)/len(rows):.0f}%) were '
              f'republished at least a day after first listing (so the two clocks differ).')
        print(f'  For those, using the LATEST record understates listing age by a median of '
              f'{gaps[len(gaps)//2]}d (max {gaps[-1]}d).')
        out['republished'] = {'n': len(multi), 'share': len(multi)/len(rows),
                              'median_understate_days': gaps[len(gaps)//2],
                              'max_understate_days': gaps[-1]}

    # unstratified, for the contrast that shows how much is platform confounding
    ca_all = []
    for i in range(len(EDGES)):
        sub = [r for r in rows if bucket(r['age']) == i]
        if sub:
            ca_all.append((i, len(sub), sum(r['dead'] for r in sub)))
    z, p_all = cochran_armitage(ca_all)
    print(f'\nPooled across all platforms (CONFOUNDED, shown for contrast):')
    for i, n, d in ca_all:
        print(f'  {LBL[i]:>9}  {d:5}/{n:<5} {100*d/n:5.1f}%')
    if z is not None:
        print(f'  trend z = {z:.2f}  p = {p_all:.4g}')
    out['pooled'] = {'buckets': [{'label': LBL[i], 'n': n, 'dead': d}
                                 for i, n, d in ca_all], 'trend_z': z, 'trend_p': p_all}

    json.dump(out, open(D / 'AGE-VS-DEATH-20260805.json', 'w'), indent=1)
    print('\nwrote AGE-VS-DEATH-20260805.json')


if __name__ == '__main__':
    main()
