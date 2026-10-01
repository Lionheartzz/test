// Requires the isolated QA server; the run code checks its health marker before writes.
import {spawnSync} from 'node:child_process';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const base=process.argv[2]||'http://127.0.0.1:8765',name=base.includes('127.0.0.1')?'localhost':'lan';
const output=resolve('output/playwright/rev2-runtime/'+name).replaceAll('\\','/');mkdirSync(output,{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/rev2-runtime-daemon')};
function cli(...args){const result=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=rev2-runtime',...args],{env,encoding:'utf8'});if(result.status!==0)throw Error(result.stdout+result.stderr);return result.stdout;}
cli('run-code','async page => {page.removeAllListeners("dialog");page.on("dialog",dialog=>dialog.accept().catch(()=>{}));return true;}');
cli('goto',base);cli('snapshot');
const code=readFileSync('tests/rev2-runtime-browser.run.js','utf8').replaceAll('__BASE_URL__',base).replaceAll('__OUTPUT_DIR__',output);
const result=cli('run-code',code);writeFileSync(output+'/cli-output.txt',result);const match=result.match(/### Result\s*\n(\{[^\n]+\})/);if(!match)throw Error(result.slice(-2000));
const data=JSON.parse(match[1]);writeFileSync(output+'/acceptance.json',JSON.stringify(data,null,2)+'\n');console.log(JSON.stringify(data));if(!data.passed)process.exitCode=1;
