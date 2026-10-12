/* Offline guide/report links must resolve to retained local artifacts. */
const fs=require('fs'),path=require('path'),{pathToFileURL,fileURLToPath}=require('url'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.env.PAPER_CORPUS_RESULTS||'');
if(!out.startsWith(path.join(root,'test-results')+path.sep))throw Error('Local results required');
(async()=>{const browser=await chromium.launch({headless:true}),records=[];
 try{
  for(const file of [path.join(root,'test-corpus','测试集导航.html'),path.join(out,'测试结果总览.html')]){
   const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(pathToFileURL(file).href);const links=await page.locator('a').evaluateAll(a=>a.map(x=>x.href));let local=0;
   for(const link of links){if(link.startsWith('file:')){const target=fileURLToPath(link);if(!target.startsWith(root+path.sep)||!fs.existsSync(target))throw Error('Missing/outside local artifact: '+target);local++;}}
   if(await page.locator('table tr').count()!==13)throw Error('All 12 cases must be in the guide/result table');
   if(errors.length)throw Error(errors.join('; '));
   await page.screenshot({path:path.join(out,path.basename(file)+'.png'),fullPage:false});
   records.push({file,local_links_checked:local,passed:true});await page.close();
  }
 }finally{await browser.close()}
 fs.writeFileSync(path.join(out,'navigation-check.json'),JSON.stringify({at:new Date().toISOString(),records,passed:2,failed:0},null,2));
 console.log(JSON.stringify({passed:2,local_links:records.reduce((n,r)=>n+r.local_links_checked,0)}));
})().catch(e=>{console.error(e);process.exitCode=1});
