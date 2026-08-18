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

    /**
     * Signs and sends a request. `path` is a route path only, with any free-text value in it
     * left decoded; query parameters go in `payload`, never in `path`.
     */
    async call(method, path, payload = null) {
        method = method.toUpperCase();
        if (path.includes('?')) {
            throw new Error('path must not contain a query string: pass query parameters as payload.');
        }

        const timestamp = Math.floor(new Date().getTime() / 1000);
        let query = '';
        let requestBody = '';

        if (payload) {
            if (method === 'GET') {
                const params = new URLSearchParams(payload).toString();
                if (params) {
                    query = `?${params}`;
                }
            } else {
                requestBody = JSON.stringify(payload);
            }
        }

        // The signature is built from the path as passed in — the API verifies the DECODED path —
        // plus the query string byte-for-byte as it is transmitted.
        const stringToSign = method + path + query + requestBody + timestamp;
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
            // ...while the path on the wire is percent-encoded. The query is already encoded.
            path: this._encodePath(path) + query,
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
     * Percent-encodes each segment of a query-free route path.
     *
     * Needed for endpoints that take a free-text value in the route path, e.g.
     * GET /marketplace-api/v1/targets-by-title/{game_id}/{title}: pass the title decoded,
     * sign the decoded path, send the encoded path. Without this, https.request throws
     * ERR_UNESCAPED_CHARACTERS on a decoded path. A literal "%" becomes "%25".
     */
    _encodePath(path) {
        // encodeURIComponent leaves ! ' ( ) * raw; encode those too, so the wire form is
        // exactly RFC 3986 unreserved (A-Za-z0-9-._~) and matches the other three clients.
        return path
            .split('/')
            .map((segment) => encodeURIComponent(segment).replace(
                /[!'()*]/g,
                (character) => '%' + character.charCodeAt(0).toString(16).toUpperCase(),
            ))
            .join('/');
    }

    _generateSignature(stringToSign) {
        const secretKeyBytes = hexStringToByte(this.secretKey);
        // Use sign.detached for a signature format compatible with the other languages
        const signatureBytes = nacl.sign.detached(new TextEncoder('utf-8').encode(stringToSign), secretKeyBytes);
        return byteToHexString(signatureBytes);
    }
}
