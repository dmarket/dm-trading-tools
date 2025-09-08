FROM node:18-slim

WORKDIR /app

COPY js/package*.json ./

RUN npm install

COPY js/ .

CMD ["node", "main.js"]
