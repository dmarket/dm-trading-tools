package main

import (
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

type Keys struct {
	Private string `json:"private"`
	Public  string `json:"public"`
}

func GetPrivateKey(s string) (*[64]byte, error) {
	b, err := hex.DecodeString(s)
	if err != nil {
		return nil, err
	}
	var privateKey [64]byte
	copy(privateKey[:], b[:64])

	return &privateKey, nil
}

func Sign(pk, msg string) (signature string, err error) {
	b, err := GetPrivateKey(pk)
	return sign(b, []byte(msg)), nil
}

func sign(pk *[64]byte, msg []byte) string {
	return hex.EncodeToString(ed25519.Sign((*pk)[:], msg))
}

type Offer struct {
	GameId string `json:"gameId"`
	Title  string `json:"title"`
	Image  string ` json:"image"`
	Extra  struct {
		CategoryPath string `json:"categoryPath"`
	}
}

type MarketResponse struct {
	Objects []Offer `json:"objects"`
}

func getRootUrl() string {
	return "https://api.dmarket.com"
}

func getFirstOfferFromMarket() (offer Offer) {
	resp, _ := http.Get(getRootUrl() + "/exchange/v1/market/items?gameId=a8db&limit=1&currency=USD")
	defer resp.Body.Close()
	bodyBytes, _ := ioutil.ReadAll(resp.Body)
	var marketResponse MarketResponse
	json.Unmarshal(bodyBytes, &marketResponse)
	return marketResponse.Objects[0]
}

func buildTargetBodyFromOffer(offer Offer) string {
	return `{
			"targets": [{
				"amount": 1,
				"gameId": "` + offer.GameId + `",
				"price": {"amount": "2", "currency": "USD"},
				"attributes": {
					"gameId": "` + offer.GameId + `",
					"categoryPath": "` + offer.Extra.CategoryPath + `",
					"title": "` + offer.Title + `",
					"name": "` + offer.Title + `",
					"image": "` + offer.Image + `",
					"ownerGets": {"amount": "1", "currency": "USD"}
				}
			}]}`
}

func main() {
	offer := getFirstOfferFromMarket()
	fmt.Println("Offer: " + offer.Title)

	// replace with your own keys
	keys := Keys{
		Private: "2de2824ac1752d0ed3c66abc67bec2db553022aa718287a1e773e104303031208397eb8e7f88032eb13dca99a11350b05d290c896a96afd60b119184b1b443c9",
		Public:  "8397eb8e7f88032eb13dca99a11350b05d290c896a96afd60b119184b1b443c9",
	}
	body := buildTargetBodyFromOffer(offer)
	fmt.Println(body)
	method := "POST"
	path := "/exchange/v1/target/create"
	timestamp := strconv.Itoa(int(time.Now().UTC().Unix()))
	unsigned := method + path + body + timestamp
	signature, _ := Sign(keys.Private, unsigned)

	client := &http.Client{}
	req, _ := http.NewRequest(method, getRootUrl()+path, ioutil.NopCloser(strings.NewReader(body)))
	req.Header.Set("X-Sign-Date", timestamp)
	req.Header.Set("X-Request-Sign", "dmar ed25519 "+signature)
	req.Header.Set("X-Api-Key", keys.Public)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	res, _ := client.Do(req)

	defer res.Body.Close()
	io.Copy(os.Stdout, res.Body)
}
