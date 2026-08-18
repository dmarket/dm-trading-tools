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

// Call signs and sends a request. path is a route path only, with any free-text value in it
// left decoded; query parameters go in payload, never in path.
func (c *DMarketClient) Call(method, path string, payload interface{}) (interface{}, error) {
	method = strings.ToUpper(method)
	if strings.Contains(path, "?") {
		return nil, fmt.Errorf("path must not contain a query string: pass query parameters as payload")
	}

	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	query := ""
	var requestBody []byte
	var err error

	if payload != nil {
		if method == "GET" {
			params, ok := payload.(map[string]string)
			if !ok {
				return nil, fmt.Errorf("GET payload must be a map[string]string")
			}
			values := url.Values{}
			for k, v := range params {
				values.Add(k, v)
			}
			if encoded := values.Encode(); encoded != "" {
				query = "?" + encoded
			}
		} else {
			requestBody, err = json.Marshal(payload)
			if err != nil {
				return nil, fmt.Errorf("failed to marshal payload: %w", err)
			}
		}
	}

	// The signature is built from the path as passed in — the API verifies the DECODED path —
	// plus the query string byte-for-byte as it is transmitted.
	stringToSign := method + path + query + string(requestBody) + timestamp
	signature := c.generateSignature(stringToSign)

	// ...while the path on the wire is percent-encoded. The query is already encoded.
	fullUrl := rootApiUrl + c.encodePath(path) + query
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

// encodePath percent-encodes each segment of a query-free route path. Needed for endpoints
// that take a free-text value in the route path, e.g.
// GET /marketplace-api/v1/targets-by-title/{game_id}/{title}: pass the title decoded, sign
// the decoded path, send the encoded path. A literal "%" therefore becomes "%25".
func (c *DMarketClient) encodePath(path string) string {
	segments := strings.Split(path, "/")
	for i, segment := range segments {
		// Everything outside the RFC 3986 unreserved set (A-Za-z0-9-._~) is encoded.
		// url.PathEscape would leave & = + : @ $ raw, and a raw "+" is read as a space by
		// anything that form-decodes the path. QueryEscape encodes those but writes a
		// space as "+", so put it back as "%20".
		segments[i] = strings.ReplaceAll(url.QueryEscape(segment), "+", "%20")
	}

	return strings.Join(segments, "/")
}

func (c *DMarketClient) generateSignature(stringToSign string) string {
	signatureBytes := ed25519.Sign(c.secretKey, []byte(stringToSign))
	return hex.EncodeToString(signatureBytes)
}

// --- DMarketClient END ---
