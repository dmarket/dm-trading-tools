#!/usr/bin/env python3
"""
Round-trip check for the signature builders in signature-builder/.

For every sample client: sign a request, send it to a local listener, then rebuild the
non-signed string from the URL that was RECEIVED and ed25519-verify the signature against
it — the same way the DMarket API does:

    non-signed string = METHOD + <percent-DECODED path> + <raw query> + body + X-Sign-Date

That decode/raw asymmetry is the part clients get wrong, so a plain "does it compile" check
would not catch a regression here. The three auth headers, the shape of every request and the
percent-encoding of the transmitted path are checked too.

Requires pynacl. Go, JS and PHP are skipped, loudly, when their toolchain is missing; Python
is the interpreter running this script, so it is never skipped. No DMarket credentials are
used and nothing is sent to the live API: each client is patched to talk to the local
listener and refused if the production host survives the patch.

Env overrides (only needed when a toolchain runs somewhere other than this machine):
    DMTT_CLIENT_HOST  host the sample clients should connect to (default 127.0.0.1)
    DMTT_PHP          php binary to use (default: php)
    DMTT_ONLY         comma-separated subset of: python,go,js,php
    DMTT_REQUIRE      comma-separated languages that must be VERIFIED, not just not-skipped
                      (CI uses all four)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import namedtuple
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDERS = os.path.join(ROOT, 'signature-builder')
CLIENT_HOST = os.environ.get('DMTT_CLIENT_HOST', '127.0.0.1')
PHP_BIN = os.environ.get('DMTT_PHP', 'php')

LANGUAGES = ('python', 'go', 'js', 'php')
SIGNATURE_PREFIX = 'dmar ed25519 '
PRODUCTION_HOST = 'api.dmarket.com'
MAX_SIGN_DATE_DRIFT = 120
LEG_TIMEOUT = 120  # seconds per language; the CI job caps the whole run at 10 minutes

# Every character of a transmitted path is either RFC 3986 unreserved, a "/" separator, or
# percent-encoded. All four clients are expected to agree on this, byte for byte.
WIRE_PATH = re.compile(r'\A(?:[A-Za-z0-9\-._~/]|%[0-9A-Fa-f]{2})*\Z')


def env_languages(name):
    values = [value.strip() for value in os.environ.get(name, '').split(',') if value.strip()]
    unknown = sorted(set(values) - set(LANGUAGES))
    if unknown:
        sys.exit(f'{name}: unknown language(s) {unknown}; known languages are {list(LANGUAGES)}')
    return values


ONLY = env_languages('DMTT_ONLY')
REQUIRE = env_languages('DMTT_REQUIRE')

# A title that exercises everything the wire form has to get right: a space and a "|" (which
# node and curl refuse to send raw), a literal "%" followed by two hex digits (a client that
# forgets to encode it sends a path the server decodes to a different title), "+" and "&"
# (left raw by url.PathEscape, and a raw "+" reads as a space to anything that form-decodes),
# and parentheses (left raw by encodeURIComponent).
TITLE = 'AK-47 | Redline 50%20off + 5&5 (Field-Tested)'
TARGETS_PATH = f'/marketplace-api/v1/targets-by-title/a8db/{TITLE}'
LAST_SALES_PATH = '/trade-aggregator/v1/last-sales'
CREATE_PATH = '/exchange/v1/target/create'

Case = namedtuple('Case', 'name method path payload')

# One case per request shape. Every client must send exactly these, in this order.
CASES = [
    Case('free-text path, no payload', 'GET', TARGETS_PATH, None),
    Case('free-text path plus query', 'GET', TARGETS_PATH, {'limit': '1', 'currency': 'USD'}),
    Case('query only', 'GET', LAST_SALES_PATH, {'gameId': 'a8db', 'title': TITLE}),
    Case('json body', 'POST', CREATE_PATH, {'title': TITLE}),
    Case('empty payload, no body', 'POST', CREATE_PATH, {}),
]

KEY = SigningKey.generate()
PUBLIC_KEY = KEY.verify_key.encode().hex()
SECRET_KEY = (KEY.encode() + KEY.verify_key.encode()).hex()

received = []


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _record(self):
        body = b''
        length = int(self.headers.get('Content-Length') or 0)
        if length:
            body = self.rfile.read(length)
        received.append({
            'method': self.command,
            'target': self.path,
            'body': body.decode('utf-8', 'replace'),
            'key': self.headers.get('X-Api-Key', ''),
            'sign': self.headers.get('X-Request-Sign', ''),
            'date': self.headers.get('X-Sign-Date', ''),
        })
        payload = b'{"orders":[]}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = _record

    def log_message(self, *_args):
        pass


def api_verifies(request):
    """Rebuild the non-signed string the way the API does and verify the signature."""
    path, separator, query = request['target'].partition('?')
    unsigned = request['method'] + unquote(path) + separator + query + request['body'] + request['date']

    sign = request['sign']
    if not sign.startswith(SIGNATURE_PREFIX):
        return False, unsigned, f'X-Request-Sign does not start with {SIGNATURE_PREFIX!r}: {sign!r}'
    try:
        signature = bytes.fromhex(sign[len(SIGNATURE_PREFIX):])
    except ValueError:
        return False, unsigned, f'X-Request-Sign is not hex: {sign!r}'
    try:
        KEY.verify_key.verify(unsigned.encode(), signature)
    except BadSignatureError:
        return False, unsigned, 'signature does not verify against the URL as received'
    return True, unsigned, None


def header_problems(request):
    problems = []
    if request['key'] != PUBLIC_KEY:
        problems.append(f'X-Api-Key is {request["key"]!r}, expected the public key {PUBLIC_KEY!r}')

    date = request['date']
    if not (len(date) == 10 and date.isdigit()):
        problems.append(f'X-Sign-Date is not a 10-digit unix timestamp in seconds: {date!r}')
    else:
        drift = abs(int(date) - int(time.time()))
        if drift > MAX_SIGN_DATE_DRIFT:
            problems.append(f'X-Sign-Date is {drift}s from now; the API rejects more than {MAX_SIGN_DATE_DRIFT}s')
    return problems


def shape_problems(request, case):
    problems = []
    if request['method'] != case.method:
        problems.append(f'method is {request["method"]}, expected {case.method}')

    path, separator, _query = request['target'].partition('?')
    if not WIRE_PATH.match(path):
        problems.append(f'transmitted path is not percent-encoded to RFC 3986 unreserved: {path!r}')
    if unquote(path) != case.path:
        problems.append(f'path decodes to {unquote(path)!r}, expected {case.path!r}')

    expects_query = bool(case.payload) and case.method == 'GET'
    if bool(separator) != expects_query:
        problems.append(f'{"no " if expects_query else ""}query string on the wire, '
                        f'expected {"one" if expects_query else "none"}')

    expects_body = bool(case.payload) and case.method != 'GET'
    if bool(request['body']) != expects_body:
        problems.append(f'{"no " if expects_body else ""}request body, '
                        f'expected {"one" if expects_body else "none"}')
    return problems


def patch(src, old, new, what):
    """Replace `old` in a sample's source, refusing to fail open if it is no longer there."""
    if src.count(old) != 1:
        sys.exit(f'ci/verify_signing.py is out of date: found {src.count(old)} occurrences of the '
                 f'{what} it patches, expected 1. Looked for:\n    {old!r}')
    return src.replace(old, new)


