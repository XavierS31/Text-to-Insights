const $ = id => document.getElementById(id);
let state = null;
let selected = null;
let filter = 'All papers';
let followCurrent = true;
let busy = false;
let filterSignature = '';
let paperSignature = '';
let initialView = true;
let showingResults = false;
let tableSignature = '';
const labels = {idle:'Ready', starting:'Starting', running:'Extracting', completed:'Completed', completed_with_issues:'Completed with issues', no_results:'No results', failed:'Failed', stopped:'Stopped', interrupted:'Interrupted', queued:'Queued', not_run:'Not run', reading:'Reading PDF', model:'Model extracting', extracted:'Extracted', partial:'Partial result', no_data:'No data', partial_no_data:'Partial · no data', no_text:'No readable text', no_result:'No valid result'};
const node = (tag, text, className) => {const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(className)e.className=className; return e;};
function badge(id, status) {const e=$(id); e.textContent=labels[status]||status; e.className='status-pill'+(['running','starting','model','reading'].includes(status)?' active':['failed','interrupted'].includes(status)?' failed':['partial','partial_no_data','completed_with_issues','no_data','no_text'].includes(status)?' warning':'');}
function duration(seconds) {if(seconds<60)return `${seconds}s`; const minutes=Math.floor(seconds/60); return minutes<60?`${minutes}m ${seconds%60}s`:`${Math.floor(minutes/60)}h ${minutes%60}m`;}
function render() {
  if(!state)return;
  const active=['starting','running'].includes(state.status);
  const fields=state.field_columns||state.columns;
  $('start').disabled=active||busy||!state.corpus_count;
  $('start').textContent=active?'Extracting…':`Extract all ${state.corpus_count} papers`;
  $('model-name').textContent=state.model;
  $('stop').disabled=!active||busy;
  $('download').disabled=!state.csv_available;
  badge('run-status',state.status);
  $('processed').textContent=state.processed;
  $('total').textContent=`/ ${state.run_total} ${state.run_total===1?'document':'documents'} in this run`;
  $('run-label').textContent=state.imported?'Saved CSV run':'Current run';
  $('progress').max=state.run_total||1;
  $('progress').value=state.processed;
  $('accepted').textContent=`${state.rows.length} saved ${state.rows.length===1?'row':'rows'}`;
  $('elapsed').textContent=state.imported?'Loaded from CSV':state.started_at?duration(state.elapsed):'Not started';
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
    $('start-selected').disabled=active||busy||!state.corpus_count;
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
    $('output-note').textContent=finalRow?`Saved CSV · chunk ${paper.selected_chunk||'—'}`:paper.values?'Saved by extractor':paper.candidate?candidateNote:'';
    $('paper-fields').textContent=values?`${fields.filter(key=>values[key]&&values[key]!=='N/A').length} / ${fields.length}`:'—';
    $('paper-review-note').hidden=!final;
    $('paper-review-note').textContent=paper.status==='partial'?'Some chunks failed validation. Populated values are model output awaiting source review.':'Model output awaiting source review. N/A means unavailable or rejected by validation.';
    $('empty-output').hidden=Boolean(values);
    $('empty-output').textContent=paper.status==='model'?`The model is processing chunk ${paper.chunk} of ${paper.chunks}. Finished paper rows are saved to CSV.`:paper.status==='no_result'?'No result was accepted for this paper. See the extraction issues and run log.':paper.status==='reading'?'Reading the PDF and preparing model chunks.':'This paper was not processed in the displayed run. Use Extract selected paper or Extract all papers to process it.';
    const groups=[['Research',fields.slice(0,2)],['Device and materials',fields.slice(2,9)],['Surfaces and contacts',fields.slice(9,21)],['Cell performance',fields.slice(21)]];
    $('values').replaceChildren(...(values?groups.map(([name,keys])=>{const section=node('section',undefined,'field-group');section.append(node('h4',name));section.append(...keys.map(key=>{const row=node('div',undefined,'value-row');row.append(node('span',key,'value-label'),node('span',values[key]??'N/A',`value-text${!values[key]||values[key]==='N/A'?' missing':''}`));return row;}));return section;}):[]));
    $('paper-diagnostics').hidden=!paper.error;
    $('paper-error').textContent=paper.error||'';
    $('paper-evidence').hidden=!paper.evidence||paper.evidence==='N/A';
    $('evidence-text').textContent=paper.evidence||'';
  } else {
    $('start-selected').disabled=true;
    $('paper-title').textContent='No downloaded papers';
    $('empty-output').textContent='Download the Zotero corpus before starting extraction.';
  }
  $('results-empty').hidden=state.csv_available;
  $('results-table').hidden=!state.csv_available;
  $('results-note').textContent=state.csv_available?`${state.rows.length} ${state.rows.length===1?'document':'documents'} with saved results · ${state.corpus_count} downloaded papers · ${state.csv_name}`:'Results appear as each paper is saved to CSV.';
  $('results-review').hidden=!state.csv_available;
  const notRun=state.papers.filter(p=>p.status==='not_run').length;
  $('results-review').textContent=`${notRun?`${notRun} downloaded papers were not processed in this run. `:''}These values are model output awaiting source review; partial results and missing measurements are retained in the CSV.`;
  const tableScroll=document.querySelector('.table-scroll');const left=tableScroll.scrollLeft;const top=tableScroll.scrollTop;
  const newTableSignature=JSON.stringify([selected,state.rows]);
  if(newTableSignature!==tableSignature){
    const head=node('tr');head.append(...['Paper','Collection','Extraction','Fields','Efficiency (%)'].map(c=>{const th=node('th',c);th.scope='col';return th;}));$('table-head').replaceChildren(head);
    $('table-body').replaceChildren(...state.rows.map((row,index)=>{const tr=node('tr');const source=state.papers.find(p=>p.row_index===index);const title=node('td');const button=node('button',row.Title||source?.title||`Paper ${index+1}`,'result-paper');button.setAttribute('aria-pressed',String(source?.paper_id===selected));button.addEventListener('click',()=>{if(source){selected=source.paper_id;followCurrent=false;filter='All papers';render();}});title.append(button);tr.append(title,node('td',row.Collections||source?.collections.join(' · ')||'—'),node('td',labels[row.Status||source?.status]||row.Status||'Saved'),node('td',`${row['Filled Fields']||fields.filter(key=>row[key]&&row[key]!=='N/A').length} / ${fields.length}`),node('td',row['Efficiency (%)']||'N/A'));return tr;}));
    tableSignature=newTableSignature;
  }
  tableScroll.scrollLeft=left;tableScroll.scrollTop=top;
}
async function poll() {
  try {const response=await fetch('/api/state');if(!response.ok)throw new Error('Status unavailable');state=await response.json();$('connection').hidden=true;if(initialView){view(state.csv_available);initialView=false;}render();}
  catch { $('connection').textContent='Connection lost. Reconnecting to the local dashboard…';$('connection').hidden=false;$('start').disabled=true;$('stop').disabled=true; }
  setTimeout(poll,1500);
}
async function action(name, body={}) {
  if(busy)return;busy=true;$('action-error').hidden=true;render();
  try {const response=await fetch(`/api/${name}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(data.error);state=data;if(name==='start'){followCurrent=true;selected=body.paper_id||null;filter='All papers';view(false);}}
  catch(error){$('action-error').textContent=error.message;$('action-error').hidden=false;}
  finally{busy=false;render();}
}
$('start').addEventListener('click',()=>action('start'));
$('start-selected').addEventListener('click',()=>{if(selected)action('start',{paper_id:selected});});
$('stop').addEventListener('click',()=>action('stop'));
$('download').addEventListener('click',()=>{const a=node('a');a.href='/api/csv';a.download=state.csv_name;a.click();});
function view(results){showingResults=results;$('results-panel').hidden=!results;$('filter-row').hidden=results;$('workspace').classList.toggle('result-detail',results);$('page-title').textContent=results?'Extraction results':'Paper extraction';$('results-view').setAttribute('aria-pressed',String(results));$('extraction-view').setAttribute('aria-pressed',String(!results));}
$('results-view').addEventListener('click',()=>view(true));
$('extraction-view').addEventListener('click',()=>view(false));
poll();
