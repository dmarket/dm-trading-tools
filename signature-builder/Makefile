.PHONY: run-python run-php run-js run-go

all: run-python run-php run-js run-go
run-python:
	docker build -t dmarket-python -f python/Dockerfile .
	docker run --rm --env-file .env dmarket-python

run-php:
	docker build -t dmarket-php -f php/Dockerfile .
	docker run --rm --env-file .env dmarket-php

run-js:
	docker build -t dmarket-js -f js/Dockerfile .
	docker run --rm --env-file .env dmarket-js

run-go:
	docker build -t dmarket-go -f go/Dockerfile .
	docker run --rm --env-file .env dmarket-go
