package main

import (
	"bytes"
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// --- DMarketClient START ---

const rootApiUrl = "https://api.dmarket.com"
const signaturePrefix = "dmar ed25519 "

type DMarketClient struct {
	publicKey string
	secretKey ed25519.PrivateKey
}

func NewDMarketClient(publicKey, secretKeyHex string) (*DMarketClient, error) {
	if publicKey == "" || secretKeyHex == "" {
		return nil, fmt.Errorf("public and secret keys must be provided")
	}

	secretKeyBytes, err := hex.DecodeString(secretKeyHex)
	if err != nil {
		return nil, fmt.Errorf("failed to decode secret key: %w", err)
	}
	if len(secretKeyBytes) != ed25519.PrivateKeySize {
		return nil, fmt.Errorf("invalid secret key length: expected %d bytes, got %d", ed25519.PrivateKeySize, len(secretKeyBytes))
	}

	return &DMarketClient{
		publicKey: publicKey,
		secretKey: secretKeyBytes,
	}, nil
}

func (c *DMarketClient) Call(method, path string, payload interface{}) (interface{}, error) {
	method = strings.ToUpper(method)
	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	apiUrlPath := path
	var requestBody []byte
	var err error

	if payload != nil {
		if method == "GET" {
			params, ok := payload.(map[string]string)
			if !ok {
				return nil, fmt.Errorf("GET payload must be a map[string]string")
			}
			query := url.Values{}
			for k, v := range params {
				query.Add(k, v)
			}
			apiUrlPath = path + "?" + query.Encode()
		} else {
			requestBody, err = json.Marshal(payload)
			if err != nil {
				return nil, fmt.Errorf("failed to marshal payload: %w", err)
			}
		}
	}

	stringToSign := method + apiUrlPath + string(requestBody) + timestamp
	signature := c.generateSignature(stringToSign)

	fullUrl := rootApiUrl + apiUrlPath
	req, err := http.NewRequest(method, fullUrl, bytes.NewBuffer(requestBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("X-Api-Key", c.publicKey)
	req.Header.Set("X-Request-Sign", signaturePrefix+signature)
	req.Header.Set("X-Sign-Date", timestamp)
	if method != "GET" && payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute request: %w", err)
	}
	defer resp.Body.Close()

	responseBody, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("API call failed with status %d: %s", resp.StatusCode, string(responseBody))
	}

	var result interface{}
	if err := json.Unmarshal(responseBody, &result); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response JSON: %w. Body: %s", err, string(responseBody))
	}

	return result, nil
}

func (c *DMarketClient) generateSignature(stringToSign string) string {
	signatureBytes := ed25519.Sign(c.secretKey, []byte(stringToSign))
	return hex.EncodeToString(signatureBytes)
}

// --- DMarketClient END ---
