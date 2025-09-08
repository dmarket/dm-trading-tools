package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
)

func getOfferFromMarket(client *DMarketClient) (map[string]interface{}, error) {
	path := "/exchange/v1/market/items"
	params := map[string]string{
		"gameId":   "a8db",
		"limit":    "1",
		"currency": "USD",
	}
	fmt.Printf("Calling GET %s with params: %+v\n", path, params)

	response, err := client.Call("GET", path, params)
	if err != nil {
		return nil, fmt.Errorf("failed to get market offer: %w", err)
	}

	responseMap, ok := response.(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("unexpected response format for market items")
	}
	objects, ok := responseMap["objects"].([]interface{})
	if !ok || len(objects) == 0 {
		return nil, fmt.Errorf("no objects found in market response")
	}
	offer, ok := objects[0].(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("offer format is invalid")
	}

	return offer, nil
}

func buildTargetBodyFromOffer(offer map[string]interface{}) map[string]interface{} {
	getString := func(key string) string {
		if val, ok := offer[key].(string); ok {
			return val
		}
		return ""
	}
	getExtra := func(key string) string {
		if extra, ok := offer["extra"].(map[string]interface{}); ok {
			if val, ok := extra[key].(string); ok {
				return val
			}
		}
		return ""
	}

	return map[string]interface{}{
		"targets": []map[string]interface{}{
			{
				"amount": 1,
				"gameId": getString("gameId"),
				"price":  map[string]string{"amount": "2", "currency": "USD"},
				"attributes": map[string]interface{}{
					"gameId":       getString("gameId"),
					"categoryPath": getExtra("categoryPath"),
					"title":        getString("title"),
					"name":         getString("title"),
					"image":        getString("image"),
					"ownerGets":    map[string]string{"amount": "1", "currency": "USD"},
				},
			},
		},
	}
}

func main() {
	publicKey := os.Getenv("DMARKET_PUBLIC_KEY")
	secretKey := os.Getenv("DMARKET_SECRET_KEY")

	if publicKey == "" || secretKey == "" {
		log.Fatal("Error: DMARKET_PUBLIC_KEY and DMARKET_SECRET_KEY environment variables must be set.")
	}

	client, err := NewDMarketClient(publicKey, secretKey)
	if err != nil {
		log.Fatalf("Error initializing client: %v", err)
	}

	getPath := "/trade-aggregator/v1/last-sales"
	getParams := map[string]string{
		"gameId": "a8db",
		"title":  "AK-47 | B the Monster (Factory New)",
	}
	fmt.Printf("Calling GET %s with params: %+v\n", getPath, getParams)
	responseData, err := client.Call("GET", getPath, getParams)
	if err != nil {
		log.Printf("Error: %v", err)
	} else {
		fmt.Println("Response:")
		prettyJSON, _ := json.MarshalIndent(responseData, "", "  ")
		fmt.Println(string(prettyJSON))
	}

	fmt.Println("\nFetching an offer from the market to create a target...")
	offer, err := getOfferFromMarket(client)
	if err != nil {
		log.Printf("An error occurred during target creation: %v", err)
	} else {
		targetBody := buildTargetBodyFromOffer(offer)

		postPath := "/exchange/v1/target/create"
		bodyJSON, _ := json.MarshalIndent(targetBody, "", "  ")
		fmt.Printf("Calling POST %s with body: %s\n", postPath, string(bodyJSON))

		postResponseData, err := client.Call("POST", postPath, targetBody)
		if err != nil {
			log.Printf("Error creating target: %v", err)
		} else {
			fmt.Println("Target creation response:")
			prettyJSON, _ := json.MarshalIndent(postResponseData, "", "  ")
			fmt.Println(string(prettyJSON))
		}
	}
}
