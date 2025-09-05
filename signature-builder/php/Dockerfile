FROM php:8.1-cli-alpine

WORKDIR /app

# Install Composer
COPY --from=composer:latest /usr/bin/composer /usr/bin/composer

COPY php/composer.json .

RUN composer install --no-dev --optimize-autoloader

COPY php/ .

CMD ["php", "main.php"]
