const fs=require('fs'),path=require('path'),{spawnSync}=require('child_process');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.env.PAPER_AUDIT_VERIFICATION_DIR||path.join(root,'docs','verification','2026-09-30-current'));
if(!out.startsWith(path.join(root,'docs','verification')+path.sep))throw Error('Verification directory must be inside docs/verification.');
const base=process.env.DEMO_URL;
if(!base||!['127.0.0.1','localhost'].includes(new URL(base).hostname)||new URL(base).port==='8765')throw Error('Independent test server required.');
fs.mkdirSync(out,{recursive:true});
const runs=[];
for(const file of ['verify_simple_demo.cjs','verify_batch_demo.cjs','verify_materials_demo.cjs','verify_statistics_demo.cjs','verify_reviews_demo.cjs','verify_content_demo.cjs']){
  console.log('RUN '+file);const started=Date.now();
  const result=spawnSync(process.execPath,[path.join(__dirname,file)],{cwd:root,env:process.env,encoding:'utf8',timeout:300000});
  const output=(result.stdout||'')+(result.stderr||'');console.log(output);
  runs.push({file,exit_code:result.status,error:result.error?.message||null,duration_ms:Date.now()-started,output});
  if(result.status!==0)break;
}
const passed=runs.length===6&&runs.every(r=>r.exit_code===0);
fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify({at:new Date().toISOString(),base,passed,scope:'public website and model substituted; real engine, budget, local review and reports',runs},null,2));
fs.writeFileSync(path.join(out,'browser.log'),runs.map(r=>r.file+'\n'+r.output).join('\n'));
process.exitCode=passed?0:1;
