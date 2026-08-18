# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Public, runnable examples of **request signing for the DMarket Trading API**, implemented four times —
Go, JS, PHP, Python — under `signature-builder/<lang>/`. There is no library to publish and no product
code: the value is that all four read the same way, so an integrator can pick their language and copy.
Spec: <https://docs.dmarket.com/v1/swagger.html>.

Each language has the same two files: a `DMarketClient` (`dmarket_client.go`, `dmarketClient.js`,
`DMarketClient.php`, `dmarket_client.py`) exposing one `call(method, path, payload)` entry point, and a
`main.*` demo that uses it.

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

`ci/verify_signing.py` env knobs: `DMTT_ONLY` (subset of `python,go,js,php`), `DMTT_REQUIRE` (fail
instead of skip when a toolchain is missing — CI requires all four), `DMTT_PHP`, `DMTT_CLIENT_HOST`.

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
| query string | percent-encoded, byte-for-byte what is sent | same |

The server rebuilds the string from the URL it received using a decoded path and a raw query, so a
client that signs an encoded path gets `401`. Hence `encodePath()` in every client: it percent-encodes
**path segments only, for transport**, while the signature is still computed from the `path` argument as
passed in. Callers always hand the client a decoded path. Do not "simplify" that split away — it is the
fix for SUPD-27468, and it only shows up on endpoints with a free-text path parameter (currently just
`GET /marketplace-api/v1/targets-by-title/{game_id}/{title}`).

Why it was invisible for half the clients: Go and Python re-encode the path in their HTTP layers, so
signing a decoded path happened to work. `https.request` in node writes `path` into the request line
verbatim and throws `ERR_UNESCAPED_CHARACTERS`; PHP's curl rejects the URL outright with `URL rejected:
Malformed input to a URL function`. Both were unable to call such an endpoint at all.

Also asymmetric by method: a `payload` becomes a query string for `GET` and a JSON body otherwise —
never both.

## Working in here

- **Change all four clients together.** They are deliberately parallel; a fix landing in one language
  and not the others is the failure mode this repo exists to prevent. The same goes for a new example
  in `main.*` and for a new leg in `ci/verify_signing.py`.
- `ci/verify_signing.py` deliberately mirrors the *server*: it rebuilds the non-signed string from the
  URL the listener received (decoded path + raw query) and verifies the signature against that. Keep it
  that way — asserting against a string the client itself produced would prove nothing.
- **`main.*` demos hit production and create a real buy order** (`exchange/v1/target/create`) with real
  keys. Do not run them casually to "check something"; use `ci/verify_signing.py`, which talks to a
  local listener with a throwaway keypair.
- The PHP sample needs the sodium functions: `php/php.ini` enables the built-in extension for the
  Docker image, and `composer.json` pulls in `paragonie/sodium_compat` as the polyfill for hosts
  without it.
