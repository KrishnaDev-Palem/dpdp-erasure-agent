# Git history scan — secrets and PII

Retroactive hygiene per `briefs/stratified-case-generation.md` §10. This record covers **all refs**, not only `HEAD`.

| Field | Value |
| ----- | ----- |
| **Date** | 2026-07-29 |
| **Tool / method** | PowerShell script over `git rev-list --all`; `git grep -I -E` per pattern across all commit objects |
| **Refs covered** | All local and remote-tracking refs at scan time: `refs/heads/*` (main, docs/stratified-public-framing, docs/stratified-case-generation-brief, docs/stratified-design-space, docs/stratified-supersede-adr-0002), `refs/remotes/origin/*` (main, ci/actions-tests, docs/stratified-case-generation-brief) |
| **Commits scanned** | 24 |
| **Result** | **Clean** — no actionable findings |

## Patterns checked

- AWS access key prefix (`AKIA…`)
- PEM private key headers (`-----BEGIN … PRIVATE KEY-----`)
- Assignment-style secrets (`password=`, `api_key=`, `secret=`, `token=`, etc.)
- Common token prefixes (`aws_secret_access_key`, OpenAI `sk-…`, GitHub `ghp_…`, Slack `xox…`)
- Email addresses outside known synthetic/example domains

## Exclusions (known benign fixtures)

Matches in local dev connection strings (`postgresql://postgres:postgres@localhost`), synthetic fixture paths, and test-spec examples were excluded from the findings list when they matched only those contexts.

## Findings

None. No remediation required from this scan.

If a future scan finds secrets or PII in history, treat remediation (history rewrite, secret rotation, or a clean tree) as a separate deliberate action — do not ignore because the repository is already public.
