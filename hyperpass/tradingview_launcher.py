"""Start an already-installed TradingView Desktop, with loopback debugging only."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import time
from .tradingview_chart import _port, _targets


def installed_binary():
    candidates=[]
    if sys.platform=='win32':
        local=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))
        candidates.extend([local/'Programs/TradingView/TradingView.exe',local/'TradingView/TradingView.exe'])
        for variable in ('ProgramFiles','ProgramFiles(x86)'):
            if os.environ.get(variable): candidates.append(Path(os.environ[variable])/'TradingView/TradingView.exe')
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
                               'Get-AppxPackage -Name TradingView.Desktop | Select-Object -ExpandProperty InstallLocation | ConvertTo-Json -Compress'],
                              capture_output=True,text=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            paths=json.loads(result.stdout.strip() or '[]')
            for folder in ([paths] if isinstance(paths,str) else paths): candidates.append(Path(folder)/'TradingView.exe')
        except (ValueError,TypeError): pass
    elif sys.platform=='darwin':
        candidates=[Path('/Applications/TradingView.app/Contents/MacOS/TradingView'),Path.home()/'Applications/TradingView.app/Contents/MacOS/TradingView']
    else:
        executable=shutil.which('tradingview')
        if executable: candidates.append(Path(executable))
    return next((path for path in candidates if path.is_file()),None)


def launch(port=9222):
    port=_port(port)
    try:
        targets=_targets(port)
        if targets: return {'started':False,'port':port,'message':'기존 로컬 디버그 연결을 사용합니다. 연결 확인에서 차트를 선택하세요.'}
    except (OSError,ValueError): pass
    executable=installed_binary()
    if not executable:
        raise ValueError('TradingView Desktop 설치를 찾지 못했습니다. 공식 Desktop 앱을 설치하고 로그인한 뒤 다시 눌러 주세요.')
    arguments=[str(executable),f'--remote-debugging-port={port}','--remote-debugging-address=127.0.0.1']
    subprocess.Popen(arguments,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0,
                     start_new_session=sys.platform!='win32')
    for _ in range(25):
        try:
            if _targets(port): return {'started':True,'port':port,'message':'TradingView를 열었습니다. 앱에서 로그인하고 차트를 연 뒤 연결을 확인하세요.'}
        except (OSError,ValueError): pass
        time.sleep(.2)
    raise ValueError('TradingView는 실행했지만 디버그 연결이 열리지 않았습니다. 작업을 저장하고 TradingView를 완전히 종료한 뒤 다시 눌러 주세요. 앱을 자동 강제 종료하지 않습니다.')
