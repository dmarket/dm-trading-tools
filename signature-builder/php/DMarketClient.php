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

        $fullUrl = $this->rootApiUrl . $apiUrlPath;

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

    private function generateSignature(string $stringToSign): string {
        return sodium_bin2hex(
            sodium_crypto_sign_detached($stringToSign, sodium_hex2bin($this->secretKey))
        );
    }
}