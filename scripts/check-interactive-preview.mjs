import {spawnSync} from 'node:child_process';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const root=process.cwd().replaceAll('\\','/'),base='http://127.0.0.1:8765';
mkdirSync('output/playwright',{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){const r=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=interactive-preview',...args],{env,encoding:'utf8'});process.stdout.write(r.stdout||'');process.stderr.write(r.stderr||'');if(r.status!==0||r.stdout?.includes('### Error'))throw Error('Interactive preview browser regression failed: '+(r.error||r.status));return r.stdout||'';}
cli('open',base);
try{
  const source=readFileSync('tests/interactive-preview.run.js','utf8').replaceAll('__PROJECT_ROOT__',root).replaceAll('__BASE_URL__',base).replace('__DESIGN__',JSON.stringify(JSON.parse(readFileSync('tests/fixtures/interactive-preview.json','utf8'))));
  const output=cli('run-code',source),match=output.match(/### Result\s*\n(\{[^\n]+\})/);
  if(!match)throw Error('Interactive preview result was not returned');
  const result=JSON.parse(match[1]);if(!result.passed)throw Error(result.error||'Interactive preview failed');
  writeFileSync('docs/evidence/interactive-preview-browser.json',JSON.stringify(result,null,2)+'\n');
}finally{cli('close');}
