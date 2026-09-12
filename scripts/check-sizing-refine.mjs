import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){const r=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=sizing-refine',...args],{env,encoding:'utf8'});process.stdout.write(r.stdout||'');process.stderr.write(r.stderr||'');if(r.status!==0||r.stdout?.includes('### Error'))throw Error('Browser regression failed');}
cli('open','about:blank');
try{cli('run-code',readFileSync('tests/sizing-refine.run.js','utf8').replaceAll('__PROJECT_ROOT__',process.cwd().replaceAll('\\','/')));}finally{cli('close');}