def refuse_production(src, what):
    """Never let a leg run against the real API: main.* creates a real buy order."""
    if PRODUCTION_HOST in src:
        sys.exit(f'refusing to run: {what} still mentions {PRODUCTION_HOST} after patching')


def env_for(base_url):
    env = dict(os.environ)
    env.update(DMARKET_BASE_URL=base_url, DMARKET_PUBLIC_KEY=PUBLIC_KEY, DMARKET_SECRET_KEY=SECRET_KEY)
    return env


def run(cmd, cwd, base_url):
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env_for(base_url), capture_output=True, text=True, timeout=LEG_TIMEOUT)
    except subprocess.TimeoutExpired as expired:
        return False, f'{" ".join(cmd)} timed out after {expired.timeout}s'
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        output = f'{" ".join(cmd)} exited {proc.returncode}\n{output}'
    return proc.returncode == 0, output


# --------------------------------------------------------------------------- python
def check_python(tmp, base_url):
    src = open(os.path.join(BUILDERS, 'python', 'dmarket_client.py')).read()
    src = patch(src, 'import json', 'import json\nimport os', 'python client import block')
    src = patch(src, 'self._root_api_url = "https://api.dmarket.com"',
                'self._root_api_url = os.environ["DMARKET_BASE_URL"]', 'python client base URL')
    refuse_production(src, 'the patched python client')
    open(os.path.join(tmp, 'dmarket_client.py'), 'w').write(src)

    cases = [(case.method, case.path, case.payload) for case in CASES]
    with open(os.path.join(tmp, 'runner.py'), 'w') as fh:
        fh.write(f'''
import os, sys
sys.path.insert(0, {tmp!r})
from dmarket_client import DMarketClient

client = DMarketClient(public_key=os.environ["DMARKET_PUBLIC_KEY"], secret_key=os.environ["DMARKET_SECRET_KEY"])
for method, path, payload in {cases!r}:
    response, error = client.call(method, path, payload=payload)
    if error is not None:
        sys.stderr.write(f"{{method}} {{path}}: {{error}}\\n")
        sys.exit(1)
''')
    return run([sys.executable, 'runner.py'], tmp, base_url)


