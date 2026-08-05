# Raw data behind the State of the MCP Registry page

Every figure on the page comes from these files. They are published so the arithmetic can
be re-walked by someone who does not trust it, which is the only version of "carefully
measured" that is worth anything.

| file | what it is |
|---|---|
| `census-2026-07-30.json` | Full-registry sweep, 2026-07-30. All 10,716 active-latest remote URLs, each with a health class and HTTP status. This is the baseline every later comparison is anchored to. |
| `successor-probe-20260803.json` | The successor probe, 2026-08-03. For every 7/30 URL that was no longer the active-latest entry on 8/2, both the old endpoint and its current successor probed in the same run. Contains the resolved pairs, the full 2×2, the four contract-continuity rows, and the raw probe result for all 1,217 URLs. |
| `AGE-VS-DEATH-20260805.json` | Listing age vs endpoint death, 2026-08-05. Joins a full registry walk (661 pages, 66,045 version records, `publishedAt` per version) to the 7/30 census, deduped to server name, one hosting platform per server, n=1,092. Holds the per-platform age buckets, Cochran-Armitage trend tests, and the Mantel-Haenszel odds ratios for both clocks (listing age and staleness). Built to answer a reader's question in the hosting-durability thread. |
| `age_walk.py` / `age_vs_death.py` | The two scripts that produce the row above. `age_walk.py` does the unfiltered registry walk; `age_vs_death.py` does the join, the dedupe, and the statistics (hand-rolled, no scipy — self-tests in the docstring notes). |
| `age_vs_death_selftest.py` | Self-tests for the hand-rolled statistics in `age_vs_death.py` (no scipy on the machine that runs this). Six cases with known answers: a flat series, a rising and its mirror, a Mantel-Haenszel table built to a known common OR of 4, a perfect null, and a synthetic Simpson's-paradox case where the within-stratum effect is exactly zero and the pooled test still returns z=7.76. `python3 age_vs_death_selftest.py` exits non-zero on any failure. |

## Method, in one paragraph

Endpoints are probed anonymously over HTTP with an MCP `initialize` handshake
(protocolVersion `2025-06-18`) followed by `tools/list`. A server counts as answering only
if `tools/list` returns a result. Servers requiring credentials return 401 and are counted
as not answering — the right reading for "can a caller use this", the wrong one for "does
this server exist"; both are recoverable from the per-URL error codes in the files.

## Known limits

- Anonymous probes only. Auth-gated servers are indistinguishable from broken ones.
- The age analysis joins an 8/05 registry walk to a 7/30 census, so a listing deleted between those dates drops out (3 of 10,716 did not match). Deletions skew toward dead listings, which biases the measured age effect toward the null.
- Listing age is the MINIMUM `publishedAt` across every version record of a server name. Using the newest record instead understates age by a median of 28 days for the 31% of servers that were republished, and inflates the apparent age effect.
- Single observation window per run. A 503 may be a deploy, not a death.
- Successor resolution uses the registry's `name` field, which is self-declared by the
  operator whose endpoint moved. Contract continuity — the stronger witness — could only be
  checked for 4 pairs, and is reported as individual rows rather than a rate.

Source for the probe scripts: the `mcp-uptime` project. Questions and corrections:
[@theopslog on dev.to](https://dev.to/theopslog).
