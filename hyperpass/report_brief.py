"""Build the student-facing brief from the exact candidate submitted for review."""
import re
from datetime import date

SECTIONS = ("관측 사실", "해석", "판단을 바꿀 조건", "다음 확인 날짜 및 자료")
PROMPT = """
Start the candidate report with these exact four Korean Markdown headings:
## 관측 사실
## 해석
## 판단을 바꿀 조건
## 다음 확인 날짜 및 자료
For each observation use one bullet with an exact short verbatim excerpt from one
accepted producer's report, followed by [[artifact-id|YYYY-MM-DD]]. Use the observation
date actually documented on the same source line, or [[artifact-id|undated]].
Only cite current producers you have accepted, including producers accepted in this
decision. Do not pass inference, a forecast or a recommendation off as an observation.
Separate interpretation, testable reversal conditions, and next verification date and
material in the remaining headings; use 날짜 미정 when an event date is unknown.
Keep remaining analysis under its own Markdown heading. Review these sections as part
of the same candidate. Never invent a source, observation date or scheduled event.
"""
_REFERENCE = re.compile(r"(.+?)\s*\[\[([a-z0-9-]+)\|(undated|\d{4}-\d{2}-\d{2})\]\]$")
_EMPTY = ("채택된 분석 근거에서 원문을 대조할 수 있는 관측값이 없습니다.",
          "별도로 작성된 해석이 없습니다.", "검토한 자료에서 구체적인 반증 조건을 정하지 못했습니다.",
          "다음 확인 날짜와 자료가 정해지지 않았습니다.")


def _fact(line, artifacts):
    match = _REFERENCE.fullmatch(line)
    if not match:
        return None
    quote, key, at = match.groups()
    quote = quote.strip().strip('“”‘’"\'').strip()
    artifact = artifacts.get(key)
    if not artifact:
        return None
    source_lines = [s for s in artifact["report"].splitlines() if quote in s]
    if not source_lines:
        return None
    try:
        dated = at != "undated" and date.fromisoformat(at) and any(at in s for s in source_lines)
    except ValueError:
        dated = False
    return f"{quote} · {'관측일 ' + at if dated else '관측일 미확인'} · [근거 {key}](#{key})"


def student_brief(candidate, producers):
    by_id = {a["id"]: a for a in producers}
    groups = {heading: [] for heading in SECTIONS}
    body, section = [], None
    for line in candidate.splitlines():
        heading = re.fullmatch(r"#{1,6}\s+(.+?)\s*", line)
        if heading:
            section = heading[1] if heading[1] in groups else None
            if section:
                continue
        if section is None:
            body.append(line)
        elif line.strip():
            groups[section].append(re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line).strip())
    facts = [_fact(line, by_id) for line in groups[SECTIONS[0]]]
    groups[SECTIONS[0]] = [fact for fact in facts if fact]
    if not groups[SECTIONS[0]]:
        # The accepted analyst's own observation record is also part of the reviewed input.
        for artifact in producers:
            for item in artifact.get("observations", [])[:3]:
                if not item["statement"].strip() or not item["source"].strip():
                    continue
                excerpt = f"{item['statement']} · {item['source']}"
                at = item['as_of'] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", item['as_of']) else "undated"
                fact = _fact(f"{excerpt} [[{artifact['id']}|{at}]]", by_id)
                if fact and fact not in groups[SECTIONS[0]] and len(groups[SECTIONS[0]]) < 5:
                    groups[SECTIONS[0]].append(fact)
    if any(fact is None for fact in facts):
        groups[SECTIONS[0]].append("근거 원문과 대조할 수 없는 관측 항목은 보류했습니다.")
    gaps = list(dict.fromkeys(gap for a in producers for gap in a.get("missing_evidence", []) if gap))
    if gaps:
        if not groups[SECTIONS[-1]]:
            groups[SECTIONS[-1]].append("다음 확인 날짜 미정")
        groups[SECTIONS[-1]].append("채택된 분석에서 추가 확인이 필요한 자료 · " + ", ".join(gaps))
    blocks = []
    for heading, fallback in zip(SECTIONS, _EMPTY):
        items = groups[heading] or [fallback]
        blocks.append("## " + heading + "\n\n" + "\n".join("- " + item for item in items))
    return "\n\n".join(blocks), "\n".join(body).strip()
