// Static DOM contract tests. No browser or network access is used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const base = path.join(__dirname,'../dashboard/static');
const html = fs.readFileSync(path.join(base,'index.html'),'utf8');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.events={};this.dataset={};this.scrollTop=0;this.scrollLeft=0;this.offsetTop=0;this.classList={toggle(){}};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(key,value){this[key]=value;}
  addEventListener(name,handler){this.events[name]=handler;}
  focus(){}
  click(){this.clicked=true;}
  get firstElementChild(){return this.children[0];}
}
const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(match=>[match[1],new Element()]));
const created=[];
const table = new Element();
const requests=[];
const fields=['Research Focus','Key Findings','Device Type','Absorber Material','Absorber Material Term Used',
  'Absorber Dopant Material','Absorber Dopant Material Term Used','Absorber Dopant Polarity','Absorber Dopant Polarity Term Used',
  'Front Surface Morphology','Front Surface Morphology Term Used','Rear Surface Morphology','Rear Surface Morphology Term Used',
  'Front Surface Passivation Material','Front Surface Passivation Material Term Used','Rear Surface Passivation Material',
  'Rear Surface Passivation Material Term Used','Negative Metallization Material','Negative Metallization Material Term Used',
  'Positive Metallization Material','Positive Metallization Material Term Used','Efficiency (%)','Cell Area (cm2)',
  'Short-Circuit Current (A)','Short-Circuit Current Density (mA/cm2)','Open-Circuit Voltage (V)','Fill Factor (%)'];
const row=Object.fromEntries(fields.map(field=>[field,'N/A']));
Object.assign(row,{Title:'Paper <source>','Source PDF':'paper.pdf',Collections:'Si-PERC',Status:'partial','Filled Fields':'1','Device Type':'PERC'});
const snapshot={run_id:'run1',status:'interrupted',model:'gemma3:1b',field_columns:fields,columns:fields,
  corpus_count:60,run_total:60,processed:1,rows:[row],csv_available:true,can_resume:true,can_retry:true,
  active_run_id:null,csv_name:'pv_extraction_results.csv',message:'Resume to continue.',elapsed:10,
  papers:[{paper_id:'paper',title:row.Title,pdf_path:'paper.pdf',collections:['Si-PERC'],authors:[],status:'partial',
    row_index:0,chunk:3,chunks:3,selected_chunk:2}]};
const history={runs:[{run_id:'run1',status:'interrupted',processed:1,run_total:60}]};
let responseSnapshot=snapshot;
const context=vm.createContext({URLSearchParams,console,encodeURIComponent,setTimeout(){},
  document:{getElementById(id){assert(elements.has(id),`Unknown DOM id ${id}`);return elements.get(id);},
    createElement(tag){const element=new Element(tag);created.push(element);return element;},
    querySelector(selector){assert.equal(selector,'.table-scroll');return table;},activeElement:null},
  async fetch(url,options){requests.push({url,options});return {ok:true,async json(){return url==='/api/runs'?history:responseSnapshot;}};}
});
vm.runInContext(fs.readFileSync(path.join(base,'app.js'),'utf8'),context);
async function main(){
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements.get('processed').textContent,1);
  assert.equal(elements.get('paper-fields').textContent,'1 / 27');
  assert.equal(elements.get('resume').hidden,false);
  assert.equal(elements.get('download-paper').disabled,false);
  assert.equal(elements.get('values').children.reduce((sum,group)=>sum+group.children.length-1,0),27);
  assert.equal(elements.get('paper-title').textContent,'Paper <source>');
  elements.get('download-paper').events.click();
  assert.equal(created.at(-1).href,'/api/csv?run_id=run1&paper_id=paper');
  responseSnapshot={...snapshot,status:'running',active_run_id:'run1',can_resume:false,can_retry:false,
    papers:[{...snapshot.papers[0],status:'model',chunk:4,chunks:15,group:'Front surfaces'}]};
  await elements.get('resume').events.click();
  assert.equal(requests.at(-1).url,'/api/resume');
  assert.deepEqual(JSON.parse(requests.at(-1).options.body),{run_id:'run1'});
  assert.equal(elements.get('start').disabled,true);
  assert.equal(elements.get('paper-group').textContent,'Front surfaces');
  assert.equal(elements.get('paper-chunks').textContent,'4 / 15');
  console.log('Frontend contracts passed: all 27 fields, saved run, resume, group progress, CSV download, literal source text.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
