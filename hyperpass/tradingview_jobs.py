"""Serialized, persisted chart-only TradingView work. No broker operations."""
import copy
from datetime import datetime,timedelta,timezone
import json
import math
import threading
import uuid
from .tradingview_chart import _port
from .pine_indicator import indicator_title

_STRATEGY_PROPERTIES_URL='https://www.tradingview.com/support/solutions/43000628599-strategy-properties/'
_BROKER_EMULATOR_URL='https://www.tradingview.com/pine-script-docs/concepts/strategies/#broker-emulator'


def now(): return datetime.now(timezone.utc).isoformat()


def _milliseconds_utc(value):
    """Convert documented TradingView millisecond timestamps; never guess units."""
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        return None
    try:
        if not math.isfinite(value): return None
        return (datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=value)).isoformat()
    except (ValueError,OverflowError,OSError):
        return None


def _date_range_summary(report):
    settings=report.get('settings')
    ranges=settings.get('dateRange') if isinstance(settings,dict) else None
    summary={'source_path':'report.settings.dateRange','source_unit':'unix_epoch_milliseconds','timezone':'UTC',
             'boundary_rule':'dateRange는 공급자가 보고한 계산·거래 범위의 경계입니다. trade.from/to를 실제 최초 진입·마지막 청산 시각으로 단정하지 마세요. 관측된 체결 시각은 observed_trade_times와 그 저장 표본 범위를 별도로 확인합니다.'}
    for name in ('backtest','trade'):
        period=ranges.get(name) if isinstance(ranges,dict) else None
        if isinstance(period,dict):
            summary[name]={field+'_utc':_milliseconds_utc(period.get(field)) for field in ('from','to')}
            summary[name]['meaning']='reported_backtest_range' if name=='backtest' else 'reported_trade_range_not_observed_fills'
    return summary


