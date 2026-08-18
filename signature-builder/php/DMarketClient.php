<?php

require_once "vendor/autoload.php";

class DMarketClient {
    private $publicKey;
    private $secretKey;
    private $rootApiUrl = "https://api.dmarket.com";
    private $signaturePrefix = "dmar ed25519 ";

    public function __construct(string $publicKey, string $secretKey) {
        if (empty($publicKey) || empty($secretKey)) {
            throw new InvalidArgumentException("Public and secret keys must be provided.");
        }
        $this->publicKey = $publicKey;
        $this->secretKey = $secretKey;
    }

    /**
     * Signs and sends a request. $path is a route path only, with any free-text value in it
     * left decoded; query parameters go in $payload, never in $path.
     */
    public function call(string $method, string $path, array $payload = null) {
        $method = strtoupper($method);
        if (strpos($path, '?') !== false) {
            throw new InvalidArgumentException("Path must not contain a query string: pass query parameters as \$payload.");
        }

        $timestamp = (new DateTime())->getTimestamp();
        $query = '';
        $requestBody = '';

        if ($payload) {
            if ($method === 'GET') {
                // URL-encode query parameters, RFC 3986
                $query = '?' . http_build_query($payload, '', '&', PHP_QUERY_RFC3986);
            } else {
                $requestBody = json_encode($payload);
            }
        }

        // The signature is built from the path as passed in - the API verifies the DECODED
        // path - plus the query string byte-for-byte as it is transmitted.
        $stringToSign = $method . $path . $query . $requestBody . $timestamp;
        $signature = $this->generateSignature($stringToSign);

        $headers = [
            'X-Api-Key: ' . $this->publicKey,
            'X-Request-Sign: ' . $this->signaturePrefix . $signature,
            'X-Sign-Date: ' . $timestamp,
        ];

        if ($method !== 'GET' && $payload) {
            $headers[] = 'Content-Type: application/json';
        }

        // ...while the path on the wire is percent-encoded. The query is already encoded.
        $fullUrl = $this->rootApiUrl . $this->encodePath($path) . $query;

        $curl = curl_init();
        curl_setopt($curl, CURLOPT_URL, $fullUrl);
        curl_setopt($curl, CURLOPT_CUSTOMREQUEST, $method);
        curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($curl, CURLOPT_HTTPHEADER, $headers);

        if ($requestBody) {
            curl_setopt($curl, CURLOPT_POSTFIELDS, $requestBody);
        }

        $response = curl_exec($curl);
        $httpCode = curl_getinfo($curl, CURLINFO_HTTP_CODE);
        $error = curl_error($curl);
        curl_close($curl);

        if ($error) {
            return [null, "cURL Error: " . $error];
        }

        if ($httpCode >= 400) {
            return [null, "API call failed with status code $httpCode: $response"];
        }

        return [json_decode($response, true), null];
    }

    /**
     * Percent-encodes each segment of a query-free route path.
     *
     * Needed for endpoints that take a free-text value in the route path, e.g.
     * GET /marketplace-api/v1/targets-by-title/{game_id}/{title}: pass the title decoded,
     * sign the decoded path, send the encoded path. Without this, curl rejects a decoded
     * path with "URL rejected: Malformed input to a URL function". rawurlencode leaves only
     * the RFC 3986 unreserved set (A-Za-z0-9-._~) alone, so a literal "%" becomes "%25".
     */
    private function encodePath(string $path): string {
        return implode('/', array_map('rawurlencode', explode('/', $path)));
    }

    private function generateSignature(string $stringToSign): string {
        return sodium_bin2hex(
            sodium_crypto_sign_detached($stringToSign, sodium_hex2bin($this->secretKey))
        );
    }
}