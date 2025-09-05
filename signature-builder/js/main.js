import { DMarketClient } from './dmarketClient.js';

// Load API keys from environment variables
const publicKey = process.env.DMARKET_PUBLIC_KEY;
const secretKey = process.env.DMARKET_SECRET_KEY;

async function getOfferFromMarket(client) {
    const path = "/exchange/v1/market/items";
    const params = { gameId: "a8db", limit: 1, currency: "USD" };
    console.log(`Calling GET ${path} with params:`, params);
    try {
        const response = await client.call("GET", path, params);
        return response.objects[0];
    } catch (error) {
        throw new Error(`Failed to get market offer: ${error.message}`);
    }
}

function buildTargetBodyFromOffer(offer) {
    return {
        targets: [
            {
                amount: 1,
                gameId: offer.gameId,
                price: { amount: "2", currency: "USD" },
                attributes: {
                    gameId: offer.gameId,
                    categoryPath: offer.extra.categoryPath,
                    title: offer.title,
                    name: offer.title,
                    image: offer.image,
                    ownerGets: { amount: "1", currency: "USD" },
                },
            },
        ],
    };
}

async function main() {
    if (!publicKey || !secretKey) {
        console.error("Error: DMARKET_PUBLIC_KEY and DMARKET_SECRET_KEY environment variables must be set.");
        return;
    }

    /**
     * Example usage of the DMarketClient.
     */

    // 1. Initialize the client
    let client;
    try {
        client = new DMarketClient(publicKey, secretKey);
    } catch (e) {
        console.error(`Error initializing client: ${e.message}`);
        return;
    }

    // 2. Make a signed GET request
    const getPath = "/trade-aggregator/v1/last-sales";
    const getParams = {
        gameId: "a8db",
        title: "AK-47 | B the Monster (Factory New)",
    };
    console.log(`Calling GET ${getPath} with params:`, getParams);
    try {
        const responseData = await client.call("GET", getPath, getParams);
        console.log("Response:");
        console.log(JSON.stringify(responseData, null, 2));
    } catch (error) {
        console.error(`Error: ${error.message}`);
    }

    // 3. Make a signed POST request to create a target
    try {
        console.log("\nFetching an offer from the market to create a target...");
        const offer = await getOfferFromMarket(client);
        const targetBody = buildTargetBodyFromOffer(offer);

        const postPath = "/exchange/v1/target/create";
        console.log(`Calling POST ${postPath} with body:`, JSON.stringify(targetBody, null, 2));
        const postResponseData = await client.call("POST", postPath, targetBody);

        console.log("Target creation response:");
        console.log(JSON.stringify(postResponseData, null, 2));
    } catch (error) {
        console.error(`An error occurred during target creation: ${error.message}`);
    }
}

main();
