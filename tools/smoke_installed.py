"""Exercise an isolated installed app over HTTP without external API credentials.

The chart fixture and DemoProvider output are synthetic. This is not a live AI
or TradingView compatibility test. All writes happen in a temporary installation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler
import zipfile

from build_release import TEAM_FILES, files


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def unpack(archive, destination):
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            path = PurePosixPath(info.filename)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename,
                    'Unsafe ZIP path')
            require(path.parts and path.parts[0] == 'Hyperpass-Research-Web', 'Unexpected ZIP root')
            target = destination.joinpath(*path.parts)
            require(target.resolve().is_relative_to(destination.resolve()), 'ZIP path escaped installation')
            require((info.external_attr >> 16) & 0o170000 != 0o120000, 'ZIP symlinks are not allowed')
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.read(info))
                if os.name != 'nt':
                    target.chmod((info.external_attr >> 16) & 0o777 or 0o644)
    return destination / 'Hyperpass-Research-Web'


class Client:
    def __init__(self, base):
        self.base = base
        self.csrf = ''
        # Local application traffic must not go through an inherited proxy.
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, payload=None, expected=200, csrf=None):
        headers = {'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf if csrf is None else csrf}
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = Request(self.base + path, data=data, headers=headers)
        try:
            response = self.opener.open(request, timeout=8)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read().decode('utf-8')
            body = json.loads(raw) if 'application/json' in response.headers.get('Content-Type', '') else raw
            require(response.status == expected, f'{path}: expected HTTP {expected}, received {response.status}: {str(body)[:200]}')
            return body

    def wait(self, path, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.request(path)
            if result['status'] not in ('queued', 'running', 'collecting'):
                if path.startswith('/api/runs/') and self.request('/api/status').get('active_run') == result['id']:
                    time.sleep(.05)
                    continue
                return result
            time.sleep(.05)
        raise AssertionError(f'{path}: work did not finish within {timeout}s')


def fixture_csv():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    lines = ['time,open,high,low,close,volume']
    for index in range(120):
        price = 100 + index * .1 + 8 * math.sin(index / 8)
        lines.append(f'{(start + timedelta(days=index)).date()},{price},{price+1},{price-1},{price},1000')
    return '\n'.join(lines)


def stop_windows_tree(process):
    """Terminate our bootloader and its child without taskkill/WMI dependencies."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = kernel.Process32NextW.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    owned = [process.pid]
    for parent in owned:
        owned.extend(pid for pid, owner in parents.items() if owner == parent and pid not in owned)
    for pid in reversed(owned):
        handle = kernel.OpenProcess(0x100001, False, pid)  # SYNCHRONIZE | PROCESS_TERMINATE
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # Child already exited while its parent was shutting down.
                continue
            raise ctypes.WinError(error)
        try:
            if not kernel.TerminateProcess(handle, 1) and kernel.WaitForSingleObject(handle, 0) != 0:
                raise ctypes.WinError(ctypes.get_last_error())
            require(kernel.WaitForSingleObject(handle, 10000) == 0, 'Owned Windows process did not terminate')
        finally:
            kernel.CloseHandle(handle)


class NoTradingViewHandler(BaseHTTPRequestHandler):
    """Deterministic local fixture: no active chart, never a real Desktop app."""
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'[]')

    def log_message(self, *args):
        pass


