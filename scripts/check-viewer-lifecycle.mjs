// Reproducible real-browser regression using the project's existing CLI dependency.
import {build} from 'vite';
import {spawnSync} from 'node:child_process';
import {readFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
await build({configFile:false,build:{outDir:'output/viewer-regression',emptyOutDir:false,
  lib:{entry:'tests/viewer-lifecycle.browser.js',name:'ViewerRegression',formats:['iife'],fileName:'viewer-regression'}}});
mkdirSync('output/playwright',{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){const result=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=viewer-regression',...args],{env,encoding:'utf8'});process.stdout.write(result.stdout||'');process.stderr.write(result.stderr||'');if(result.status!==0)throw Error('Browser regression CLI failed: '+result.status);}
cli('open','about:blank');
try{cli('run-code',readFileSync('tests/viewer-lifecycle.run.js','utf8').replaceAll('__PROJECT_ROOT__',process.cwd().replaceAll('\\','/')));}finally{cli('close');}
