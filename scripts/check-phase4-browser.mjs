import {spawnSync} from 'node:child_process';
import {readFileSync,mkdirSync,writeFileSync,readdirSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';

const base='http://127.0.0.1:8766',output=resolve('output/playwright/phase4').replaceAll('\\','/');
const health=await fetch(base+'/api/health').then(response=>response.json());
if(health.service!=='pmc-manifold'||health.network?.urls?.[0]!==base)throw Error('Start the isolated acceptance service on 8766 first.');
const fixtureName='Phase 4-6 PASS acceptance fixture';
const saved=resolve('output/phase4-isolated/projects/saved');
if(!existsSync(saved)||!readdirSync(saved).some(name=>name.endsWith('.json')&&JSON.parse(readFileSync(resolve(saved,name),'utf8')).design?.name===fixtureName))
  throw Error('Seed the isolated PASS fixture with check-remaining-browser.mjs first.');
const savedDrawing=(()=>{
  const drawings=resolve('output/phase4-isolated/projects/drawings');
  if(!existsSync(drawings))return null;
  for(const project of readdirSync(drawings,{withFileTypes:true})){
    if(!project.isDirectory()||!existsSync(resolve('output/phase4-isolated/projects/saved',project.name+'.json')))continue;
    for(const drawing of readdirSync(resolve(drawings,project.name),{withFileTypes:true})){
      if(drawing.isDirectory()&&existsSync(resolve(drawings,project.name,drawing.name,'current.json')))
        return `${base}/drawing.html?project=${project.name}&drawing=${drawing.name}`;
    }
  }
  return null;
})();
mkdirSync(output,{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){
  const result=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=phase4-acceptance',...args],{env,encoding:'utf8'});
  if(result.status!==0||result.error)throw Error(result.stderr||result.stdout||String(result.error||result.status));
  return result.stdout||'';
}
cli('open',base);
try{
  const source=readFileSync('tests/phase4-browser.run.js','utf8').replaceAll('__BASE_URL__',base).replaceAll('__OUTPUT_DIR__',output).replaceAll('__SAVED_DRAWING_URL__',savedDrawing||'').replaceAll('__FIXTURE_NAME__',fixtureName);
  const result=cli('run-code',source),match=result.match(/### Result\s*\n(\{[^\n]+\})/);
  if(!match)throw Error('Browser result unavailable: '+result.slice(-2000));
  const data=JSON.parse(match[1]);
  writeFileSync(resolve(output,'acceptance.json'),JSON.stringify(data,null,2)+'\n');
  if(!data.passed)throw Error(data.error);
  process.stdout.write(`Phase 4 read-only browser acceptance passed: ${data.dimensions.length} screenshots, ${data.blockedWrites} write requests.\n`);
}finally{cli('close');}
