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

    public function call(string $method, string $path, array $payload = null) {
        $method = strtoupper($method);
        $timestamp = (new DateTime())->getTimestamp();
        $apiUrlPath = $path;
        $requestBody = '';

        if ($payload) {
            if ($method === 'GET') {
                // URL-encode query parameters, RFC 3986
                $apiUrlPath = $path . '?' . http_build_query($payload, '', '&', PHP_QUERY_RFC3986);
            } else {
                $requestBody = json_encode($payload);
            }
        }

        // The signature is built from the DECODED path - that is what the API verifies -
        // while query parameters are signed exactly as they are transmitted (percent-encoded).
        $stringToSign = $method . $apiUrlPath . $requestBody . $timestamp;
        $signature = $this->generateSignature($stringToSign);

        $headers = [
            'X-Api-Key: ' . $this->publicKey,
            'X-Request-Sign: ' . $this->signaturePrefix . $signature,
            'X-Sign-Date: ' . $timestamp,
        ];

        if ($method !== 'GET' && $payload) {
            $headers[] = 'Content-Type: application/json';
        }

        // ...and the URL on the wire is percent-encoded.
        $fullUrl = $this->rootApiUrl . $this->encodePath($apiUrlPath);

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
     * Percent-encodes each path segment, leaving an already-encoded query string as is.
     *
     * Needed for endpoints that take a free-text value in the route path, e.g.
     * GET /marketplace-api/v1/targets-by-title/{game_id}/{title}: pass the title decoded,
     * sign the decoded path, send the encoded URL. Without this, curl rejects a decoded
     * path with "URL rejected: Malformed input to a URL function".
     */
    private function encodePath(string $apiUrlPath): string {
        $queryIndex = strpos($apiUrlPath, '?');
        $path = $queryIndex === false ? $apiUrlPath : substr($apiUrlPath, 0, $queryIndex);
        $query = $queryIndex === false ? '' : substr($apiUrlPath, $queryIndex);

        return implode('/', array_map('rawurlencode', explode('/', $path))) . $query;
    }

    private function generateSignature(string $stringToSign): string {
        return sodium_bin2hex(
            sodium_crypto_sign_detached($stringToSign, sodium_hex2bin($this->secretKey))
        );
    }
}