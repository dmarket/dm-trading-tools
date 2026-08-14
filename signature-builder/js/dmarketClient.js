import https from 'https';
import nacl from 'tweetnacl';
import { URLSearchParams } from 'url';

// Helper functions from the original script
function byteToHexString(uint8arr) {
    if (!uint8arr) {
        return '';
    }
    let hexStr = '';
    for (let i = 0; i < uint8arr.length; i++) {
        let hex = (uint8arr[i] & 0xff).toString(16);
        hex = (hex.length === 1) ? '0' + hex : hex;
        hexStr += hex;
    }
    return hexStr;
}

function hexStringToByte(str) {
    if (typeof str !== 'string') {
        throw new TypeError('Wrong data type passed to convertor. Hexadecimal string is expected');
    }
    const uInt8arr = new Uint8Array(str.length / 2);
    for (let i = 0, j = 0; i < str.length; i += 2, j++) {
        uInt8arr[j] = parseInt(str.substr(i, 2), 16);
    }
    return uInt8arr;
}

export class DMarketClient {
    constructor(publicKey, secretKey) {
        if (!publicKey || !secretKey) {
            throw new Error('Public and secret keys must be provided.');
        }
        this.publicKey = publicKey;
        this.secretKey = secretKey;
        this.rootApiUrl = 'api.dmarket.com';
        this.signaturePrefix = 'dmar ed25519 ';
    }

    async call(method, path, payload = null) {
        method = method.toUpperCase();
        const timestamp = Math.floor(new Date().getTime() / 1000);
        let apiUrlPath = path;
        let requestBody = '';

        if (payload) {
            if (method === 'GET') {
                const params = new URLSearchParams(payload);
                apiUrlPath = `${path}?${params.toString()}`;
            } else {
                requestBody = JSON.stringify(payload);
            }
        }

        // The signature is built from the DECODED path — that is what the API verifies —
        // while query parameters are signed exactly as they are transmitted (percent-encoded).
        const stringToSign = method + apiUrlPath + requestBody + timestamp;
        const signature = this._generateSignature(stringToSign);

        const headers = {
            'X-Api-Key': this.publicKey,
            'X-Request-Sign': this.signaturePrefix + signature,
            'X-Sign-Date': timestamp,
        };

        if (method !== 'GET' && payload) {
            headers['Content-Type'] = 'application/json';
            headers['Content-Length'] = Buffer.byteLength(requestBody);
        }

        const options = {
            hostname: this.rootApiUrl,
            // ...and the URL on the wire is percent-encoded.
            path: this._encodePath(apiUrlPath),
            method: method,
            headers: headers,
        };

        return new Promise((resolve, reject) => {
            const req = https.request(options, (res) => {
                let data = '';
                res.on('data', (chunk) => {
                    data += chunk;
                });
                res.on('end', () => {
                    if (res.statusCode >= 400) {
                        reject(new Error(`API call failed with status code ${res.statusCode}: ${data}`));
                    } else {
                        try {
                            resolve(JSON.parse(data));
                        } catch (e) {
                            reject(new Error('Failed to parse JSON response.'));
                        }
                    }
                });
            });

            req.on('error', (e) => {
                reject(e);
            });

            if (method !== 'GET' && requestBody) {
                req.write(requestBody);
            }

            req.end();
        });
    }

    /**
     * Percent-encodes each path segment, leaving an already-encoded query string as is.
     *
     * Needed for endpoints that take a free-text value in the route path, e.g.
     * GET /marketplace-api/v1/targets-by-title/{game_id}/{title}: pass the title decoded,
     * sign the decoded path, send the encoded URL. Without this, https.request throws
     * ERR_UNESCAPED_CHARACTERS on a decoded path.
     */
    _encodePath(apiUrlPath) {
        const queryIndex = apiUrlPath.indexOf('?');
        const path = queryIndex === -1 ? apiUrlPath : apiUrlPath.slice(0, queryIndex);
        const query = queryIndex === -1 ? '' : apiUrlPath.slice(queryIndex);

        return path.split('/').map(encodeURIComponent).join('/') + query;
    }

    _generateSignature(stringToSign) {
        const secretKeyBytes = hexStringToByte(this.secretKey);
        // Use sign.detached for a signature format compatible with the other languages
        const signatureBytes = nacl.sign.detached(new TextEncoder('utf-8').encode(stringToSign), secretKeyBytes);
        return byteToHexString(signatureBytes);
    }
}