# --------------------------------------------------------------------------- go
def go_payload(payload):
    if payload is None:
        return 'nil'
    # Go wants double-quoted strings; python repr() would emit rune literals.
    entries = ', '.join(f'{json.dumps(key)}: {json.dumps(value)}' for key, value in payload.items())
    return f'map[string]string{{{entries}}}'


def check_go(tmp, base_url):
    if not shutil.which('go'):
        return None
    src = open(os.path.join(BUILDERS, 'go', 'dmarket_client.go')).read()
    src = patch(src, 'const rootApiUrl = "https://api.dmarket.com"',
                'var rootApiUrl = os.Getenv("DMARKET_BASE_URL")', 'go client base URL')
    src = patch(src, '"net/url"', '"net/url"\n\t"os"', 'go client import block')
    refuse_production(src, 'the patched go client')
    open(os.path.join(tmp, 'dmarket_client.go'), 'w').write(src)

    cases = '\n'.join(f'\t\t{{{json.dumps(case.method)}, {json.dumps(case.path)}, {go_payload(case.payload)}}},'
                      for case in CASES)
    with open(os.path.join(tmp, 'main.go'), 'w') as fh:
        fh.write(f'''
package main

import (
	"fmt"
	"os"
)

func main() {{
	c, err := NewDMarketClient(os.Getenv("DMARKET_PUBLIC_KEY"), os.Getenv("DMARKET_SECRET_KEY"))
	if err != nil {{
		fmt.Println(err)
		os.Exit(1)
	}}
	for _, call := range []struct {{
		method  string
		path    string
		payload interface{{}}
	}}{{
{cases}
	}} {{
		if _, err := c.Call(call.method, call.path, call.payload); err != nil {{
			fmt.Printf("%s %s: %v\\n", call.method, call.path, err)
			os.Exit(1)
		}}
	}}
}}
''')
    init = subprocess.run(['go', 'mod', 'init', 'verify'], cwd=tmp, capture_output=True, text=True)
    if init.returncode != 0:
        return False, 'go mod init exited %d\n%s' % (init.returncode, (init.stdout + init.stderr).strip())
    return run(['go', 'run', '.'], tmp, base_url)


# --------------------------------------------------------------------------- js
def check_js(tmp, base_url):
    if not shutil.which('node'):
        return None
    modules = os.path.join(BUILDERS, 'js', 'node_modules')
    if not os.path.isdir(modules):
        print('    node_modules missing — run `npm ci` in signature-builder/js first')
        return None
    os.symlink(modules, os.path.join(tmp, 'node_modules'), target_is_directory=True)

    src = open(os.path.join(BUILDERS, 'js', 'dmarketClient.js')).read()
    src = patch(src, "import https from 'https';", "import https from 'http';", 'js client transport')
    src = patch(src, "this.rootApiUrl = 'api.dmarket.com';",
                "const base = new URL(process.env.DMARKET_BASE_URL);\n"
                "        this.rootApiUrl = base.hostname;\n"
                "        this.rootApiPort = base.port;", 'js client base URL')
    src = patch(src, '            method: method,', '            port: this.rootApiPort,\n            method: method,',
                'js client request options')
    refuse_production(src, 'the patched js client')
    open(os.path.join(tmp, 'dmarketClient.js'), 'w').write(src)
    open(os.path.join(tmp, 'package.json'), 'w').write('{"type":"module"}')

    cases = json.dumps([[case.method, case.path, case.payload] for case in CASES])
    with open(os.path.join(tmp, 'runner.mjs'), 'w') as fh:
        fh.write(f'''
import {{ DMarketClient }} from './dmarketClient.js';

const client = new DMarketClient(process.env.DMARKET_PUBLIC_KEY, process.env.DMARKET_SECRET_KEY);
for (const [method, path, payload] of {cases}) {{
    try {{
        await client.call(method, path, payload);
    }} catch (error) {{
        console.error(`${{method}} ${{path}}: ${{error.message}}`);
        process.exit(1);
    }}
}}
''')
    return run(['node', 'runner.mjs'], tmp, base_url)


# --------------------------------------------------------------------------- php
def php_literal(value):
    if value is None:
        return 'null'
    if isinstance(value, dict):
        return '[' + ', '.join(f'{php_literal(k)} => {php_literal(v)}' for k, v in value.items()) + ']'
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"


