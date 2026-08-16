# Contributing

Contributions are welcome. Two requirements, both mechanical:

## 1. DCO sign-off

Every commit in a pull request must carry a `Signed-off-by` line matching
its author (`git commit -s`). This is the [Developer Certificate of
Origin](https://developercertificate.org/): a one-line statement that you
have the right to submit the work under this repository's MIT license. A CI
check enforces it on every PR; unsigned commits are rejected mechanically,
not personally. (Maintainer commits pushed directly to main predate and are
outside this requirement.)

## 2. The evidence discipline

This repository's claims are regenerated, never asserted. A change is
mergeable when:

- the full test suite is green;
- every generated artifact (results, bundles, fixtures, comparison tables)
  is byte-identical when regenerated. The freshness gates in CI enforce
  this;
- any new gate or check comes with a test that feeds it corrupted input and
  proves it fires. A gate without a liveness test is untested code.

If your change makes a published number wrong, the fix is to regenerate the
number, never to edit it.
