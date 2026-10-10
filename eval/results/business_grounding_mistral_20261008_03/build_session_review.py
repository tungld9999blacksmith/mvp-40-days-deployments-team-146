"""Create a new offline review workbook from the completed session run."""
import csv
import hashlib
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "eval/results/agent_v2_1_business_sessions_mistral_20261008_03/comparison.json"
summaries = json.loads(SOURCE.read_text(encoding="utf-8"))
sessions = summaries[0]["sessions"]
assert len(sessions) == 20 and all(not session["error"] and len(session["turns"]) == 4 for session in sessions)


def escaped(value):
    return html.escape(str(value))


panels = []
rows = []
for session in sessions:
    panels.append(f'<h2>{escaped(session["session_id"])}</h2>')
    for turn in session["turns"]:
        key = f'{session["session_id"]}:{turn["turn"]}'
        last = turn["messages"][-1]
        original = last.get("response_metadata", {}).get("original_business_answer")
        original_html = f'<details><summary>Model output before runtime grounding</summary><pre>{escaped(original)}</pre></details>' if original is not None else ""
        state = {field: turn.get(field) for field in ("reminder_state_before", "reminder_state_after", "booking_count_before_confirm", "proposal_count")}
        controls = "".join(f'<label>{field}<select data-key="{escaped(key)}" data-field="{field}"><option value="">Unreviewed</option><option>pass</option><option>fail</option><option>unsure</option></select></label>' for field in ("correctness", "source_support", "task_success"))
        panels.append(f'<article><h3>Turn {turn["turn"]}</h3><p>{escaped(turn["user"])}</p><pre>{escaped(turn["answer"])}</pre>{original_html}<details><summary>Current-turn tools and effects</summary><pre>{escaped(json.dumps(turn["current_turn_calls"],ensure_ascii=False,indent=2))}</pre><pre>{escaped(json.dumps(state,ensure_ascii=False,indent=2))}</pre></details><div>{controls}<label>Notes<textarea data-key="{escaped(key)}" data-field="notes"></textarea></label></div></article>')
        rows.append([session["session_id"], turn["turn"], "", "", "", "", ""])

source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
document = '''<!doctype html><html lang="vi"><meta charset="utf-8"><title>Business grounding review</title>
<style>body{font:16px system-ui;max-width:1100px;margin:24px auto;padding:16px}article{border:1px solid #aaa;border-radius:8px;padding:20px;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f4f6;padding:12px}label{display:inline-grid;margin:8px}textarea{width:420px;max-width:80vw}header{position:sticky;top:0;background:white;padding:12px;border-bottom:1px solid #aaa}select,input,button{padding:8px}</style>
<header><h1>Review 20 phiên / 80 lượt — Agent M1</h1><p>Development fixture, chưa nghiệm thu. Đối chiếu câu trả lời với tool của lượt hiện tại; đọc đủ cả phiên. Không dùng tool lượt cũ để chứng minh cập nhật mới. RAG dùng fixture, không chứng minh retrieval thật.</p><label>Reviewer<input id="reviewer"></label><button id="export">Export review JSON</button><span id="count"></span></header>
''' + "\n".join(panels) + '''<script>
const sourceHash = "SOURCE_HASH";
const storageKey = "business-grounding-review-" + sourceHash;
let saved = JSON.parse(localStorage.getItem(storageKey) || '{"reviewer":"","labels":{}}');
const reviewer = document.getElementById('reviewer');
reviewer.value = saved.reviewer;
function persist(){localStorage.setItem(storageKey,JSON.stringify(saved));document.getElementById('count').textContent=Object.values(saved.labels).filter(r=>r.correctness&&r.source_support&&r.task_success).length+'/80 labelled';}
document.querySelectorAll('[data-key]').forEach(el=>{el.value=saved.labels[el.dataset.key]?.[el.dataset.field]||'';el.addEventListener('change',()=>{(saved.labels[el.dataset.key] ||= {})[el.dataset.field]=el.value;persist();});});
reviewer.addEventListener('change',()=>{saved.reviewer=reviewer.value;persist();});
document.getElementById('export').addEventListener('click',()=>{if(!reviewer.value.trim()){alert('Enter reviewer name first.');return;}const payload={source_sha256:sourceHash,scope:'development',reviewer:reviewer.value,exported_at:new Date().toISOString(),labels:saved.labels};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='business-grounding-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
persist();
</script></html>'''.replace("SOURCE_HASH", source_hash)
with (HERE / "session_review.html").open("x", encoding="utf-8") as stream:
    stream.write(document)
with (HERE / "session_turn_human_review.csv").open("x", encoding="utf-8", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["session_id", "turn", "correctness", "source_support", "task_success", "reviewer", "notes"])
    writer.writerows(rows)
with (HERE / "session_human_review.csv").open("x", encoding="utf-8", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["session_id", "correctness", "task_success", "source_support", "reviewer", "notes"])
    writer.writerows([session["session_id"], "", "", "", "", ""] for session in sessions)
print("Created review HTML, 80 blank turn rows and 20 blank session rows; no independent labels supplied.")
