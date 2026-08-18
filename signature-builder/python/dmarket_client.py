
import json
from datetime import datetime
from urllib.parse import quote, urlencode

import requests
from nacl.bindings import crypto_sign


class DMarketClient:
    def __init__(self, public_key: str, secret_key: str):
        if not public_key or not secret_key:
            raise ValueError("Public and secret keys must be provided.")
        self._public_key = public_key
        self._secret_key = secret_key
        self._root_api_url = "https://api.dmarket.com"
        self._signature_prefix = "dmar ed25519 "

    def call(self, method: str, path: str, payload: dict = None):
        """
        Makes a signed API call to DMarket.

        :param method: HTTP method (e.g., 'GET', 'POST').
        :param path: API endpoint path (e.g., '/trade-aggregator/v1/last-sales'). A route path
            only, with any free-text value in it left decoded — no query string.
        :param payload: Dictionary of parameters for the request. Becomes the query string for
            GET, a JSON body otherwise.
        :return: A tuple of (response_json, error_string).
        :raises ValueError: if path carries a query string.
        """
        if "?" in path:
            raise ValueError("path must not contain a query string: pass query parameters as payload.")

        method = method.upper()
        nonce = str(round(datetime.now().timestamp()))
        query = ""
        request_body = ""

        if payload:
            if method == "GET":
                query = f"?{urlencode(payload, quote_via=quote)}"
            else:
                request_body = json.dumps(payload)

        # The signature is built from the path as passed in — the API verifies the DECODED path —
        # plus the query string byte-for-byte as it is transmitted.
        string_to_sign = method + path + query + request_body + nonce
        signature = self._generate_signature(string_to_sign)

        headers = {
            "X-Api-Key": self._public_key,
            "X-Request-Sign": self._signature_prefix + signature,
            "X-Sign-Date": nonce,
        }
        if method not in ["GET"] and payload:
            headers["Content-Type"] = "application/json"

        # ...while the path on the wire is percent-encoded. The query is already encoded.
        full_url = self._root_api_url + self._encode_path(path) + query

        try:
            response = requests.request(
                method,
                full_url,
                headers=headers,
                data=request_body.encode('utf-8') if request_body else None
            )
            response.raise_for_status()
            return response.json(), None
        except requests.exceptions.RequestException as e:
            error_details = e.response.text if e.response else "No response body"
            return None, f"API call failed: {e}. Details: {error_details}"

    @staticmethod
    def _encode_path(path: str) -> str:
        """
        Percent-encodes each segment of a query-free route path.

        Needed for endpoints that take a free-text value in the route path, e.g.
        GET /marketplace-api/v1/targets-by-title/{game_id}/{title}: pass the title decoded,
        sign the decoded path, send the encoded path. Everything outside the RFC 3986
        unreserved set (A-Za-z0-9-._~) is encoded, so a literal "%" becomes "%25".
        """
        return "/".join(quote(segment, safe="") for segment in path.split("/"))

    def _generate_signature(self, string_to_sign: str) -> str:
        encoded = string_to_sign.encode('utf-8')
        secret_bytes = bytes.fromhex(self._secret_key)
        signature_bytes = crypto_sign(encoded, secret_bytes)
        return signature_bytes[:64].hex()

