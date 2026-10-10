import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, cp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { once } from 'node:events';

async function until(check, diagnostic) {
  const deadline=Date.now()+30000;
  while(Date.now()<deadline) {
    try { if(await check()) return; } catch {}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.fail(diagnostic());
}

test('development server updates TS/CSS/HTML, preserves valid output on failure and stops', {timeout:90000}, async t => {
  const root=await mkdtemp(join(tmpdir(),'triage-admin-watch-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  await cp(new URL('../scripts',import.meta.url),join(root,'scripts'),{recursive:true});
  await mkdir(join(root,'src/styles'),{recursive:true});
  await writeFile(join(root,'tsconfig.json'),JSON.stringify({compilerOptions:{target:'ES2022',module:'ES2022',rootDir:'src',outDir:'dist/assets',strict:true},include:['src/**/*.ts']}));
  await writeFile(join(root,'src/main.ts'),'export const marker: string = "original";');
  await writeFile(join(root,'src/styles/site.css'),'body { color: red; }');
  await writeFile(join(root,'index.html'),'<html>Original shell</html>');
  const child=spawn(process.execPath,['scripts/dev.mjs'],{cwd:root,env:{...process.env,FRONTEND_PORT:'0'},stdio:['ignore','pipe','pipe']});
  let logs='';child.stdout.on('data',chunk=>logs+=chunk);child.stderr.on('data',chunk=>logs+=chunk);
  t.after(async()=>{if(child.exitCode===null && child.signalCode===null){const ended=once(child,'exit');child.kill('SIGTERM');await ended;}});
  await until(()=>/Dashboard available at http:\/\/localhost:\d+/.test(logs),()=>logs);
  const port=logs.match(/Dashboard available at http:\/\/localhost:(\d+)/)[1];
  const url=`http://127.0.0.1:${port}`;
  const read=async path=>(await fetch(url+path)).text();
  assert.match(await read('/assets/main.js'),/original/);
  assert.equal((await fetch(url+'/healthz')).status,200);
  assert.equal((await fetch(url+'/')).headers.get('cache-control'),'no-cache');
  await writeFile(join(root,'src/main.ts'),'export const marker: string = "updated";');
  await until(async()=>/updated/.test(await read('/assets/main.js')),()=>logs);
  await writeFile(join(root,'src/main.ts'),'export const marker: string = 123;');
  await until(()=>logs.includes('Dashboard build failed.'),()=>logs);
  assert.match(await read('/assets/main.js'),/updated/);
  await writeFile(join(root,'src/main.ts'),'export const marker: string = "recovered";');
  await until(async()=>/recovered/.test(await read('/assets/main.js')),()=>logs);
  await writeFile(join(root,'src/styles/site.css'),'body { color: blue; }');
  await until(async()=>/blue/.test(await read('/styles/site.css')),()=>logs);
  await writeFile(join(root,'index.html'),'<html>Updated shell</html>');
  await until(async()=>/Updated shell/.test(await read('/')),()=>logs);
  const ended=once(child,'exit');child.kill('SIGTERM');await ended;
  assert.equal(child.exitCode,0,logs);
  await assert.rejects(fetch(url+'/healthz')); // no orphaned server remains
});
