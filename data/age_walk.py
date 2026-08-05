#!/usr/bin/env python3
"""Walk the whole registry keeping publishedAt per version, so listing AGE is derivable.

Asked by @valentin_monteiro (dev.to, 2026-08-05): does failure rate climb with listing age
INSIDE a single platform? If so, age is a second free input to a revalidation queue, and it
separates the platform effect from which platforms happened to be popular two years ago.

The subtlety that decides whether this measurement is honest:
`_meta[...]/official.publishedAt` is the publish time of THAT VERSION RECORD, not of the
server's first appearance. A server that republished last week shows a recent publishedAt
while having been listed for a year. So age must be computed per SERVER NAME as the MINIMUM
publishedAt across every version record, which requires the unfiltered walk (isLatest false
records included), not the active-latest filter the earlier scripts kept.
"""
import json, sys, urllib.parse, urllib.request, datetime, time

UA = 'mcp-uptime/0.3 (+https://mcp-uptime.theopslog.workers.dev)'
DATE = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime('%Y%m%d')

recs, cursor, pages = [], None, 0
while True:
    q = 'https://registry.modelcontextprotocol.io/v0/servers?limit=100'
    if cursor:
        q += '&cursor=' + urllib.parse.quote(cursor)
    for attempt in range(3):
        try:
            d = json.loads(urllib.request.urlopen(
                urllib.request.Request(q, headers={'User-Agent': UA}), timeout=45).read())
            break
        except Exception as e:
            if attempt == 2:
                print(f'page {pages+1} failed after 3 tries: {type(e).__name__} — INCOMPLETE', flush=True)
                d = None
            else:
                time.sleep(2 * (attempt + 1))
    if d is None:
        break
    pages += 1
    for s in d.get('servers', []):
        srv = s.get('server') or {}
        m = (s.get('_meta') or {}).get('io.modelcontextprotocol.registry/official') or {}
        recs.append({
            'name': srv.get('name'),
            'version': srv.get('version'),
            'publishedAt': m.get('publishedAt'),
            'updatedAt': m.get('updatedAt'),
            'status': m.get('status'),
            'isLatest': m.get('isLatest'),
            'urls': [r.get('url') for r in (srv.get('remotes') or []) if r.get('url')],
        })
    if pages % 50 == 0:
        print(f'{pages} pages, {len(recs)} records', flush=True)
    cursor = (d.get('metadata') or {}).get('nextCursor')
    if not cursor:
        break

out = f'registry-age-{DATE}.json'
json.dump({'date': DATE, 'pages': pages, 'n_records': len(recs), 'records': recs},
          open(out, 'w'))
print(f'{pages} pages -> {len(recs)} version records -> {out}')
