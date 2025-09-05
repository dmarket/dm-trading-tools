FROM golang:1.24.0-alpine

WORKDIR /app

COPY go/go.mod ./

RUN go mod download

COPY go/ .

RUN go build -o /dmarket-go-example .

CMD ["/dmarket-go-example"]
