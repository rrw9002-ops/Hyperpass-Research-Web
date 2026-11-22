"""Serialized, persisted chart-only TradingView work. No broker operations."""
import copy
from datetime import datetime,timezone
import json
import threading
import uuid
from .tradingview_chart import _port


def now(): return datetime.now(timezone.utc).isoformat()


class TradingViewJobs:
    def __init__(self,store):
        self.store=store
        self.lock=threading.RLock()
        self.active=None
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tradingview_jobs(id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            rows=db.execute('SELECT body FROM tradingview_jobs').fetchall()
        for row in rows:
            job=json.loads(row[0])
            if job['status'] in ('queued','running'):
                job.update(status='failed',error='앱 종료로 중단됐습니다. TradingView 화면 상태를 확인한 뒤 새로 요청하세요.',finished_at=now())
                self.put(job)

    def put(self,job):
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO tradingview_jobs(id,body) VALUES (?,?)',(job['id'],json.dumps(job,ensure_ascii=False,allow_nan=False)))

    def get(self,identity):
        with self.store.connect() as db:
            row=db.execute('SELECT body FROM tradingview_jobs WHERE id=?',(identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self):
        with self.store.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT body FROM tradingview_jobs ORDER BY rowid DESC LIMIT 100')]

    @staticmethod
    def evidence(job):
        result=copy.deepcopy(job.get('result') or {})
        result.pop('previous_source',None)
        report=result.get('report') or {}
        for field in ('equity','orders','trades'):
            rows=report.get(field)
            if isinstance(rows,list):
                report[field]=rows[-20:]
                report[field+'_selection']={'returned':len(report[field]),'stored':len(rows),'selection':'last 20; full available data in saved job JSON'}
        code=job['request'].get('code','')
        result['strategy_source']=code[:24000]
        result['strategy_source_truncated']=len(code)>24000
        result['saved_job_id']=job['id']
        return result

    def start(self,payload):
        action=payload.get('action')
        if action not in ('configure','backtest'): raise ValueError('TradingView 작업을 선택하세요.')
        _port(payload.get('port',9222))
        if action=='backtest' and (not isinstance(payload.get('code'),str) or not payload['code'].strip() or len(payload['code'].encode())>200000):
            raise ValueError('Pine 전략 코드를 입력하세요. 최대 200KB입니다.')
        fields=('action','port','target_id','symbol','timeframe','indicators','code')
        request={key:copy.deepcopy(payload[key]) for key in fields if key in payload}
        with self.lock:
            if self.active: raise ValueError('TradingView 작업이 진행 중입니다. 끝난 뒤 요청하세요.')
            job={'id':uuid.uuid4().hex,'status':'queued','stage':'queued','message':'TradingView 작업 준비','created_at':now(),'request':request,'result':None,'error':None}
            self.put(job)
            self.active=job['id']
            threading.Thread(target=self._run,args=(job,),daemon=True).start()
            return job

    def _run(self,job):
        def progress(stage,message=None):
            if isinstance(stage,dict):
                if isinstance(stage.get('previous_source'),str): job['previous_source']=stage['previous_source']
                stage,message=stage.get('stage','working'),stage.get('message','TradingView 작업 중')
            with self.lock:
                job.update(status='running',stage=str(stage),message=str(message or stage))
                self.put(job)
        try:
            from .tradingview_control import configure_chart,run_strategy
            request=job['request']
            port=request.get('port',9222)
            target=request.get('target_id') or None
            progress('connecting','열린 TradingView 차트를 확인합니다.')
            if request['action']=='configure':
                result=configure_chart(port=port,target_id=target,symbol=request.get('symbol'),timeframe=request.get('timeframe'),indicators=request.get('indicators'))
            else:
                if request.get('symbol') or request.get('timeframe') or request.get('indicators'):
                    configured=configure_chart(port=port,target_id=target,symbol=request.get('symbol'),timeframe=request.get('timeframe'),indicators=request.get('indicators'))
                    job['configuration']=configured
                    if configured.get('status')!='configured':
                        raise ValueError('요청한 차트 설정이 모두 확인되지 않아 전략 실행을 중단했습니다. 적용 상태를 확인하세요.')
                result=run_strategy(port=port,target_id=target,code=request['code'],timeout=75,on_progress=progress)
            failed=result.get('status') in ('compile_error','no_report','partial','failed')
            job.update(status='failed' if failed else 'completed',stage='finished',result=result,
                       message='TradingView 작업을 완료했습니다.' if not failed else 'TradingView 결과를 확인하세요. 성공한 백테스트로 처리하지 않았습니다.',
                       error='컴파일 오류 또는 확인되지 않은 결과입니다. 상세 내용을 확인하세요.' if failed else None)
        except (ValueError,OSError) as exc:
            job.update(status='failed',stage='failed',error=str(exc),message='TradingView 작업이 중단됐습니다.')
        except Exception:
            job.update(status='failed',stage='failed',error='TradingView 응답을 처리하지 못했습니다. 앱 상태와 지원 버전을 확인하세요.',message='TradingView 작업이 중단됐습니다.')
        finally:
            with self.lock:
                job['finished_at']=now()
                self.put(job)
                self.active=None
