#!/usr/bin/env python3
"""Self-tests for the hand-rolled statistics in age_vs_death.py.

There is no scipy or numpy on the machine that runs this, so the Cochran-Armitage trend
test and the Mantel-Haenszel stratified odds ratio are implemented by hand. Hand-rolled
statistics that have never been run against a known answer are just arithmetic with a
confident name on it.

These six cases were run before the estimator was ever pointed at real data. They existed
only in a shell session until 2026-08-05, when publish-verifier correctly blocked an article
for claiming "those tests are in the repo" while no such file existed. A test that lives in
a terminal you already closed is not a test, and citing it publicly is worse than not having
one. So it lives here now, and it is published alongside the analysis it guards.

    python3 age_vs_death_selftest.py        # exits non-zero on any failure

Case 6 is the load-bearing one. It is the reason the published result is stratified by
platform rather than pooled: it constructs data where the within-platform age effect is
EXACTLY zero in both strata, and shows that the pooled test still reports z=7.76. That is
Simpson's paradox, generated deliberately so the shape is recognisable when it turns up in
real data — which it did, at z=14.66 pooled against OR 2.60 stratified.
"""
import importlib.util
import math
import pathlib
import sys

spec = importlib.util.spec_from_file_location('avd', pathlib.Path(__file__).parent / 'age_vs_death.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

FAILURES = []


def check(label, got, want, tol=0.01):
    ok = got is not None and want is not None and abs(got - want) <= tol
    print(f'  {"PASS" if ok else "FAIL"}  {label:52} got={got!r:>12}  want~{want}')
    if not ok:
        FAILURES.append(label)


print('Cochran-Armitage trend test')

# 1. No trend whatsoever: identical rate in every bucket -> z must be 0.
z, p = m.cochran_armitage([(i, 100, 20) for i in range(4)])
check('1. flat series -> z = 0', z, 0.0)
check('1. flat series -> p = 1', p, 1.0)

# 2. Strong monotone rise. Value pinned so a future refactor that changes the scoring,
#    the variance term, or the score vector cannot pass silently.
z, p = m.cochran_armitage([(0, 100, 5), (1, 100, 20), (2, 100, 40), (3, 100, 60)])
check('2. rising series -> z = 8.925', z, 8.925)

# 3. The mirror image must give the same magnitude with the opposite sign. Catches a
#    dropped sign or an abs() that would make the test blind to direction.
z, p = m.cochran_armitage([(0, 100, 60), (1, 100, 40), (2, 100, 20), (3, 100, 5)])
check('3. falling series -> z = -8.925', z, -8.925)

print('\nMantel-Haenszel stratified odds ratio')

# 4. Two strata built to a known common OR of ~4, with deliberately opposite base rates
#    so a naive pooled OR would NOT land on 4. Stratum A: (40*86)/(60*14) = 4.10.
#    Stratum B: (80*50)/(20*50) = 4.00.
orv, chi, p = m.mantel_haenszel([(40, 60, 14, 86), (80, 20, 50, 50)])
check('4. known common OR ~4 -> OR = 4.04', orv, 4.04)

# 5. Perfect null in both strata. OR must be exactly 1 and p must not be significant.
orv, chi, p = m.mantel_haenszel([(25, 25, 25, 25), (40, 40, 40, 40)])
check('5. null strata -> OR = 1.00', orv, 1.00)
check('5. null strata -> p not significant', 1.0 if p > 0.05 else 0.0, 1.0)

print('\nSimpson\'s paradox guard — the reason the published result is stratified')

# 6. Within each platform the dead rate is CONSTANT across age (80% in A, 10% in B), so
#    the true within-platform age effect is zero. But the old buckets are concentrated in
#    the deadly platform and the young ones in the healthy platform. Pooling therefore
#    manufactures a large age trend out of nothing but platform mix.
A = [(0, 10, 8), (1, 20, 16), (2, 40, 32), (3, 80, 64)]     # 80% dead at every age
B = [(0, 80, 8), (1, 40, 4), (2, 20, 2), (3, 10, 1)]        # 10% dead at every age
za, _ = m.cochran_armitage(A)
zb, _ = m.cochran_armitage(B)
check('6. within platform A -> z = 0', za, 0.0)
check('6. within platform B -> z = 0', zb, 0.0)

pooled = [(i, a[1] + b[1], a[2] + b[2]) for i, (a, b) in enumerate(zip(A, B))]
zp, pp = m.cochran_armitage(pooled)
check('6. POOLED -> z = 7.76 (spurious)', zp, 7.758)

print(f'\n{"ALL PASS" if not FAILURES else "FAILURES: " + ", ".join(FAILURES)}')
sys.exit(1 if FAILURES else 0)
