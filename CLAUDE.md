# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Public, runnable examples of **request signing for the DMarket Trading API**, implemented four times —
Go, JS, PHP, Python — under `signature-builder/<lang>/`. There is no library to publish and no product
code: the value is that all four read the same way, so an integrator can pick their language and copy.
Spec: <https://docs.dmarket.com/v1/swagger.html>.

Each language has the same two files: a `DMarketClient` (`dmarket_client.go`, `dmarketClient.js`,
`DMarketClient.php`, `dmarket_client.py`) exposing one `call(method, path, payload)` entry point, and a
`main.*` demo that uses it. The *signing* is line-for-line parallel; the surrounding idioms are not —
`call` returns `(result, error)` in Go, a `(response, error)` tuple in Python and a two-element array in
PHP, and returns a promise that rejects in JS. Errors are raised for programming mistakes (bad keys, a
`?` in `path`) and returned for transport and HTTP failures.

## Commands

Docker is the canonical way to run a sample — from `signature-builder/`, with a `.env` copied from
`.env_example` (needs `DMARKET_PUBLIC_KEY` / `DMARKET_SECRET_KEY`):

```bash
make all                 # build + run all four
make run-go              # or run-js / run-php / run-python
```

Note the Dockerfiles are written for build context `signature-builder/`, not the language directory.

Natively, from inside `signature-builder/<lang>/`:

```bash
go run .                            # NOT `go run main.go` — main.go alone does not compile,
                                    # it needs dmarket_client.go in the same package
npm i && npm start                  # js
composer install && php main.php    # php
pip3 install -r requirements.txt && python3 main.py   # python
```

There is no test suite and no linter config. CI (`.github/workflows/ci.yml`) runs `go build`/`go vet`,
`node --check`, `php -l`, `python -m compileall`, plus the check that actually matters:

```bash
pip install pynacl requests
npm ci --prefix signature-builder/js        # needed for the JS leg
composer install --working-dir signature-builder/php
python ci/verify_signing.py
```

`ci/verify_signing.py` env knobs: `DMTT_ONLY` (subset of `python,go,js,php`), `DMTT_REQUIRE` (those
languages must end up *verified*, not merely not-skipped — CI requires all four), `DMTT_PHP`,
`DMTT_CLIENT_HOST`. An unknown language in either aborts the run, and so does a run that verified
nothing.

## The signing contract

```
non-signed string = METHOD + path + ["?" + query] + [body] + X-Sign-Date
```

signed with Ed25519 (NaCl), hex-encoded, sent as three headers: `X-Api-Key`, `X-Sign-Date` (unix
seconds, rejected if older than 2 minutes), `X-Request-Sign: dmar ed25519 <hex>`.

**The asymmetry is the whole point of this repo, and it is not symmetric between the two URL halves:**

| URL part | Signed as | Sent as |
|---|---|---|
| route path | **decoded** (literal value) | percent-encoded |
| query string | byte-for-byte what is sent | same |

The query string has no canonical form to match — Go and JS write a space as `+`, PHP and Python as
`%20`, and all four are fine because each signs what it sends. The path does have one: the server
rebuilds the string from the URL it received using a *decoded* path, so a client that signs the encoded
path gets `401`. Hence `encodePath()` in every client: it percent-encodes **path segments only, for
transport**, while the signature is computed from the `path` argument as passed in. Callers always hand
the client a decoded path, query-free — `call` rejects a `path` containing `?`, because the helper can
no longer tell a query separator from a literal one. Do not "simplify" that split away — it is the fix
for SUPD-27468, and it only shows up on endpoints with a free-text path parameter (currently just
`GET /marketplace-api/v1/targets-by-title/{game_id}/{title}`).

The reverse mistake is quiet, not loud: pass an already-encoded path and it is encoded twice, the API
decodes it back to what was signed, the signature verifies, and the lookup runs against a title that
literally contains `%20`.

All four `encodePath()`s encode everything outside the RFC 3986 unreserved set (`A-Za-z0-9-._~`), so
they emit byte-identical paths. That is why Go uses `url.QueryEscape` with `+`→`%20` rather than
`url.PathEscape` (which leaves `& = + : @ $` raw), and why the JS one encodes `! ' ( ) *` on top of
`encodeURIComponent`. `ci/verify_signing.py` fails if the four ever drift apart.

Why it was invisible for half the clients: Go and Python re-encode the path in their HTTP layers, so
signing a decoded path happened to work. `https.request` in node writes `path` into the request line
verbatim and throws `ERR_UNESCAPED_CHARACTERS`; PHP's curl rejects the URL outright with `URL rejected:
Malformed input to a URL function`. Both were unable to call such an endpoint at all.

Also asymmetric by method: a `payload` becomes a query string for `GET` and a JSON body otherwise —
never both.

`call` rejects a `path` containing `?` in all four clients. `encodePath` would encode it correctly
(`%3F`), so this is a deliberate trade: an inline query string is the overwhelmingly likelier intent,
and encoding it would silently send a request with no query rather than fail. The cost is that a title
containing `?` cannot go through `call` — documented in README.md alongside the `/` limitation.

## Working in here

- **Change all four clients together.** They are deliberately parallel; a fix landing in one language
  and not the others is the failure mode this repo exists to prevent. The same goes for a new example
  in `main.*` and for a new leg in `ci/verify_signing.py`.
- `ci/verify_signing.py` deliberately mirrors the *server*: it rebuilds the non-signed string from the
  URL the listener received (decoded path + raw query) and verifies the signature against that. Keep it
  that way — asserting against a string the client itself produced would prove nothing.
- **The harness patches the client sources by string match** to point them at its listener: the base-URL
  literal in each client, plus `import https` / the import block / the request options. Renaming or
  reformatting those lines does not break silently — every patch and every skip is fail-closed, and a
  no-match aborts the run — but you do have to update the corresponding `patch(...)` call. Same for the
  request count: the harness asserts each client sends exactly the four cases in `CASES`.
- **`main.*` demos hit production and create a real buy order** (`exchange/v1/target/create`) with real
  keys. Do not run them casually to "check something"; use `ci/verify_signing.py`, which talks to a
  local listener with a throwaway keypair.
- The PHP sample needs the sodium functions. They are compiled into the `php:8.1-cli-alpine` base
  image, so the Docker build needs nothing extra; `php/php.ini` is *not* what provides them — the CLI
  SAPI never scans `/app` for an ini file, so that file has no effect. `composer.json` pulls in
  `paragonie/sodium_compat` as the polyfill for hosts whose PHP lacks the extension.