def exercise(client, installation, record):
    status = client.request('/api/status')
    client.csrf = status['csrf']
    require(status['connected'] is False, 'Fresh install must not have an AI key')
    require(not status.get('model'), 'Fresh install unexpectedly selected a research model')
    providers = client.request('/api/ai')['providers']
    require(providers and all(not provider.get('model') for provider in providers),
            'An unconnected AI service reported a selected model')
    require('Hyperpass' in client.request('/'), 'Main page failed to load')
    for asset in ('app.js', 'brain.js', 'chart.js', 'team.js', 'tradingview.js', 'symbol-search.js', 'indicator-lab.js', 'workspaces.css'):
        require(bool(client.request('/' + asset)), 'Missing UI asset: ' + asset)
    record('startup_and_assets', 'Fresh localhost app loaded all workspace assets with no configured key or selected model.')

    indicator_code = '//@version=6\nindicator("Smoke average", overlay=true)\nplot(ta.sma(close, 20))'
    saved_indicator = client.request('/api/indicators', {'name': '내 이동평균', 'code': indicator_code}, expected=201)
    edited_indicator = dict(saved_indicator, name='50봉 평균', code=indicator_code.replace('20)', '50)'))
    client.request('/api/indicators', edited_indicator)
    require(client.request('/api/indicators')['indicators'] == [edited_indicator], 'Personal indicator edit was not saved')
    record('personal_indicators', 'Created, edited and reopened a personal Pine indicator over the installed app API.')

    listed = client.request('/api/team')['documents']
    require({'team/' + item['path'] for item in listed} == TEAM_FILES, 'Expected exactly 33 fixed team documents')
    path = '/api/team/document?' + urlencode({'path': 'common.md'})
    original = client.request(path)
    marker = '\n\nInstalled smoke fixture: retain provenance and independent review.\n'
    saved = client.request('/api/team/document', {'path': 'common.md', 'content': original['content'] + marker,
                           'expected_revision': original['revision']})
    require(saved['revision'] != original['revision'], 'Saving team guidance did not change the revision')
    client.request('/api/team/document', {'path': 'common.md', 'content': 'stale content',
                   'expected_revision': original['revision']}, expected=409)
    client.request('/api/team/document?' + urlencode({'path': '../app.py'}), expected=400)
    require((installation / 'team/.history' / ('common-' + original['revision'] + '.md')).is_file(),
            'Team save did not preserve the prior document')
    record('team_editor', '33 documents present; edit persisted with backup, stale save rejected (409), traversal rejected.')

    client.request('/api/runs', {'question': 'CSRF rejection fixture', 'mode': 'demo'}, expected=403, csrf='invalid')
    client.request('/api/runs', {'question': 'Live request without credentials'}, expected=400)
    record('request_guards', 'Invalid CSRF token rejected and unconfigured live analysis refused.')

    chart = client.request('/api/charts', {'source': 'csv', 'symbol': 'SYNTHETIC', 'csv': fixture_csv(),
                           'interval': '1d', 'options': {'strategy': 'trend_breakout', 'fast_period': 5,
                           'slow_period': 10, 'breakout_period': 5, 'initial_capital': 10000,
                           'fee_bps': 5, 'slippage_bps': 5}}, expected=201)
    require(len(chart['candles']) == 120 and bool(chart['backtest']['equity']), 'CSV chart/backtest missing results')
    exported = client.request('/api/charts/' + chart['id'] + '/export')
    require(exported['id'] == chart['id'], 'Chart export returned another record')
    require(client.request('/api/charts/' + chart['id'] + '/pine').startswith('//@version=6'), 'Pine export missing')
    record('csv_chart', '120 synthetic OHLCV rows imported, local test computed, chart JSON and Pine exported.')

    started = client.request('/api/runs', {'question': '설치 점검용 고정 데모입니다. 실제 시장 분석이 아닙니다.',
                             'mode': 'demo', 'target_role': 'technical-analyst', 'max_calls': 12,
                             'web_search': False}, expected=202)
    run = client.wait('/api/runs/' + started['id'])
    require(run['status'] == 'completed' and run['report_complete'], 'Demo workflow did not complete')
    require(run['mode'] == 'demo' and 'AI 분석 아님' in run['report'], 'Demo was not clearly labelled')
    require(run['reviews']['judgment-reviewer'], 'Demo was completed without independent review')
    require(run['progress']['percent'] == 100, 'Completed demo progress was not 100%')
    require(run['team_document_revisions']['common.md'] == saved['revision'], 'Run did not use saved guidance')
    require(marker.strip() in run['team_snapshot']['documents']['common.md'], 'Persisted instruction snapshot missing')
    require('demo' in client.request('/api/runs/' + run['id'] + '/export'), 'Report export missing demo label')
    record('demo_workflow', 'Fixed DemoProvider calls completed with accepted evidence, independent review and saved instruction snapshot.')

    limited = client.request('/api/runs', {'question': '설치 점검 호출 제한 데모', 'mode': 'demo',
                             'target_role': 'technical-analyst', 'max_calls': 4, 'web_search': False}, expected=202)
    incomplete = client.wait('/api/runs/' + limited['id'])
    require(incomplete['status'] == 'budget_exhausted' and not incomplete['report_complete'], 'Call limit falsely marked complete')
    require(incomplete['progress']['percent'] < 100, 'Incomplete work falsely displayed 100%')
    record('incomplete_status', 'Call-limit workflow remains incomplete and below 100%.')

    fixture = ThreadingHTTPServer(('127.0.0.1', 0), NoTradingViewHandler)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    try:
        job = client.request('/api/tradingview/jobs', {'action': 'configure', 'port': fixture.server_port}, expected=202)
        failed = client.wait('/api/tradingview/jobs/' + job['id'])
        require(failed['status'] == 'failed' and failed.get('error'), 'Absent chart job falsely marked successful')
        require(any(item['id'] == job['id'] for item in client.request('/api/tradingview/jobs')['jobs']), 'Failed job not persisted')
    finally:
        fixture.shutdown()
        fixture.server_close()
        thread.join(2)
    record('tradingview_failure', 'Local no-chart fixture produced a persisted failed job, not a successful backtest.')

    library = client.request('/api/library')
    require(library['counts']['charts'] == 1, 'Chart absent from library')
    require(library['counts']['reports'] == 0 and library['counts']['samples'] >= 1, 'Demo counted as a live research report')
    record('library_classification', 'Chart and demo records remain separated from real completed AI reports.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--source', type=Path)
    source.add_argument('--executable', type=Path)
    source.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = {'version': '0.5.1-preview', 'platform': platform.platform(), 'architecture': platform.machine(),
               'python': platform.python_version(), 'kind': 'source' if args.source else 'executable' if args.executable else 'archive',
               'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'checks': [],
               'not_tested': ['Paid OpenAI/Claude/Gemini model responses', 'External market-data APIs',
                              'Real TradingView Desktop chart/Pine compatibility', 'macOS Gatekeeper/notarization and browser UI interaction']}
    def record(name, detail):
        summary['checks'].append({'name': name, 'status': 'passed', 'detail': detail})
        print('PASS ' + name, flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix='Hyperpass-installed-') as folder:
            temporary = Path(folder)
            installation = temporary / '설치 공백' / 'Hyperpass-Research-Web'
            installation.mkdir(parents=True)
            if args.source:
                for name, path in files(args.source.resolve()):
                    target = installation / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                command = [sys.executable, str(installation / 'app.py')]
            elif args.executable:
                binary = installation / ('Hyperpass-Research-Web.exe' if os.name == 'nt' else 'Hyperpass-Research-Web')
                shutil.copy2(args.executable.resolve(), binary)
                binary.chmod(0o755)
                command = [str(binary)]
                require(not (installation / 'team').exists(), 'Standalone executable seed test must start without team files')
            else:
                installation = unpack(args.archive.resolve(), temporary / '압축 해제 공백')
                if os.name == 'nt':
                    command = [str(installation / 'Hyperpass-Research-Web.exe')]
                else:
                    require((installation / 'Start-Mac.command').stat().st_mode & 0o111, 'Mac launcher ZIP permission missing')
                    require((installation / 'Hyperpass-Research-Web').stat().st_mode & 0o111, 'Mac binary ZIP permission missing')
                    command = ['/bin/bash', str(installation / 'Start-Mac.command')]
            data = temporary / 'isolated-data'
            command += ['--no-browser', '--port', '0', '--data-dir', str(data)]
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
            log_path = temporary / 'app.log'
            with log_path.open('w', encoding='utf-8') as log:
                kwargs = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NO_WINDOW}
                process = subprocess.Popen(command, cwd=installation, stdout=log, stderr=subprocess.STDOUT, env=env, **kwargs)
                try:
                    deadline = time.monotonic() + 50
                    client = None
                    while time.monotonic() < deadline:
                        require(process.poll() is None, 'Application exited before HTTP startup')
                        try:
                            with (data / '.instance.lock').open('rb') as metadata:
                                metadata.seek(1)  # The first byte is locked on Windows.
                                port = json.loads(metadata.read(256))['port']
                            candidate = Client(f'http://127.0.0.1:{port}')
                            candidate.request('/api/status')
                            client = candidate
                            break
                        except (OSError, ValueError, KeyError, URLError):
                            time.sleep(.1)
                    require(client is not None, 'Application did not expose its localhost endpoint within 50s')
                    exercise(client, installation, record)
                finally:
                    if process.poll() is None:
                        if os.name == 'nt':
                            stop_windows_tree(process)
                        else:
                            import signal
                            os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            if os.name == 'nt':
                                process.kill()
                            else:
                                os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=10)
            record('process_cleanup', 'Only the smoke-test process group was terminated; temporary installation and data were removed.')
        summary['status'] = 'passed'
    except Exception as exc:
        summary['status'] = 'failed'
        summary['error'] = f'{type(exc).__name__}: {exc}'
        print(summary['error'], file=sys.stderr, flush=True)
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
