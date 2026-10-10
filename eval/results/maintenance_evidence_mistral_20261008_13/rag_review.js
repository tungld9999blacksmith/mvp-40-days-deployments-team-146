
const sourceHash="09024c2fce8415c0b502fdb0868a54b9bbdc7b1f32188a4d3cff23d1e7265512",storageKey="rag-maintenance-review-"+sourceHash;
let saved=JSON.parse(localStorage.getItem(storageKey)||'{"reviewer":"","labels":{}}');
const reviewer=document.getElementById('reviewer');reviewer.value=saved.reviewer;
function persist(){localStorage.setItem(storageKey,JSON.stringify(saved));document.getElementById('count').textContent=Object.values(saved.labels).filter(r=>r.correctness&&r.citation_support&&r.task_success).length+'/100 labelled';}
document.querySelectorAll('[data-key]').forEach(el=>{el.value=saved.labels[el.dataset.key]?.[el.dataset.field]||'';el.addEventListener('change',()=>{(saved.labels[el.dataset.key] ||= {})[el.dataset.field]=el.value;persist();});});
reviewer.addEventListener('change',()=>{saved.reviewer=reviewer.value;persist();});
document.getElementById('export').addEventListener('click',()=>{if(!reviewer.value.trim()){alert('Enter reviewer name');return;}const payload={source_sha256:sourceHash,scope:'development',reviewer:reviewer.value,exported_at:new Date().toISOString(),labels:saved.labels};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='rag-maintenance-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});persist();
