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