# CI Coverage Policy

Sparkbot requires at least 90% coverage on new and changed executable Python
lines. Total backend coverage remains visible and may not meaningfully regress.

The previous CI configuration required 90% total project coverage even though
the verified `main` baseline was 51.2450% (10,537 covered lines out of 20,562
statements) at commit `9ebedb23548d16fd085e5d959d5c82fa0148a9ae`.
That gate could not be satisfied by a pull request that preserved or improved
the repository baseline.

The coverage gate now applies two checks:

1. Coverage.py reports executable lines, and the gate intersects those lines
   with added Python lines from the Git diff. At least 90% must be covered.
   Deleted lines, comments, blank lines, tests, and non-production paths do not
   enter the patch denominator. Missing or malformed coverage data fails closed.
2. Total coverage must remain at or above the recorded baseline. A tolerance of
   0.02 percentage points accounts for the observed three-line variation in the
   otherwise identical test suite; larger regressions fail.

Smokeshow continues to publish total coverage. The machine-readable policy and
baseline live in `ci/coverage-policy.json`. When `main` coverage improves, a
reviewed CI-policy change must update the covered-line count, statement count,
and base SHA together. The baseline is technical debt, not the quality target;
the long-term target remains at least 90% total project coverage.

Broad exclusions of handwritten production code are prohibited. Coverage
improvements must come from meaningful tests or justified executable-code
changes.
