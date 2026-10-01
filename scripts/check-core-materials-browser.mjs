import {spawnSync} from 'node:child_process';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const base=process.argv[2]||'http://127.0.0.1:8765',name=base.includes('127.0.0.1')?'localhost':'lan';
const output=resolve('output/playwright/core-materials/'+name).replaceAll('\\','/');mkdirSync(output,{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/core-materials-daemon')};
function cli(...args){const r=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=core-materials',...args],{env,encoding:'utf8'});if(r.status!==0)throw Error(r.stdout+r.stderr);return r.stdout;}
cli('run-code','async page=>{page.removeAllListeners("dialog");page.on("dialog",dialog=>dialog.accept().catch(()=>{}));return true;}');
cli('goto',base);cli('snapshot');
const code=readFileSync('tests/core-materials-browser.run.js','utf8').replaceAll('__BASE_URL__',base).replaceAll('__OUTPUT_DIR__',output);
const result=cli('run-code',code);writeFileSync(output+'/cli-output.txt',result);const match=result.match(/### Result\s*\n(\{[^\n]+\})/);if(!match)throw Error(result.slice(-2500));
const data=JSON.parse(match[1]);writeFileSync(output+'/acceptance.json',JSON.stringify(data,null,2)+'\n');console.log(JSON.stringify(data));if(!data.passed)process.exitCode=1;
