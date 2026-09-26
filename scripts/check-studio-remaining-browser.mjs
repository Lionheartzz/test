import {spawnSync} from 'node:child_process';
import {readFileSync,readdirSync,mkdirSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';

const base='http://127.0.0.1:8766';
const isolated=resolve('output/phase4-isolated'),saved=resolve(isolated,'projects/saved');
const output=resolve('output/playwright/studio-remaining').replaceAll('\\','/');
if(!existsSync(resolve(isolated,'data/pmc_engineering.db'))||!existsSync(saved))throw Error('Start the isolated test server first.');
const request=async(path,body)=>{
  const response=await fetch(base+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-PMC-Request':'local-console'},body:JSON.stringify(body)});
  const value=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(`${path}: ${response.status} ${JSON.stringify(value).slice(0,300)}`);
  return value;
};
const health=await request('/api/health');
if(health.service!=='pmc-manifold'||health.network?.urls?.[0]!==base)throw Error('Unexpected isolated service.');
const records=readdirSync(saved).filter(name=>name.endsWith('.json')).map(name=>JSON.parse(readFileSync(resolve(saved,name),'utf8')));
const pass=records.find(row=>row.design?.name==='Phase 4-6 PASS acceptance fixture');
if(!pass?.id)throw Error('Run check-remaining-browser.mjs to seed the isolated PASS fixture first.');
const project=await request('/api/projects/'+pass.id);
if(project.build?.status!=='PASS'||project.stale)throw Error('Isolated export fixture must have a current PASS build.');
const conflict=await request('/api/projects',{design:{name:'Phase 6 optimistic conflict fixture',block:{length:100,width:80,height:60,material:'S50C'}}});
const conflictId=conflict.project_id||conflict.id;
mkdirSync(output,{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){
  const result=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=studio-remaining-isolated',...args],{env,encoding:'utf8'});
  if(result.status!==0||result.error)throw Error(result.stderr||result.stdout||String(result.error||result.status));
  return result.stdout||'';
}
cli('open',base);
try{
  const source=readFileSync('tests/studio-remaining.run.js','utf8')
    .replaceAll('__BASE_URL__',base).replaceAll('__PASS_PROJECT__',pass.id)
    .replaceAll('__CONFLICT_PROJECT__',conflictId).replaceAll('__OUTPUT_DIR__',output);
  const result=cli('run-code',source),match=result.match(/### Result\s*\n(\{[^\n]+\})/);
  if(!match)throw Error('Browser result unavailable: '+result.slice(-2000));
  const data=JSON.parse(match[1]);writeFileSync(resolve(output,'acceptance.json'),JSON.stringify(data,null,2)+'\n');
  if(!data.passed)throw Error(`${data.stage}: ${data.error}`);
  process.stdout.write(`Studio isolated browser acceptance passed: ${data.stages.join(', ')}.\n`);
}finally{cli('close');}
