import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';

// Start scripts/phase4-isolated-server.py --data output/home-isolated --port 8766 first.
const base='http://127.0.0.1:8766',data=resolve('output/home-isolated');
if(!existsSync(resolve(data,'data/pmc_engineering.db')))throw Error('Start the isolated home test server first.');
const health=await (await fetch(base+'/api/health')).json();
if(health.service!=='pmc-manifold'||health.network?.urls?.[0]!==base)throw Error('Unexpected test service.');
const output=resolve('output/playwright/home-redesign').replaceAll('\\','/');mkdirSync(output,{recursive:true});
const env={...process.env,PWTEST_DAEMON_SESSION_DIR:resolve('output/playwright/daemon')};
function cli(...args){
  const result=spawnSync(process.execPath,['node_modules/@playwright/cli/playwright-cli.js','-s=home-acceptance',...args],{env,encoding:'utf8'});
  if(result.status!==0||result.error)throw Error(result.stderr||result.stdout||String(result.error));return result.stdout;
}
cli('open',base);
try{
  const source=readFileSync('tests/home-browser.run.js','utf8').replaceAll('__BASE_URL__',base).replaceAll('__OUTPUT_DIR__',output);
  const outputText=cli('run-code',source),match=outputText.match(/### Result\s*\n(\{[^\n]+\})/);
  if(!match){writeFileSync(resolve(output,'cli-output.txt'),outputText);throw Error(outputText.slice(-3000));}
  const result=JSON.parse(match[1]);writeFileSync(resolve(output,'acceptance.json'),JSON.stringify(result,null,2)+'\n');
  if(!result.passed)throw Error(`${result.stage}: ${result.error}`);
  console.log('Home browser acceptance passed: '+result.stages.join('; '));
}finally{cli('close');}
