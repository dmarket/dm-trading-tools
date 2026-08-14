# Signature Builder
For comfortable Trading API usage traders may use API keys and signed requests.
Here you can find the examples of request signature in several programming languages.
API doc details: https://docs.dmarket.com/v1/swagger.html.

The *signature-builder* folder show the examples of a basic lightweight client for DMarket trading API usage. 
It offers you a bot that:
- gets the first offer from the market with an API request (public GET exchange/v1/market/items request)
- builds a body for a target from the found offer with a low price to make you profits after target closing
- builds the signature for the target creation using API keys (https://docs.dmarket.com/v1/swagger.html for doc about API keys generation)
- creates a target using the body of the target and signature with an API request (POST exchange/v1/target/create)

You may use the examples to extend the logic for all the trading operations on the DMarket.
## Signing a request path vs. query string

The non-signed string is `(HTTP method) + (route path + query string) + (body) + (timestamp)`, and
the two URL parts are treated differently:

- **route path** — signed **decoded**, i.e. with the literal value
  (`/marketplace-api/v1/targets-by-title/a8db/AK-47 | Redline (Field-Tested)`);
- **query string** — signed **exactly as transmitted**, i.e. percent-encoded
  (`?gameId=a8db&title=AK-47%20%7C%20Redline%20%28Field-Tested%29`).

The URL that goes over the wire is percent-encoded in both cases — the clients here do that for
you, so always hand them the decoded path. Signing an already-encoded path returns
`401 Unauthorized`.

This only matters for methods that take a free-text value in the route path, currently
`GET /marketplace-api/v1/targets-by-title/{game_id}/{title}`.
