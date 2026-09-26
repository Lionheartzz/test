import {spawnSync} from 'node:child_process';
import {readFileSync,readdirSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';

const base='http://127.0.0.1:8766',output=resolve('output/playwright/phase5-6').replaceAll('\\','/');
const saved=resolve('output/phase4-isolated/projects/saved');
const projects=readdirSync(saved).filter(name=>name.endsWith('.json')).map(name=>JSON.parse(readFileSync(resolve(saved,name),'utf8')));
const first=projects.find(row=>row.design?.name==='Two cavity interactive regression');
const second=projects.find(row=>row.design?.name==='Phase 5-6 isolated switch target');
if(!first?.id||!second?.id)throw Error('The two isolated browser fixture projects are missing.');
mkdirSync(output,{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){
  const result=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=phase5-6-isolated',...args],{env,encoding:'utf8'});
  if(result.status!==0||result.error)throw Error(result.stderr||result.stdout||String(result.error||result.status));
  return result.stdout||'';
}
cli('open',base);
try{
  const source=readFileSync('tests/phase5-6-browser.run.js','utf8')
    .replaceAll('__BASE_URL__',base).replaceAll('__FIRST_PROJECT__',first.id)
    .replaceAll('__SECOND_PROJECT__',second.id).replaceAll('__OUTPUT_DIR__',output);
  const result=cli('run-code',source),match=result.match(/### Result\s*\n(\{[^\n]+\})/);
  if(!match)throw Error('Browser result unavailable: '+result.slice(-2000));
  const data=JSON.parse(match[1]);
  writeFileSync(resolve(output,'acceptance.json'),JSON.stringify(data,null,2)+'\n');
  if(!data.passed)throw Error(`${data.stage}: ${data.error}`);
  process.stdout.write(`Phase 5/6 isolated browser acceptance passed: ${data.writes} non-render POST requests, ${data.renders} read-only paper renders.\n`);
}finally{cli('close');}
