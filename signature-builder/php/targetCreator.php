<?php
phpinfo();
require_once "vendor/paragonie/sodium_compat/autoload.php";

var_dump([
    sodium_library_version_major(),
    sodium_library_version_minor(),
    sodium_version_string()
]);


function getRootUrl() {
    return "https://api.dmarket.com";
}

function generateSignature($privateKey, $method, $route, $timestamp, array $postParams = [])
{
    if (!empty($postParams)) {
        $text = $method . $route . json_encode($postParams) . $timestamp;
    } else {
        $text = $method . $route . $timestamp;
    }
    return 'dmar ed25519 ' . sodium_bin2hex(sodium_crypto_sign_detached($text, sodium_hex2bin($privateKey)));
}

function getFirstOfferFromMarket() {
    $marketResponse = file_get_contents(getRootUrl() . '/exchange/v1/market/items?gameId=a8db&limit=1&currency=USD');
    $data = json_decode($marketResponse,true);
    $offer = $data['objects'][0];
    return $offer;
}

function buildTargetBodyFromOffer($offer)
{
    return array("targets" =>
        array(array(
            "amount" => 1,
            "gameId" => $offer['gameId'],
            "price" => array("amount" => "2", "currency" => "USD"),
            "attributes" => array(
                "gameId" => $offer['gameId'],
                "categoryPath" => $offer['extra']['categoryPath'],
                "title" => $offer['title'],
                "name" => $offer['title'],
                "image" => $offer['image'],
                "ownerGets" => array("amount" => "1", "currency" => "USD"))
        )));
}

// replace with your own keys
$publicKey = "8397eb8e7f88032eb13dca99a11350b05d290c896a96afd60b119184b1b443c9";
$secretKey = "2de2824ac1752d0ed3c66abc67bec2db553022aa718287a1e773e104303031208397eb8e7f88032eb13dca99a11350b05d290c896a96afd60b119184b1b443c9";

$randomOffer = getFirstOfferFromMarket();
$now = new DateTime();
$targetBody = buildTargetBodyFromOffer($randomOffer);
$timestamp = $now->getTimestamp();
$method = 'POST';
$url = '/exchange/v1/target/create';
$headers = [
    'X-Api-Key:' . $publicKey,
    'X-Request-Sign:' . generateSignature($secretKey, $method, $url, $timestamp, $targetBody),
    'X-Sign-Date:' . $timestamp,
    'Content-Type:' . 'application/json'
];

$curlRequest = curl_init();
curl_setopt($curlRequest, CURLOPT_URL, getRootUrl() . $url);
curl_setopt($curlRequest, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($curlRequest, CURLOPT_POSTFIELDS, json_encode($targetBody));
curl_setopt($curlRequest, CURLOPT_HTTPHEADER, $headers);
curl_setopt($curlRequest, CURLOPT_RETURNTRANSFER, true);

$result = curl_exec($curlRequest);
print($result);
curl_close($curlRequest);
