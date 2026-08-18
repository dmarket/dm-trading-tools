#!/usr/bin/env python3
"""
Round-trip check for the signature builders in signature-builder/.

For every sample client: sign a request, send it to a local listener, then rebuild the
non-signed string from the URL that was RECEIVED and ed25519-verify the signature against
it — the same way the DMarket API does:

    non-signed string = METHOD + <percent-DECODED path> + <raw query> + body + X-Sign-Date

That decode/raw asymmetry is the part clients get wrong, so a plain "does it compile" check
would not catch a regression here. Requires pynacl; each language is skipped, loudly, if
its toolchain is missing.

Env overrides (only needed when a toolchain runs somewhere other than this machine):
    DMTT_CLIENT_HOST  host the sample clients should connect to (default 127.0.0.1)
    DMTT_PHP          php binary to use (default: php)
    DMTT_ONLY         comma-separated subset of: python,go,js,php
    DMTT_REQUIRE      comma-separated languages that must not be skipped (CI uses all four)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote

from nacl.signing import SigningKey

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDERS = os.path.join(ROOT, 'signature-builder')
CLIENT_HOST = os.environ.get('DMTT_CLIENT_HOST', '127.0.0.1')
PHP_BIN = os.environ.get('DMTT_PHP', 'php')
ONLY = [s for s in os.environ.get('DMTT_ONLY', '').split(',') if s]
REQUIRE = [s for s in os.environ.get('DMTT_REQUIRE', '').split(',') if s]

TITLE = 'AK-47 | Redline (Field-Tested)'
TARGETS_PATH = f'/marketplace-api/v1/targets-by-title/a8db/{TITLE}'
LAST_SALES_PATH = '/trade-aggregator/v1/last-sales'
CREATE_PATH = '/exchange/v1/target/create'

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
    target = request['target']
    cut = target.find('?')
    path, query = (target, '') if cut == -1 else (target[:cut], target[cut:])
    unsigned = request['method'] + unquote(path) + query + request['body'] + request['date']
    try:
        KEY.verify_key.verify(unsigned.encode(), bytes.fromhex(request['sign'].replace('dmar ed25519 ', '')))
        return True, unsigned
    except Exception:
        return False, unsigned


def env_for(base_url):
    env = dict(os.environ)
    env.update(DMARKET_BASE_URL=base_url, DMARKET_PUBLIC_KEY=PUBLIC_KEY, DMARKET_SECRET_KEY=SECRET_KEY)
    return env


def run(cmd, cwd, base_url):
    proc = subprocess.run(cmd, cwd=cwd, env=env_for(base_url), capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        print(f'    client exited {proc.returncode}')
        print('    ' + (proc.stdout + proc.stderr).strip().replace('\n', '\n    ')[:1500])
    return proc.returncode == 0


# --------------------------------------------------------------------------- python
def check_python(tmp, base_url):
    runner = os.path.join(tmp, 'runner.py')
    with open(runner, 'w') as fh:
        fh.write(f'''
import json, os, sys
sys.path.insert(0, {os.path.join(BUILDERS, "python")!r})
from dmarket_client import DMarketClient

client = DMarketClient(public_key=os.environ["DMARKET_PUBLIC_KEY"], secret_key=os.environ["DMARKET_SECRET_KEY"])
client._root_api_url = os.environ["DMARKET_BASE_URL"]
client.call("GET", {TARGETS_PATH!r})
client.call("GET", {LAST_SALES_PATH!r}, payload={{"gameId": "a8db", "title": {TITLE!r}}})
client.call("POST", {CREATE_PATH!r}, payload={{"title": {TITLE!r}}})
''')
    return run([sys.executable, runner], tmp, base_url)


# --------------------------------------------------------------------------- go
def check_go(tmp, base_url):
    if not shutil.which('go'):
        return None
    src = open(os.path.join(BUILDERS, 'go', 'dmarket_client.go')).read().replace(
        'const rootApiUrl = "https://api.dmarket.com"',
        'var rootApiUrl = os.Getenv("DMARKET_BASE_URL")').replace(
        '"net/url"', '"net/url"\n\t"os"')
    open(os.path.join(tmp, 'dmarket_client.go'), 'w').write(src)
    literal = json.dumps  # Go wants double-quoted strings; repr() would emit rune literals
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
		{{"GET", {literal(TARGETS_PATH)}, nil}},
		{{"GET", {literal(LAST_SALES_PATH)}, map[string]string{{"gameId": "a8db", "title": {literal(TITLE)}}}}},
		{{"POST", {literal(CREATE_PATH)}, map[string]interface{{}}{{"title": {literal(TITLE)}}}}},
	}} {{
		if _, err := c.Call(call.method, call.path, call.payload); err != nil {{
			fmt.Println(err)
			os.Exit(1)
		}}
	}}
}}
''')
    subprocess.run(['go', 'mod', 'init', 'verify'], cwd=tmp, capture_output=True)
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
    src = src.replace("import https from 'https';", "import https from 'http';")
    src = src.replace("this.rootApiUrl = 'api.dmarket.com';",
                      "const base = new URL(process.env.DMARKET_BASE_URL);\n"
                      "        this.rootApiUrl = base.hostname;\n"
                      "        this.rootApiPort = base.port;")
    src = src.replace('            method: method,', '            port: this.rootApiPort,\n            method: method,')
    open(os.path.join(tmp, 'dmarketClient.js'), 'w').write(src)
    open(os.path.join(tmp, 'package.json'), 'w').write('{"type":"module"}')
    with open(os.path.join(tmp, 'runner.mjs'), 'w') as fh:
        fh.write(f'''
import {{ DMarketClient }} from './dmarketClient.js';

const client = new DMarketClient(process.env.DMARKET_PUBLIC_KEY, process.env.DMARKET_SECRET_KEY);
await client.call("GET", {json.dumps(TARGETS_PATH)});
await client.call("GET", {json.dumps(LAST_SALES_PATH)}, {{ gameId: "a8db", title: {json.dumps(TITLE)} }});
await client.call("POST", {json.dumps(CREATE_PATH)}, {{ title: {json.dumps(TITLE)} }});
''')
    return run(['node', 'runner.mjs'], tmp, base_url)


# --------------------------------------------------------------------------- php
def check_php(tmp, base_url):
    if not shutil.which(PHP_BIN) and not os.path.isfile(PHP_BIN):
        return None
    shutil.copy(os.path.join(BUILDERS, 'php', 'DMarketClient.php'), tmp)
    vendor = os.path.join(BUILDERS, 'php', 'vendor')
    os.makedirs(os.path.join(tmp, 'vendor'), exist_ok=True)
    if os.path.isfile(os.path.join(vendor, 'autoload.php')):
        shutil.copytree(vendor, os.path.join(tmp, 'vendor'), dirs_exist_ok=True)
    else:
        open(os.path.join(tmp, 'vendor', 'autoload.php'), 'w').write('<?php\n')
    with open(os.path.join(tmp, 'runner.php'), 'w') as fh:
        fh.write(f'''<?php
require_once __DIR__ . '/DMarketClient.php';

$client = new DMarketClient(getenv('DMARKET_PUBLIC_KEY'), getenv('DMARKET_SECRET_KEY'));
$property = (new ReflectionClass($client))->getProperty('rootApiUrl');
$property->setAccessible(true);
$property->setValue($client, getenv('DMARKET_BASE_URL'));

foreach ([
    ['GET', {TARGETS_PATH!r}, null],
    ['GET', {LAST_SALES_PATH!r}, ['gameId' => 'a8db', 'title' => {TITLE!r}]],
    ['POST', {CREATE_PATH!r}, ['title' => {TITLE!r}]],
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

    failed, skipped = [], []
    for name, check in CHECKS:
        if ONLY and name not in ONLY:
            continue
        print(f'=== {name}')
        before = len(received)
        tmp = tempfile.mkdtemp(prefix=f'dmtt-{name}-')
        ran = check(tmp, base_url)
        if ran is None:
            print('    SKIPPED — toolchain not available\n')
            skipped.append(name)
            continue
        requests = received[before:]
        if not ran or not requests:
            print('    no request reached the listener' if not requests else '')
            failed.append(name)
            print()
            continue
        for request in requests:
            ok, unsigned = api_verifies(request)
            print(f'    {request["method"]} {request["target"]}')
            print(f'      signed as : {unsigned!r}')
            print(f'      verifies  : {"yes" if ok else "NO"}')
            if not ok:
                failed.append(name)
        print()

    server.shutdown()
    print(f'checked: {[n for n, _ in CHECKS if not ONLY or n in ONLY]}')
    if skipped:
        print(f'SKIPPED (not verified): {skipped}')
    missing = sorted(set(REQUIRE) & set(skipped))
    if missing:
        print(f'FAILED: {missing} were required but could not run')
        return 1
    if failed:
        print(f'FAILED: {sorted(set(failed))}')
        return 1
    print('all signatures verify')
    return 0


if __name__ == '__main__':
    sys.exit(main())
