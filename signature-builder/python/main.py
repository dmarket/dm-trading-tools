
import json
import os
from dmarket_client import DMarketClient

# Load API keys from environment variables
public_key = os.getenv("DMARKET_PUBLIC_KEY")
secret_key = os.getenv("DMARKET_SECRET_KEY")

def get_offer_from_market(client: DMarketClient):
    path = "/exchange/v1/market/items"
    params = {"gameId": "a8db", "limit": 1, "currency": "USD"}
    print(f"Calling GET {path} with params: {params}")
    response_data, error = client.call("GET", path, payload=params)
    if error:
        raise Exception(f"Failed to get market offer: {error}")
    return response_data["objects"][0]

def build_target_body_from_offer(offer):
    return {"targets": [
        {"amount": 1, "gameId": offer["gameId"], "price": {"amount": "2", "currency": "USD"},
         "attributes": {"gameId": offer["gameId"],
                        "categoryPath": offer["extra"]["categoryPath"],
                        "title": offer["title"],
                        "name": offer["title"],
                        "image": offer["image"],
                        "ownerGets": {"amount": "1", "currency": "USD"}}}
    ]}

def main():
    """
    Example usage of the DMarketClient.
    """
    if not public_key or not secret_key:
        print("Error: DMARKET_PUBLIC_KEY and DMARKET_SECRET_KEY environment variables must be set.")
        return

    # 1. Initialize the client
    try:
        client = DMarketClient(public_key=public_key, secret_key=secret_key)
    except ValueError as e:
        print(f"Error initializing client: {e}")
        return

    # 2. Make a signed GET request
    path = "/trade-aggregator/v1/last-sales"
    params = {
        "gameId": "a8db",
        "title": "AK-47 | B the Monster (Factory New)"
    }
    print(f"Calling GET {path} with params: {params}")
    response_data, error = client.call("GET", path, payload=params)

    if error:
        print(f"Error: {error}")
    else:
        print("Response:")
        print(json.dumps(response_data, indent=2))

    # 3. Make a signed POST request to create a target
    try:
        print("\nFetching an offer from the market to create a target...")
        offer = get_offer_from_market(client)
        target_body = build_target_body_from_offer(offer)

        path = "/exchange/v1/target/create"
        print(f"Calling POST {path} with body: {json.dumps(target_body, indent=2)}")
        response_data, error = client.call("POST", path, payload=target_body)

        if error:
            print(f"Error creating target: {error}")
        else:
            print("Target creation response:")
            print(json.dumps(response_data, indent=2))

    except Exception as e:
        print(f"An error occurred during target creation: {e}")

if __name__ == "__main__":
    main()