def check_php(tmp, base_url):
    if not shutil.which(PHP_BIN) and not os.path.isfile(PHP_BIN):
        return None
    vendor = os.path.join(BUILDERS, 'php', 'vendor')
    if not os.path.isfile(os.path.join(vendor, 'autoload.php')):
        print('    vendor missing — run `composer install` in signature-builder/php first')
        return None
    shutil.copytree(vendor, os.path.join(tmp, 'vendor'), dirs_exist_ok=True)

    src = open(os.path.join(BUILDERS, 'php', 'DMarketClient.php')).read()
    # PHP cannot call getenv() in a property initialiser; the runner sets it by reflection,
    # which also fails loudly if the property is ever renamed.
    src = patch(src, 'private $rootApiUrl = "https://api.dmarket.com";', "private $rootApiUrl = '';",
                'php client base URL')
    refuse_production(src, 'the patched php client')
    open(os.path.join(tmp, 'DMarketClient.php'), 'w').write(src)

    cases = ',\n    '.join(f'[{php_literal(case.method)}, {php_literal(case.path)}, {php_literal(case.payload)}]'
                           for case in CASES)
    with open(os.path.join(tmp, 'runner.php'), 'w') as fh:
        fh.write(f'''<?php
require_once __DIR__ . '/DMarketClient.php';

$client = new DMarketClient(getenv('DMARKET_PUBLIC_KEY'), getenv('DMARKET_SECRET_KEY'));
$property = (new ReflectionClass($client))->getProperty('rootApiUrl');
$property->setAccessible(true);
$property->setValue($client, getenv('DMARKET_BASE_URL'));

foreach ([
    {cases},
] as [$method, $path, $payload]) {{
    list($response, $error) = $client->call($method, $path, $payload);
    if ($error !== null) {{
        fwrite(STDERR, "$method $path: $error\\n");
        exit(1);
    }}
}}
''')
    return run([PHP_BIN, 'runner.php'], tmp, base_url)


CHECKS = [('python', check_python), ('go', check_go), ('js', check_js), ('php', check_php)]


def main():
    server = HTTPServer(('0.0.0.0', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f'http://{CLIENT_HOST}:{server.server_port}'
    print(f'listening on port {server.server_port}, clients will call {base_url}\n')

    verified, failed, skipped = [], [], []
    wire_paths = {}
    for name, check in CHECKS:
        if ONLY and name not in ONLY:
            continue
        print(f'=== {name}')
        before = len(received)
        tmp = tempfile.mkdtemp(prefix=f'dmtt-{name}-')
        result = check(tmp, base_url)
        if result is None:
            print('    SKIPPED — toolchain not available\n')
            skipped.append(name)
            continue

        ran, output = result
        requests = received[before:]
        problems = [] if ran else ['the client did not exit cleanly']
        if len(requests) != len(CASES):
            problems.append(f'{len(requests)} request(s) reached the listener, expected {len(CASES)}')

        for index, case in enumerate(CASES):
            if index >= len(requests):
                problems.append(f'{case.name}: no request reached the listener')
                continue
            request = requests[index]
            ok, unsigned, why = api_verifies(request)
            print(f'    {case.name}: {request["method"]} {request["target"]}')
            print(f'      signed as : {unsigned!r}')
            print(f'      verifies  : {"yes" if ok else "NO"}')
            case_problems = ([] if ok else [why])
            case_problems += shape_problems(request, case) + header_problems(request)
            for problem in case_problems:
                print(f'      PROBLEM   : {problem}')
            problems += [f'{case.name}: {problem}' for problem in case_problems]
            wire_paths.setdefault(index, {})[name] = request['target'].partition('?')[0]

        for extra in requests[len(CASES):]:
            problems.append(f'unexpected extra request: {extra["method"]} {extra["target"]}')

        if problems:
            failed.append(name)
            if output:
                print('    client output:')
                print('    ' + output.replace('\n', '\n    ')[:2000])
        else:
            verified.append(name)
        print()

    server.shutdown()

    # The four clients must agree on the wire form of a path, byte for byte: that is the whole
    # claim of this repo, and no round-trip check can see a difference that only breaks on a
    # hop in front of the API (a raw "+" read as a space, say).
    diverged = False
    for index, forms in sorted(wire_paths.items()):
        if len(set(forms.values())) > 1:
            diverged = True
            print(f'FAILED: clients disagree on the path they send for "{CASES[index].name}":')
            for language, form in sorted(forms.items()):
                print(f'    {language}: {form}')

    print(f'selected: {[name for name, _ in CHECKS if not ONLY or name in ONLY]}')
    if verified:
        print(f'verified: {sorted(verified)}')
    if skipped:
        print(f'SKIPPED (not verified): {sorted(skipped)}')
    if failed:
        print(f'FAILED: {sorted(set(failed))}')

    missing = sorted(set(REQUIRE) - set(verified))
    if missing:
        print(f'FAILED: {missing} were required but not verified')
    if not verified:
        print('FAILED: no language was verified')

    if failed or missing or diverged or not verified:
        return 1
    print(f'signatures verify for {sorted(verified)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
