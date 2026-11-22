"""Editable, versioned research instructions with a fixed ten-role roster."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from .instance import InstanceInUse, InstanceLock

MAX_DOCUMENT_BYTES=64*1024
MAX_SNAPSHOT_BYTES=1024*1024
ROLE_TITLES={
    'head-manager':'Head Manager · 총괄',
    'fundamental-analyst':'기본 분석', 'technical-analyst':'기술 분석',
    'news-analyst':'뉴스 분석', 'macro-analyst':'매크로 분석',
    'instrument-analyst':'상품 분석', 'valuation-analyst':'가치 평가',
    'portfolio-manager':'포트폴리오', 'risk-manager':'위험 검토',
    'judgment-reviewer':'독립 판단 검토',
}
REFERENCE_TITLES={
    'sources':'출처 평가', 'scenarios':'시나리오', 'roles':'역할 경계',
    'research-framing':'연구 질문 구성', 'records':'연구 기록', 'forecast':'전망',
    'dispatch':'팀 배정', 'data-qc':'데이터 품질', 'context':'맥락 구분',
    'child-contract':'전문가 보고 계약', 'calculations':'계산', 'anti-overfit':'과최적화 점검',
}
DOCUMENTS={'common.md':{'title':'공통 리서치 지침','kind':'common','role':None}}
for _role,_title in ROLE_TITLES.items():
    DOCUMENTS[f'roles/{_role}.md']={'title':_title+' · 역할 지침','kind':'role','role':_role}
    DOCUMENTS[f'skills/{_role}.md']={'title':_title+' · 분석 방법','kind':'skill','role':_role}
for _name,_title in REFERENCE_TITLES.items():
    DOCUMENTS[f'references/{_name}.md']={'title':_title+' · 공통 방법','kind':'reference','role':None}

_LOCKS={}
_LOCKS_LOCK=threading.Lock()


class TeamConfigError(ValueError):
    """A user-facing configuration error without private filesystem details."""


class TeamConfigConflict(TeamConfigError):
    def __init__(self,current_revision):
        super().__init__('다른 편집에서 이 문서가 변경되었습니다. 최신 내용을 다시 불러온 뒤 저장해 주세요.')
        self.current_revision=current_revision


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _linked(path):
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def _encode(content):
    if not isinstance(content,str):
        raise TeamConfigError('문서 내용은 UTF-8 텍스트여야 합니다.')
    try:
        raw=content.encode('utf-8')
    except UnicodeError:
        raise TeamConfigError('UTF-8로 저장할 수 없는 문자가 포함되어 있습니다.') from None
    if not content.strip() or len(raw)>MAX_DOCUMENT_BYTES:
        raise TeamConfigError('문서는 비어 있을 수 없으며 UTF-8 기준 64 KiB 이내여야 합니다.')
    if any(ord(char)<32 and char not in '\r\n\t' for char in content):
        raise TeamConfigError('문서에 텍스트가 아닌 제어 문자가 포함되어 있습니다.')
    return raw


def validate_snapshot(snapshot):
    """Return a detached, checked snapshot; callers cannot mutate a live run."""
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get('documents'),dict):
        raise TeamConfigError('팀 지침 스냅샷 형식이 올바르지 않습니다.')
    documents=snapshot['documents']
    if set(documents)!=set(DOCUMENTS):
        raise TeamConfigError('팀 지침 스냅샷에 필수 문서가 없거나 허용되지 않은 문서가 있습니다.')
    encoded={path:_encode(content) for path,content in documents.items()}
    if sum(map(len,encoded.values()))>MAX_SNAPSHOT_BYTES:
        raise TeamConfigError('팀 지침 전체 크기는 1 MiB 이내여야 합니다.')
    revisions={path:_digest(raw) for path,raw in encoded.items()}
    revision=_digest(json.dumps(revisions,sort_keys=True,separators=(',',':')).encode('utf-8'))
    if snapshot.get('revision')!=revision or snapshot.get('revisions')!=revisions:
        raise TeamConfigError('팀 지침 스냅샷의 내용과 버전이 일치하지 않습니다.')
    result={'revision':revision,'documents':dict(documents),'revisions':revisions}
    if isinstance(snapshot.get('upstream'),dict):
        result['upstream']={key:str(snapshot['upstream'].get(key,'')) for key in ('repository','commit','upstream_version')}
    return result


class TeamConfig:
    def __init__(self,team_dir,bundled_root):
        raw_root=Path(team_dir).absolute()
        if _linked(raw_root):
            raise TeamConfigError('team 폴더는 심볼릭 링크나 연결 폴더일 수 없습니다.')
        self.root=raw_root.resolve()
        self.team_dir=self.root
        self.bundled_root=Path(bundled_root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        with _LOCKS_LOCK:
            self._lock=_LOCKS.setdefault(str(self.root).casefold() if os.name=='nt' else str(self.root),threading.RLock())
        manifest=self.bundled_root/'provenance/upstream-manifest.json'
        try:
            data=json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {}
        except (OSError,UnicodeError,ValueError):
            data={}
        self.upstream={key:str(data.get(key,'')) for key in ('repository','commit','upstream_version')}
        self._sources={item.get('snapshot'):item.get('source_url','') for item in data.get('files',[]) if isinstance(item,dict)}
        with self._exclusive():
            for path in DOCUMENTS:
                target=self._path(path)
                if not target.exists():
                    self._atomic(target,_encode(self._default(path)),replace=False)

    def _path(self,path):
        if not isinstance(path,str) or path not in DOCUMENTS:
            raise TeamConfigError('편집할 수 없는 문서 경로입니다. 기본 역할·방법 문서만 수정할 수 있습니다.')
        target=self.root/path
        self._check_path(target)
        return target

    def _check_path(self,target):
        if not target.resolve().is_relative_to(self.root):
            raise TeamConfigError('team 폴더 밖의 파일에는 접근할 수 없습니다.')
        for candidate in (target,*target.parents):
            if candidate==self.root:
                if _linked(candidate):
                    raise TeamConfigError('team 폴더의 연결 경로는 사용할 수 없습니다.')
                break
            if _linked(candidate):
                raise TeamConfigError('문서 경로의 심볼릭 링크나 연결 폴더는 사용할 수 없습니다.')

    @contextmanager
    def _exclusive(self):
        with self._lock:
            lock_dir=self.root/'.edit-lock'
            self._check_path(lock_dir)
            deadline=time.monotonic()+3
            while True:
                try:
                    guard=InstanceLock(lock_dir).acquire()
                    break
                except InstanceInUse:
                    if time.monotonic()>=deadline:
                        raise TeamConfigError('다른 창에서 팀 지침을 저장하고 있습니다. 잠시 후 다시 시도해 주세요.') from None
                    time.sleep(.05)
            try:
                yield
            finally:
                guard.release()

    def _read(self,path):
        target=self._path(path)
        try:
            with target.open('rb') as handle:
                raw=handle.read(MAX_DOCUMENT_BYTES+1)
            content=raw.decode('utf-8')
        except (OSError,UnicodeError):
            raise TeamConfigError(f'팀 문서를 UTF-8로 읽지 못했습니다: {path}') from None
        _encode(content)
        return raw,content

    def _document(self,path,include_content=True):
        raw,content=self._read(path)
        target=self._path(path)
        modified=datetime.fromtimestamp(target.stat().st_mtime,timezone.utc).isoformat()
        result={'path':path,**DOCUMENTS[path],'revision':_digest(raw),'bytes':len(raw),'modified_at':modified,'editable':True}
        if include_content:
            result['content']=content
        return result

    def list_documents(self):
        with self._exclusive():
            return [self._document(path,False) for path in DOCUMENTS]

    def get_document(self,path):
        with self._exclusive():
            return self._document(path)

    def save_document(self,path,content,expected_revision):
        raw=_encode(content)
        if not isinstance(expected_revision,str) or not re.fullmatch('[a-f0-9]{64}',expected_revision):
            raise TeamConfigError('저장할 문서의 기존 버전이 필요합니다. 문서를 다시 불러와 주세요.')
        with self._exclusive():
            target=self._path(path)
            previous,_=self._read(path)
            current=_digest(previous)
            if current!=expected_revision:
                raise TeamConfigConflict(current)
            if previous==raw:
                return dict(self._document(path),changed=False)
            total=len(raw)
            for other in DOCUMENTS:
                if other!=path:
                    total+=len(self._read(other)[0])
            if total>MAX_SNAPSHOT_BYTES:
                raise TeamConfigError('팀 지침 전체 크기는 1 MiB 이내여야 합니다.')
            backup=self.root/'.history'/Path(path).parent/(Path(path).stem+'-'+current+'.md')
            self._atomic(backup,previous,replace=False)
            # Recheck immediately before replacement, including external-editor changes.
            observed=_digest(self._read(path)[0])
            if observed!=current:
                raise TeamConfigConflict(observed)
            self._atomic(target,raw,replace=True)
            return dict(self._document(path),changed=True)

    def snapshot(self):
        with self._exclusive():
            # API saves are locked; a direct editor does not honor that lock.
            # A second pass prevents publishing a mixed set while it is changing.
            for _ in range(3):
                loaded={path:self._read(path) for path in DOCUMENTS}
                revisions={path:_digest(pair[0]) for path,pair in loaded.items()}
                if all(_digest(self._read(path)[0])==revision for path,revision in revisions.items()):
                    revision=_digest(json.dumps(revisions,sort_keys=True,separators=(',',':')).encode('utf-8'))
                    return validate_snapshot({'revision':revision,'documents':{path:pair[1] for path,pair in loaded.items()},
                                              'revisions':revisions,'upstream':self.upstream})
            raise TeamConfigError('팀 문서가 외부에서 변경 중입니다. 편집을 저장한 뒤 다시 분석을 시작하세요.')

    def _atomic(self,target,raw,replace):
        self._check_path(target)
        target.parent.mkdir(parents=True,exist_ok=True)
        self._check_path(target)
        descriptor,temp_name=tempfile.mkstemp(prefix='.team-write-',dir=target.parent)
        temp=Path(temp_name)
        try:
            with os.fdopen(descriptor,'wb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            self._check_path(target)
            if replace:
                os.replace(temp,target)
            else:
                # Link the fully written temporary file without overwriting an
                # existing edited default or an earlier immutable backup.
                try:
                    os.link(temp,target)
                except FileExistsError:
                    pass
        finally:
            if temp.exists():
                temp.unlink()

    def _source(self,path):
        candidate=self.bundled_root/path
        if not candidate.is_file():
            raise TeamConfigError(f'기본 팀 문서의 원본이 누락됐습니다: {path}')
        try:
            return candidate.read_text(encoding='utf-8')
        except (OSError,UnicodeError):
            raise TeamConfigError(f'기본 팀 문서의 원본을 읽지 못했습니다: {path}') from None

    def _default(self,path):
        packaged=self.bundled_root/'team'/path
        if packaged.resolve()!=self._path(path).resolve() and packaged.is_file():
            return packaged.read_text(encoding='utf-8')
        spec=DOCUMENTS[path]
        if spec['kind']=='reference':
            return self._source(path)
        if path=='common.md':
            source='provenance/upstream/fixed-role.txt'
            content=('## 모든 역할의 공통 분석 원칙\n\n'
                '- 사용자 질문, 분석 기간과 명시한 제약을 유지합니다.\n'
                '- 사실·계산 결과·가정·판단을 구분하고 출처와 기준 시점을 남깁니다.\n'
                '- 반대 근거, 불확실성, 판단을 바꿀 조건을 제시합니다.\n'
                '- 배정된 질문과 전문성에 집중하고 다른 담당자의 근거를 임의로 대체하지 않습니다.\n'
                '- 같은 담당자가 보완하고, 현재 채택된 근거만 결론에 사용합니다.\n'
                '- 이전 기록은 참고 맥락이며 현재 데이터나 새 실행 권한이 아닙니다.\n'
                '- 실제 실행되지 않은 조회·계산·백테스트·검토를 수행했다고 표현하지 않습니다.\n'
                '- 기본 응답 언어는 한국어입니다. 필요한 용어와 출처 명칭은 원문을 함께 씁니다.\n')
        elif spec['kind']=='role':
            source=f"provenance/upstream/{spec['role']}.txt"
            content=self._source(source)
            if spec['role']!='head-manager':
                match=re.search(r'developer_instructions\s*=\s*"""([\s\S]*?)"""',content)
                if not match:
                    raise TeamConfigError('기본 역할 원문에서 역할 지침을 찾지 못했습니다.')
                content=match.group(1).strip()+'\n'
        else:
            source='provenance/upstream/workflow.txt' if spec['role']=='head-manager' else f"provenance/upstream/method-{spec['role']}.txt"
            content=self._source(source) if spec['role']=='head-manager' else self._source(f"methods/{spec['role']}.md")
        origin=self._sources.get(source) or self.upstream.get('repository','')
        return (f"# {spec['title']}\n\n"
                '> 이 문서는 편집 가능한 연구 지침입니다. 저장 후 다음 분석부터 적용됩니다.\n'
                '> 원본의 Codex·MCP·파일·주문 절차는 웹앱에서 실제로 제공하는 연구 기능으로만 해석합니다.\n'
                '> 고정 역할 경계, 근거 채택, 독립 검토, 비매매 원칙과 실제 실행 권한은 이 문서로 변경되지 않습니다.\n\n'
                f"원본 기준: {self.upstream.get('commit','unknown')}\n출처: {origin}\n\n---\n\n"+content)
