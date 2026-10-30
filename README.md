# AdmitCheck

A GenLayer app that turns official programme pages into a quote-backed admission card, then checks your declared facts against it.

Programme pages bury the facts that decide an application: minimum degree, GPA floor and its scale, accepted English test and score, deadline, application fee. People read them differently every time, and the page changes between intakes without anyone noticing.

## What it does

| Method | Type | Purpose |
|---|---|---|
| `index_program(urls)` | write | Read 1 to 3 official pages, store a requirement card with verbatim quotes |
| `refresh_program(id)` | write | Re-read the pages, bump version only if a gate value moved |
| `evaluate(id, applicant_json)` | view | Deterministic check of your declared facts against the card |
| `get_program(id)` | view | Full card plus canonical gate values |
| `find_program(url)` | view | Look up a card by its first URL |
| `list_programs()` | view | The indexed cards |
| `count()` | view | Number of cards |

## Where GenLayer is actually needed

Reading prose into structured fields is judgment, so `index_program` uses a custom leader/validator pair (`gl.vm.run_nondet_unsafe`):

- Leader: fetches up to three pages, extracts a fixed card, and refuses to continue if fewer than two facets carry a verbatim quote or if both the degree and the English test come back unknown.
- Validator: fetches its own copies, checks that the leader's quotes appear in them verbatim, runs its own extraction, and requires every gate field to agree after canonicalization.

Everything after that is plain arithmetic. `evaluate` is a view: no model call, no transaction, no fee. Numeric fields are stored and compared as canonical strings, never as floats.

## Why the numbers are strings

Floats are not safe in calldata. Every numeric field is parsed, rounded to four decimals and stored as a canonical decimal string, and consensus compares those strings by exact equality. A decimal comma such as `3,0` is accepted and normalized.

## Evaluate output

The result carries one row per facet with `PASS`, `FAIL` or `UNKNOWN`, plus a verdict:

- `ELIGIBLE`: every facet passed.
- `NOT_ELIGIBLE`: at least one facet failed, or the deadline has passed.
- `NEEDS_REVIEW`: nothing failed but something could not be decided from the page or from your input.

`window` reports `OPEN`, `CLOSED` or `UNKNOWN` for the deadline.

## Honest limits

- Applicant facts are self-declared. Nothing verifies transcripts or test scores.
- A field the page does not state is stored as unknown, never guessed.
- Pages behind a login wall, heavy JavaScript rendering or bot filters will fail to ground. Sites that render text server side, such as university programme pages, work; client-rendered sites may not.
- The card reflects one read of the page. Use `refresh_program` to keep it current; it returns `UNCHANGED`, `CHANGED` or `FETCH_FAILED`.
- GPA is compared on the requirement's own scale with a small tolerance, so a different scale does not create a false failure.

## Tests

    pip install -r requirements.txt
    python -m pytest tests/direct -q
    genvm-lint check contracts/admitcheck.py

23 direct-mode tests cover indexing, duplicate reuse, paraphrased quote rejection, unreadable source, validator disagreement on deadline, validator rejection of an ungrounded quote, each evaluate facet, scale mismatch, deadline closing, refresh unchanged, refresh changed, refresh failure and decimal comma parsing.

## Scope

Contract and tests only. There is no frontend in this repository.