def _observed_trade_times(report):
    """Summarize valid fills from stored rows, before making the AI excerpt."""
    rows=report.get('trades')
    stored=len(rows) if isinstance(rows,list) else None
    metrics=report.get('metrics')
    total=metrics.get('total_trades') if isinstance(metrics,dict) else None
    reported_rows=report.get('total_report_trades')
    counts=[v for v in (reported_rows,total) if isinstance(v,int) and not isinstance(v,bool) and v>=0]
    invalid_count=any(v is not None and (not isinstance(v,int) or isinstance(v,bool) or v<0)
                      for v in (reported_rows,total))
    coverage=('not_provided' if stored is None else 'unknown' if not counts else
              'partial' if any(v>stored for v in counts) else
              'inconsistent' if any(v<stored for v in counts) else
              'unknown' if invalid_count else 'matches_reported_counts')
    entries,exits=[],[]
    for row in rows if isinstance(rows,list) else []:
        if not isinstance(row,dict): continue
        for field,values in (('e',entries),('x',exits)):
            fill=row.get(field)
            value=_milliseconds_utc(fill.get('tm')) if isinstance(fill,dict) else None
            if value is not None: values.append(datetime.fromisoformat(value))
    return {
        'source_path':'report.trades[].e.tm / report.trades[].x.tm',
        'source_unit':'unix_epoch_milliseconds','timezone':'UTC',
        'scope':'stored_trade_rows_before_excerpt',
        'stored_rows':stored,'reported_trade_rows':reported_rows,'reported_total_trades':total,
        'coverage':coverage,'valid_entry_timestamps':len(entries),'valid_exit_timestamps':len(exits),
        'first_entry_utc':min(entries).isoformat() if entries else None,
        'latest_exit_utc':max(exits).isoformat() if exits else None,
        'rule':'저장된 거래 행의 유효한 e.tm 최솟값과 x.tm 최댓값만 변환했습니다. 마지막 20행으로 발췌하기 전 저장 자료가 계산 범위입니다. partial/inconsistent/unknown/not_provided이면 전체 거래의 최초·최종 체결이라고 단정하지 마세요. matches_reported_counts도 행수 일치만 뜻하며 timestamp 누락·오류 또는 자료 자체의 정확성을 검증했다는 뜻이 아닙니다. null은 관측 가능한 유효 시각이 없다는 뜻입니다.',
    }


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
        observed_trade_times=_observed_trade_times(report)
        study_id=report.get('study_id') or result.get('study_id')
        omitted=[]
        if 'before' in result:
            result.pop('before')
            omitted.append({'path':'before','reason':'실행 전 차트 상태는 이번 전략의 결과·설정 근거에서 제외했습니다.'})
        selected_context={'study_id':study_id,'status':'not_available'}
        chart=result.get('chart')
        if isinstance(chart,dict) and isinstance(chart.get('studies'),list):
            studies=chart['studies']
            conflict=bool(report.get('study_id') and result.get('study_id') and report['study_id']!=result['study_id'])
            matches=[row for row in studies if isinstance(row,dict) and isinstance(study_id,str) and study_id and row.get('id')==study_id]
            selected=matches if len(matches)==1 and not conflict else []
            chart['studies']=selected
            selected_context.update(status='matched' if selected else 'id_conflict' if conflict else 'no_unique_match',
                                    stored_studies=len(studies),supplied_studies=len(selected))
            if len(selected)!=len(studies):
                omitted.append({'path':'chart.studies','stored_items':len(studies),'supplied_items':len(selected),
                                'reason':'이번 보고서의 study_id와 일치하는 전략 설정만 전달합니다. 다른 전략·지표의 설정을 이번 실행에 적용하지 않습니다. 일치 항목이 없으면 다른 항목으로 대체하지 않습니다.'})
        arrays={}
        for field in ('equity','orders','trades'):
            rows=report.get(field)
            if isinstance(rows,list):
                report[field]=rows[-20:]
                report[field+'_selection']={'returned':len(report[field]),'stored':len(rows),'selection':'last 20; full available data in saved job JSON'}
                arrays[field]={'stored_rows':len(rows),'supplied_rows':len(report[field]),'selection':'last_20'}
        code=job['request'].get('code','')
        result['strategy_source']=code[:24000]
        result['strategy_source_truncated']=len(code)>24000
        result['saved_job_id']=job['id']
        metrics=report.get('metrics') or {}
        performance=report.get('performance') or {}
        all_performance=performance.get('all') or {}
        equity_rows=arrays.get('equity',{}).get('stored_rows')
        equity_supplied=arrays.get('equity',{}).get('supplied_rows')
        result['unit_conventions']={
            'metrics_percentage_unit':report.get('metric_units') or 'not_declared',
            'normalized_percentage_point_fields':[
                'report.metrics.net_profit_percent','report.metrics.max_drawdown_percent',
                'report.metrics.buy_hold_return_percent','report.metrics.percent_profitable'],
            'normalized_percentage_rule':'report.metric_units가 percentage_points이면 위 metrics 값은 이미 백분율 표시값입니다. %를 붙이며 다시 100을 곱하지 않습니다. 단위 선언이 없는 옛 기록은 동일 단위라고 추정하지 않습니다.',
            'raw_performance_percentage_fields':'report.performance 안에서 이름이 Percent로 끝나는 필드와 percentProfitable',
            'raw_performance_percentage_unit':'fraction',
            'raw_to_display_percentage_multiplier':100,
            'raw_percentage_rule':'원본 분수에 100을 곱하면 백분율입니다. 서로 단위를 맞춘 뒤 같은 지표를 비교하세요. 변환 전 숫자 크기의 차이는 불일치가 아닙니다.',
            'dimensionless_ratio_fields':['profit_factor','profitFactor','sharpe_ratio','sharpeRatio','sortino_ratio','sortinoRatio','ratioAvgWinAvgLoss'],
            'dimensionless_ratio_rule':'이 비율·지수에는 단위가 없으며 백분율로 바꾸지 않습니다.',
            'pine_slippage_unit':'ticks',
            'pine_slippage_rule':'Pine strategy()의 slippage는 틱 수입니다. 퍼센트 비용 시나리오를 같은 숫자로 직접 넣을 수 없으며, 가격·최소 호가 단위에 따른 환산 가정 또는 별도 비용 모형이 필요합니다. 고정 틱 수가 전 구간의 고정 퍼센트를 뜻하지 않습니다.',
            'pine_strategy_properties_reference':_STRATEGY_PROPERTIES_URL,
            'money_currency':report.get('currency'),
            'raw_values_preserved':True,
        }
        result['source_scope']={
            'saved_job_id':job['id'],
            'strategy_study_id':study_id,
            'selected_study_context':selected_context,
            'omitted_context':omitted,
            'chart_connection_target_id':result.get('target_id'),
            'target_id_purpose':'Desktop 차트 연결 식별자이며 보고서·연구 산출물 ID가 아닙니다.',
            'reported_total_trades':metrics.get('total_trades'),
            'reported_trade_rows':report.get('total_report_trades'),
            'reported_total_orders':report.get('total_orders'),
            'arrays':arrays,
            'equity_availability':{
                'status':'available' if equity_rows else 'unavailable' if equity_rows==0 else 'not_provided',
                'stored_rows':equity_rows,'supplied_rows':equity_supplied,
                'available_in_saved_job':bool(equity_rows),
                'saved_job_has_additional_rows':bool(equity_rows and equity_rows>equity_supplied),
                'rule':'저장 equity 행수가 0이거나 배열이 없으면 전체 saved_job JSON에도 자산곡선이 없습니다. 원본 파일을 다시 열면 얻는다고 안내하지 마세요. 전체 거래·주문 행과 봉별 자산곡선은 별개이며, 없는 곡선은 별도 확보가 필요합니다. 거래 종료 누적손익은 미실현 손익을 포함하는 봉별 자산곡선의 대체물이 아닙니다.',
            },
            'selection_rule':'분석에는 각 배열의 마지막 20행까지만 전달합니다. 저장 행수·전달 행수·전체 거래 수를 구분하세요. 제공 표본의 첫 행을 전체 거래 시작으로 보거나 읽지 않은 저장 행을 검토했다고 주장하지 마세요.',
            'strategy_source_characters':{'stored':len(code),'supplied':len(result['strategy_source'])},
        }
        result['date_range_summary']=_date_range_summary(report)
        result['observed_trade_times']=observed_trade_times
        result['time_conventions']={
            'report.settings.dateRange':'from/to는 공급자가 보고한 기간 경계의 Unix epoch 밀리초이며 date_range_summary는 UTC 변환본입니다. 실제 최초 진입·마지막 청산 시각과 같다고 가정하지 않습니다. 원본은 보존하며 변환할 수 없는 값은 null입니다.',
            'report.trades[].e.tm':'진입 시각, Unix epoch 밀리초',
            'report.trades[].x.tm':'청산 시각, Unix epoch 밀리초',
            'report.trades[].e.b / report.trades[].x.b':'봉 인덱스이며 Unix 시각이 아닙니다.',
            'report.orders[].time_index':'TradingView 내부 주문 인덱스이며 Unix 시각으로 변환하지 않습니다.',
            'completed_at':'앱이 보고서 완료를 확인한 시각이며 시장 데이터 기준 시각·백테스트 종료일이 아닙니다.',
        }
        result['risk_context']={
            'margin_calls_observed':all_performance.get('marginCalls'),
            'margin_calls_source':'report.performance.all.marginCalls',
            'margin_calls_scope':'모의실행에서 보고된 관측값입니다. 0이어도 실제 운용의 안전성을 보장하지 않으며 값이 없으면 관측 여부를 추정하지 않습니다.',
            'denominator_rule':'초기자본은 시작 시점의 금액입니다. 누적 이익 이후 절대 손실·낙폭·최대 증거금이 초기자본보다 크다는 이유만으로 레버리지·부채·마진콜·파산을 추정하지 마세요. 해당 시점의 자산·노출과 적용된 증거금 규칙을 함께 확인해야 합니다.',
            'drawdown_rule':'최대 금액 낙폭과 최대 비율 낙폭의 발생 시점이 같다고 가정하지 마세요. 시계열이 없으면 해당 구간의 자산·회복 시점을 복원했다고 주장하지 않습니다.',
            'extrema_rule':'최대 이익·최대 손실의 금액 극값과 퍼센트 극값은 서로 다른 거래에서 발생할 수 있습니다. 동일 거래 ID 또는 동일 원본 거래 행으로 대응을 확인하기 전에는 한 거래의 금액과 수익률처럼 묶지 말고 각각 별도 집계로 표시합니다. 최대 금액 낙폭과 최대 비율 낙폭도 같은 원칙을 적용합니다.',
            'gap_execution_rule':'slippage=0은 추가 틱 슬리피지 설정이 0이라는 뜻이며, 가격 자료에 갭이 없거나 갭을 전혀 반영하지 않았다는 뜻이 아닙니다. 기본 broker emulator도 차트의 봉 사이 갭과 다음 봉 시가를 체결 계산에 사용합니다. Bar Magnifier 미사용도 OHLC·갭 자체 미반영을 뜻하지 않습니다. 실거래의 스프레드·시장충격·유동성·부분체결 등 추가 체결 마찰의 검증 여부와 구분합니다.',
            'broker_emulator_reference':_BROKER_EMULATOR_URL,
            'sensitivity_rule':'비용·사이징 변경의 결과는 경로에 의존합니다. 고정 체결 수량을 가정한 비용 근사와 복리 사이징을 반영한 재실행 결과를 구분하고, 실행하지 않은 민감도를 정량적으로 단정하지 마세요.',
            'standard_ohlc_setting':{
                'parameter':'fill_orders_on_standard_ohlc','applies_to_chart_type':'heikin_ashi',
                'rule':'Heikin-Ashi 차트의 합성 가격 대신 실제 OHLC 가격으로 체결하도록 하는 옵션입니다. 표준 OHLC 차트에서 false라는 이유로 실제 OHLC 미사용·합성 가격 체결·체결 왜곡을 추정하지 마세요. 모든 비표준 차트나 봉 내부 해상도를 개선하는 공통 옵션도 아닙니다.',
            },
            'bar_magnifier_setting':{
                'parameter':'use_bar_magnifier','function':'lower_timeframe_fill_prices',
                'rule':'과거 체결 계산에 더 낮은 주기의 가격을 사용하는 별도 옵션입니다. 미사용은 낮은 주기 데이터로 체결을 정밀화하지 않았다는 뜻이며, OHLC 자체를 사용하지 않았거나 시뮬레이션이 없었다는 뜻이 아닙니다. fill_orders_on_standard_ohlc와 구분하세요.',
            },
            'strategy_properties_reference':_STRATEGY_PROPERTIES_URL,
        }
        return result

    def start(self,payload):
        action=payload.get('action')
        if action not in ('configure','backtest','indicator'): raise ValueError('TradingView 작업을 선택하세요.')
        if action=='indicator':
            indicator_title(payload.get('code'))
            if not payload.get('symbol') or not payload.get('timeframe'):
                raise ValueError('개인 지표를 적용할 종목과 주기를 선택하세요.')
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
            from .tradingview_control import configure_chart,run_strategy,run_indicator
            request=job['request']
            port=request.get('port',9222)
            target=request.get('target_id') or None
            progress('connecting','열린 TradingView 차트를 확인합니다.')
            if request['action']=='configure':
                result=configure_chart(port=port,target_id=target,symbol=request.get('symbol'),timeframe=request.get('timeframe'),indicators=request.get('indicators'))
            else:
                expected_chart=None
                if request.get('symbol') or request.get('timeframe') or request.get('indicators'):
                    configured=configure_chart(port=port,target_id=target,symbol=request.get('symbol'),timeframe=request.get('timeframe'),indicators=request.get('indicators'))
                    job['configuration']=configured
                    if configured.get('status')!='configured':
                        raise ValueError('요청한 차트 설정을 확인하지 못했습니다. 적용 상태를 확인하세요.')
                    target=configured.get('target_id') or target
                    expected_chart=configured['chart']
                if request['action']=='indicator':
                    result=run_indicator(port=port,target_id=target,code=request['code'],timeout=75,on_progress=progress,expected_chart=expected_chart)
                else:
                    result=run_strategy(port=port,target_id=target,code=request['code'],timeout=75,on_progress=progress,expected_chart=expected_chart)
            failed=result.get('status') not in ('completed','configured','applied')
            job.update(status='failed' if failed else 'completed',stage='finished',result=result,
                       message='TradingView 작업을 완료했습니다.' if not failed else 'TradingView에서 확인한 오류와 적용 상태를 확인하세요.',
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
