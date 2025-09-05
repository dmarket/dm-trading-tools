<?php

require_once __DIR__ . '/vendor/autoload.php';
require_once __DIR__ . '/DMarketClient.php';

// Load API keys from environment variables
$publicKey = getenv('DMARKET_PUBLIC_KEY');
$secretKey = getenv('DMARKET_SECRET_KEY');

function getOfferFromMarket(DMarketClient $client): array {
    $path = "/exchange/v1/market/items";
    $params = ["gameId" => "a8db", "limit" => 1, "currency" => "USD"];
    echo "Calling GET $path with params: " . json_encode($params) . "\n";
    list($responseData, $error) = $client->call("GET", $path, $params);
    if ($error) {
        throw new Exception("Failed to get market offer: $error");
    }
    return $responseData['objects'][0];
}

function buildTargetBodyFromOffer(array $offer): array {
    return [
        "targets" => [
            [
                "amount" => 1,
                "gameId" => $offer['gameId'],
                "price" => ["amount" => "2", "currency" => "USD"],
                "attributes" => [
                    "gameId" => $offer['gameId'],
                    "categoryPath" => $offer['extra']['categoryPath'],
                    "title" => $offer['title'],
                    "name" => $offer['title'],
                    "image" => $offer['image'],
                    "ownerGets" => ["amount" => "1", "currency" => "USD"]
                ]
            ]
        ]
    ];
}

function main() {
    global $publicKey, $secretKey;

    if (empty($publicKey) || empty($secretKey)) {
        echo "Error: DMARKET_PUBLIC_KEY and DMARKET_SECRET_KEY environment variables must be set.\n";
        return;
    }

    /**
     * Example usage of the DMarketClient.
     */

    // 1. Initialize the client
    try {
        $client = new DMarketClient($publicKey, $secretKey);
    } catch (InvalidArgumentException $e) {
        echo "Error initializing client: " . $e->getMessage() . "\n";
        return;
    }

    // 2. Make a signed GET request
    $path = "/trade-aggregator/v1/last-sales";
    $params = [
        "gameId" => "a8db",
        "title" => "AK-47 | B the Monster (Factory New)"
    ];

    echo "Calling GET $path with params: " . json_encode($params) . "\n";
    list($responseData, $error) = $client->call("GET", $path, $params);

    if ($error) {
        echo "Error: $error\n";
    } else {
        echo "Response:\n";
        echo json_encode($responseData, JSON_PRETTY_PRINT) . "\n";
    }

    // 3. Make a signed POST request to create a target
    try {
        echo "\nFetching an offer from the market to create a target...\n";
        $offer = getOfferFromMarket($client);
        $targetBody = buildTargetBodyFromOffer($offer);

        $path = "/exchange/v1/target/create";
        echo "Calling POST $path with body: " . json_encode($targetBody, JSON_PRETTY_PRINT) . "\n";
        list($responseData, $error) = $client->call("POST", $path, $targetBody);

        if ($error) {
            echo "Error creating target: $error\n";
        } else {
            echo "Target creation response:\n";
            echo json_encode($responseData, JSON_PRETTY_PRINT) . "\n";
        }
    } catch (Exception $e) {
        echo "An error occurred during target creation: " . $e->getMessage() . "\n";
    }
}

main();
