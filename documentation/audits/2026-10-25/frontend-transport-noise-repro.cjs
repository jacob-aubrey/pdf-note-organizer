const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const tick = () => new Promise(resolve => setImmediate(resolve));
const source = fs.readFileSync('zotero-support/ui.js', 'utf8');
async function scenario(noise) {
  let output, killed = 0;
  const child = {stdin: {write: async () => {}}, stderr: {readString: () => new Promise(() => {})},
    stdout: {readString: () => new Promise(resolve => { output = resolve; })}, kill: async () => { killed++; }};
  const Zotero = {Prefs: {set() {}, get: name => name === 'notable.developmentWorker' ? '{"command":"synthetic","arguments":[]}' : false},
    Server: {init: async () => {}, port: 123}};
  const context = vm.createContext({setTimeout,clearTimeout,setInterval,clearInterval,Zotero,
    ChromeUtils: {importESModule: () => ({Subprocess: {call: async () => child}})}});
  vm.runInContext(source,context);
  const ui=context.NotableUI; ui.statePath='synthetic';ui.stopped=false;ui.message=()=>{};
  const request=ui.rpc('status').then(value=>({resolved:value}), error=>({rejected:error.message}));
  while (!ui.pending.size) await tick();
  const id=[...ui.pending.keys()][0];
  output(noise+JSON.stringify({id,result:{validPacket:true}})+'\n');
  const result=await request;
  await tick();
  const record={noise, ...result,killed,pending:ui.pending.size,processCleared:ui.process===null};
  if (!noise) {assert.equal(result.resolved.validPacket,true);assert.equal(killed,0);await ui.closeProcess(child,false);}
  else {assert.match(result.rejected,/helper stopped|invalid response/);assert.equal(killed,1);assert.equal(ui.process,null);}
  return record;
}
(async()=>{
 const data=JSON.parse(fs.readFileSync('documentation/audits/2026-10-25/pymupdf-stdout-repro.json','utf8'));
 const line=data.stdout.split(/\r?\n/).find(line=>line.startsWith('MuPDF error:'));
 const results=[];
 results.push(await scenario(''));
 results.push(await scenario(line+'\n\n'));
 const target=process.env.NOTABLE_REPRO_OUTPUT || 'documentation/audits/2026-10-25/frontend-transport-noise-repro.json';
 fs.writeFileSync(target,JSON.stringify({controllerSource:'zotero-support/ui.js',controller_sha256:crypto.createHash('sha256').update(source).digest('hex'),scenario:'Real controller launches synthetic process; real PyMuPDF diagnostic precedes valid matching response',results},null,2)+'\n');
 console.log(JSON.stringify(results,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
