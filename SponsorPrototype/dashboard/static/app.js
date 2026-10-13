const $ = id => document.getElementById(id);
let state = null;
let selected = null;
let filter = 'All papers';
let followCurrent = true;
let busy = false;
let filterSignature = '';
let paperSignature = '';
const labels = {idle:'Ready', starting:'Starting', running:'Extracting', completed:'Completed', no_results:'No results', failed:'Failed', stopped:'Stopped', interrupted:'Interrupted', queued:'Queued', reading:'Reading PDF', model:'Model extracting', extracted:'Extracted', no_result:'No valid result'};
const node = (tag, text, className) => {const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(className)e.className=className; return e;};
function badge(id, status) {const e=$(id); e.textContent=labels[status]||status; e.className='status-pill'+(['running','starting','model','reading'].includes(status)?' active':['failed','interrupted'].includes(status)?' failed':'');}
function duration(seconds) {if(seconds<60)return `${seconds}s`; const minutes=Math.floor(seconds/60); return minutes<60?`${minutes}m ${seconds%60}s`:`${Math.floor(minutes/60)}h ${minutes%60}m`;}
function render() {
  if(!state)return;
  const active=['starting','running'].includes(state.status);
  $('start').disabled=active||busy||!state.corpus_count;
  $('start').textContent=['completed','no_results','failed','stopped','interrupted'].includes(state.status)?'Run again':'Start extraction';
  $('stop').disabled=!active||busy;
  $('download').disabled=!state.csv_available;
  badge('run-status',state.status);
  $('processed').textContent=state.processed;
  $('total').textContent=`/ ${state.papers.length} papers`;
  $('progress').max=state.papers.length||1;
  $('progress').value=state.processed;
  $('accepted').textContent=`${state.accepted} ${state.csv_available?'CSV':'accepted'} ${state.accepted===1?'row':'rows'}`;
  $('elapsed').textContent=state.started_at?duration(state.elapsed):'Not started';
  $('result-count').textContent=state.rows.length;
  $('run-message').textContent=state.message || (active?'Running locally with gemma3:1b.':'Ready to extract the downloaded papers.');
  $('log').textContent=state.log||'No extraction has started.';
  const collections=[...new Set(state.papers.flatMap(p=>p.collections))];
  $('collection-overview').replaceChildren(...collections.map(collection=>{const e=node('div',undefined,'collection-stat'); e.append(node('span',collection)); const value=node('div'); value.append(node('strong',state.papers.filter(p=>p.collections.includes(collection)).length),node('small','downloaded papers')); e.append(value,node('div',undefined,'collection-strip'));return e;}));
  const newFilterSignature=JSON.stringify([collections,filter]);
  if(filterSignature!==newFilterSignature){
    $('filters').replaceChildren(...['All papers',...collections].map(name=>{const b=node('button',name); b.setAttribute('aria-pressed',String(filter===name)); b.addEventListener('click',()=>{filter=name;followCurrent=false;selected=null;render();});return b;}));
    filterSignature=newFilterSignature;
  }
  const papers=state.papers.filter(p=>filter==='All papers'||p.collections.includes(filter));
  const previousSelected=selected;
  if(followCurrent&&state.current_id&&papers.some(p=>p.paper_id===state.current_id))selected=state.current_id;
  if(!papers.some(p=>p.paper_id===selected))selected=papers[0]?.paper_id;
  const newPaperSignature=JSON.stringify([selected,papers.map(p=>[p.paper_id,p.status])]);
  if(paperSignature!==newPaperSignature){
    const scroll=$('paper-list').scrollTop;const focusedId=document.activeElement?.dataset.paperId;
    $('paper-list').replaceChildren(...papers.map(p=>{const b=node('button',undefined,'paper-button'); b.dataset.paperId=p.paper_id;b.setAttribute('aria-pressed',String(p.paper_id===selected));b.setAttribute('aria-label',`${p.title}, ${labels[p.status]||p.status}`); const dot=node('span',undefined,`status-dot ${p.status}`);const content=node('span');const meta=node('span',undefined,'paper-meta');meta.append(node('span',p.collections.join(' · ')),node('span',labels[p.status]||p.status));content.append(node('span',p.title,'paper-name'),meta);b.append(dot,content);b.addEventListener('click',()=>{selected=p.paper_id;followCurrent=false;render();});return b;}));
    $('paper-list').scrollTop=scroll;
    if(focusedId)Array.from($('paper-list').children).find(b=>b.dataset.paperId===focusedId)?.focus({preventScroll:true});
    if(followCurrent&&selected!==previousSelected){
      const current=Array.from($('paper-list').children).find(b=>b.dataset.paperId===selected);
      if(current)$('paper-list').scrollTop=current.offsetTop-$('paper-list').firstElementChild.offsetTop;
    }
    paperSignature=newPaperSignature;
  }
  $('paper-count').textContent=`${papers.length} papers`;
  const paper=state.papers.find(p=>p.paper_id===selected);
  if(paper) {
    $('selected-collection').textContent=paper.collections.join(' · ');
    $('paper-title').textContent=paper.title;
    $('paper-author').textContent=(paper.authors||[]).slice(0,4).join(', ')+((paper.authors||[]).length>4?' et al.':'');
    $('paper-doi').hidden=!paper.doi;
    $('paper-doi').textContent=paper.doi?`DOI: ${paper.doi}`:'';
    // DOI is bibliographic content, never executable markup or an arbitrary URL.
    if(paper.doi)$('paper-doi').href=`https://doi.org/${encodeURI(paper.doi)}`;
    badge('paper-status',paper.status);
    $('paper-step').textContent=labels[paper.status]||paper.status;
    $('paper-chunks').textContent=paper.chunks?`${paper.chunk} / ${paper.chunks}`:'—';
    const finalRow=Number.isInteger(paper.row_index)?state.rows[paper.row_index]:null;
    const values=finalRow||paper.values||paper.candidate;
    const final=Boolean(finalRow||paper.values);
    $('output-title').textContent=final?'Extracted values':'Parsed model response';
    const candidateNote=paper.status==='no_result'?'Last parsed chunk · not accepted':['stopped','interrupted'].includes(paper.status)?'Last parsed chunk · run stopped':state.status==='failed'?'Last parsed chunk · run failed':'Latest parsed chunk · selection pending';
    $('output-note').textContent=finalRow?'From original CSV':paper.values?'Accepted by original extractor':paper.candidate?candidateNote:'';
    $('paper-fields').textContent=values?`${Object.values(values).filter(v=>v!=='N/A').length} / ${state.columns.length}`:'—';
    $('empty-output').hidden=Boolean(values);
    $('empty-output').textContent=paper.status==='model'?`Gemma is processing chunk ${paper.chunk} of ${paper.chunks}. Parsed values appear when the model response is accepted by the original parser.`:paper.status==='no_result'?'The original extractor did not accept a result for this paper. See the log and any reported parser error.':paper.status==='reading'?'PDFMiner is reading the paper before the original splitter prepares the model chunks.':'This paper has no extracted values yet. Start extraction to process the downloaded corpus.';
    $('values').replaceChildren(...(values?state.columns.map(key=>{const row=node('div',undefined,'value-row');row.append(node('span',key,'value-label'),node('span',values[key]??'N/A',`value-text${values[key]==='N/A'?' missing':''}`));return row;}):[]));
    $('paper-error').hidden=!paper.error;
    $('paper-error').textContent=paper.error?`Reported during extraction: ${paper.error}`:'';
  } else {
    $('paper-title').textContent='No downloaded papers';
    $('empty-output').textContent='Download the Zotero corpus before starting extraction.';
  }
  $('results-empty').hidden=state.csv_available;
  $('results-table').hidden=!state.csv_available;
  $('results-note').textContent=state.csv_available?`${state.rows.length} rows · ${state.columns.length} original columns · pv_extraction_results_ollama.csv`:'Results appear when the original extractor saves its CSV.';
  const tableScroll=document.querySelector('.table-scroll');const left=tableScroll.scrollLeft;const top=tableScroll.scrollTop;
  const head=node('tr');head.append(...state.columns.map(c=>node('th',c)));$('table-head').replaceChildren(head);
  $('table-body').replaceChildren(...state.rows.map(row=>{const tr=node('tr');tr.append(...state.columns.map(c=>node('td',row[c])));return tr;}));
  tableScroll.scrollLeft=left;tableScroll.scrollTop=top;
}
async function poll() {
  try {const response=await fetch('/api/state');if(!response.ok)throw new Error('Status unavailable');state=await response.json();$('connection').hidden=true;render();}
  catch { $('connection').textContent='Connection lost. Reconnecting to the local dashboard…';$('connection').hidden=false;$('start').disabled=true;$('stop').disabled=true; }
  setTimeout(poll,1500);
}
async function action(name) {
  if(busy)return;busy=true;$('action-error').hidden=true;render();
  try {const response=await fetch(`/api/${name}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const data=await response.json();if(!response.ok)throw new Error(data.error);state=data;if(name==='start'){followCurrent=true;selected=null;filter='All papers';}}
  catch(error){$('action-error').textContent=error.message;$('action-error').hidden=false;}
  finally{busy=false;render();}
}
$('start').addEventListener('click',()=>action('start'));
$('stop').addEventListener('click',()=>action('stop'));
$('download').addEventListener('click',()=>{const a=node('a');a.href='/api/csv';a.download='pv_extraction_results_ollama.csv';a.click();});
function view(results){$('results-panel').hidden=!results;$('extraction-panel').hidden=results;$('results-view').setAttribute('aria-pressed',String(results));$('extraction-view').setAttribute('aria-pressed',String(!results));}
$('results-view').addEventListener('click',()=>view(true));
$('extraction-view').addEventListener('click',()=>view(false));
poll();
