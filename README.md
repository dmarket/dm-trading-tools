# DM Trading Tools

Runnable examples of how to sign requests to the [DMarket Trading API](https://docs.dmarket.com/v1/swagger.html),
in **Go, JavaScript, PHP and Python**.

Every authenticated call to the Trading API carries an Ed25519 signature over a string you build from
the request itself. The four clients in [`signature-builder/`](signature-builder) each implement that in one small file, so
you can read the one in your language and copy it into your own bot.

```
signature-builder/
├── go/      dmarket_client.go   + main.go
├── js/      dmarketClient.js    + main.js
├── php/     DMarketClient.php   + main.php
└── python/  dmarket_client.py   + main.py
```

Each client exposes a single entry point — `call(method, path, payload)` — that signs the request, sets
the auth headers and returns the decoded JSON.

## Getting started

1. Generate an API key pair in your DMarket account settings ([details](https://dmarket.com/faq#tradingAPI)).
   You get a public key and a secret key, both hex strings.
2. Copy the env template and fill it in:

   ```bash
   cd signature-builder
   cp .env_example .env      # DMARKET_PUBLIC_KEY / DMARKET_SECRET_KEY
   ```

3. Run a sample — in Docker, no local toolchain needed:

   ```bash
   make run-go       # or run-js / run-php / run-python, or `make all`
   ```

   Or natively, from inside the language's folder:

   | Language | Setup | Run |
   |---|---|---|
   | Go | — | `go run .` |
   | JS | `npm i` | `npm start` |
   | PHP | `composer install` | `php main.php` |
   | Python | `pip3 install -r requirements.txt` | `python3 main.py` |

> **The samples talk to production.** `main.*` reads the first live offer off the market and then
> creates a real buy order (target) for it at `$2` (`price.amount` in `buildTargetBodyFromOffer`).
> Change that price, or delete step 4, before running any of them with real keys.

## How the signature works

A valid authenticated request needs three headers:

| Header | Value |
|---|---|
| `X-Api-Key` | your public key, lowercase hex |
| `X-Sign-Date` | unix timestamp in seconds — rejected if older than 2 minutes |
| `X-Request-Sign` | `dmar ed25519 <signature>` |

The signature is Ed25519 (NaCl `sign`) over

```
METHOD + path + ["?" + query string] + [body] + X-Sign-Date
```

hex-encoded (64 bytes → 128 characters). For example:

```
GET/trade-aggregator/v1/last-sales?gameId=a8db&title=AK-47%20%7C%20Redline%20%28Field-Tested%291605619994
```

### Percent-encoding: path and query are not treated alike

This is the one detail that costs people an afternoon. The API rebuilds the string it verifies from the
URL it received, using a **decoded** path and the query **exactly as transmitted**:

| URL part | What you sign | What you send |
|---|---|---|
| route path | the decoded, literal value | percent-encoded |
| query string | byte-for-byte what you send | the same bytes |

There is no canonical encoding to match for the query string — sign exactly the bytes your HTTP layer
will put on the wire. The four clients here differ and all four are correct: Go and JS write a space in
a query value as `+`, PHP and Python as `%20`.

So for a title in the path, sign the raw title and send the encoded URL:

```python
title = "AK-47 | Redline (Field-Tested)"                              # decoded
path  = f"/marketplace-api/v1/targets-by-title/a8db/{title}"           # sign this
# on the wire: /marketplace-api/v1/targets-by-title/a8db/AK-47%20%7C%20Redline%20%28Field-Tested%29
```

The clients here do the encoding for you — always hand them the decoded path. Query parameters are the
other way round: pass them as `payload` and the client encodes and signs them consistently. A `path`
that already contains a `?` is rejected outright.

Handing a client an already percent-encoded path does **not** fail loudly. It gets encoded a second
time, the API decodes it back to what you signed, the signature verifies — and then the API looks up a
title that literally contains `%20`, so you get a perfectly successful response about the wrong item.

One limitation: a `/` inside a free-text value is not supported. The clients encode segment by segment,
so the `/` stays a separator and the request lands on a different route.

Only endpoints that take a free-text value in the route path are affected — currently
`GET /marketplace-api/v1/targets-by-title/{game_id}/{title}`.

### Game ids

`gameId` values are `a8db` (CS2), `9a92` (Dota 2), `tf2` and `rust`.

## Verifying a change

`ci/verify_signing.py` checks every client the way the API does: it signs a request, sends it to a local
listener, then rebuilds the non-signed string from the URL that arrived and verifies the signature
against it. It needs no DMarket credentials and makes no calls to the live API — it generates a
throwaway keypair per run and redirects every client at the listener.

```bash
pip install pynacl requests
npm ci --prefix signature-builder/js                      # for the JS leg
composer install --working-dir signature-builder/php      # for the PHP leg
python ci/verify_signing.py
```

Set `DMTT_ONLY=go,python` to narrow it down, and `DMTT_REQUIRE=go,python` to fail instead of skip when a
toolchain is missing — CI requires all four. This runs in CI along with a build/lint job per language.

## Links

- API reference: <https://docs.dmarket.com/v1/swagger.html>
- API keys and rate limits: <https://dmarket.com/faq#startUsingTradingAPI>
