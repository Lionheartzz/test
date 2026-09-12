import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){const r=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=preview-followup',...args],{env,encoding:'utf8'});process.stdout.write(r.stdout||'');process.stderr.write(r.stderr||'');if(r.status!==0||r.stdout?.includes('### Error'))throw Error('Browser regression failed: '+(r.error||r.status));}
cli('open','about:blank');
try{cli('run-code',readFileSync('tests/preview-followup.run.js','utf8').replaceAll('__PROJECT_ROOT__',process.cwd().replaceAll('\\','/')).replace('__DESIGN__',JSON.stringify(JSON.parse(readFileSync('tests/fixtures/route-cost-vs-proxy.json','utf8')))));}finally{cli('close');}
