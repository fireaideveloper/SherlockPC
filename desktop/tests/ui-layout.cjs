const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');
(async () => {
 const http=require('http'),path=require('path');
 const root=path.resolve(__dirname,'../dist');
 const output=fs.mkdtempSync(path.join(require('os').tmpdir(),'sherlock-ui-'));
 const server=http.createServer((req,res)=>{const name=path.join(root,req.url==='/'?'index.html':req.url);res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.woff2')?'font/woff2':'text/html');try{res.end(fs.readFileSync(name))}catch{res.statusCode=404;res.end()}});await new Promise(resolve=>server.listen(4173,'127.0.0.1',resolve));server.unref();
 const browser = await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE||undefined,args:['--no-sandbox','--disable-gpu'],headless:true});
 const page = await browser.newPage();
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.addInitScript(fixture=>{
  const state=window.testState={fixture,cleared:false,opened:0,calls:[],generation:'initial'};
  window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
   state.calls.push([command,args]);
   if(command==='set_locale')return null;
   const storage=()=>({...fixture.overview.storage,state_count:state.cleared?0:47,generation:state.generation});
   const overview=()=>({...fixture.overview,storage:storage()});
   if(command==='monitor_status')return {ok:true,result:{overview:state.cleared?null:overview(),error:null}};
   if(command==='startup_status'||command==='set_startup_enabled')return {supported:true,enabled:args?.enabled??true,error:null};
   if(command==='refresh_state'){state.cleared=false;fixture.overview.current.state_id++;return overview();}
   if(command==='backend_call'){
    const p=args.payload;let result;
    if(p.action==='history_info')result=storage();
    if(p.action==='open_history_folder'){state.opened++;result=storage();}
    if(p.action==='history_page')result={...fixture.page,rows:state.cleared?[]:fixture.page.rows.slice(p.page*p.page_size,(p.page+1)*p.page_size),total:state.cleared?0:47,page:p.page,page_size:p.page_size,generation:state.generation};
    if(p.action==='investigate')result=fixture.investigation;
    if(p.action==='clear_history'){if(p.confirmed!==true)throw Error('Missing confirmation');state.cleared=true;state.generation='new';result={deleted_count:47,storage:storage()};}
    return {ok:true,result};
   }
   throw Error(command);
  }};
 },JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/ui.json'))));
 await page.goto('http://127.0.0.1:4173');
 await page.getByRole('button',{name:'Check memory',exact:true}).click();
 await page.getByRole('button',{name:'Investigate →',exact:true}).click();
 await page.getByText('Investigation result',{exact:true}).waitFor();
 const results=[];
 for(const [width,height] of [[820,640],[820,680],[1024,640],[1280,720],[1380,900],[1920,1080]]){
  await page.setViewportSize({width,height});
  for(const tab of ['Overview','Investigation','History','Settings']){
   await page.getByRole('navigation').getByRole('button',{name:new RegExp('^'+tab)}).click();
   if(tab==='History')await page.locator('tbody tr').first().waitFor();
   const inspect=async(label)=>{
    const result=await page.evaluate(()=>{
     const out=[];
     for(const el of document.querySelectorAll('.workspace button,.workspace h1,.workspace h2,.workspace p,.workspace input,.workspace table,.workspace .activity-row')){
      const r=el.getBoundingClientRect();if(!r.width||!r.height)continue;
      if(r.bottom>innerHeight-30||r.right>innerWidth||r.left<0)out.push({text:el.textContent?.slice(0,60),bottom:r.bottom,right:r.right});
      const panel=el.closest('.panel');if(panel&&r.bottom>panel.getBoundingClientRect().bottom+1)out.push({text:el.textContent?.slice(0,60),panelOverflow:true});
     }
     const table=document.querySelector('.history-panel table'),bottom=document.querySelector('.history-bottom');if(table&&bottom&&table.getBoundingClientRect().bottom>bottom.getBoundingClientRect().top)out.push({tableOverlapsPager:true});
     return {overflow:out,scroll:document.documentElement.scrollHeight>innerHeight||document.body.scrollHeight>innerHeight};
    });
    results.push({width,height,tab:label,...result});
   };
   if(tab==='Investigation')for(const name of ['Summary','Findings','Trace','Limits']){await page.getByRole('tab',{name,exact:true}).click();await inspect('Report '+name);}
   else await inspect(tab);
   if(width===1280&&height===720)await page.screenshot({ animations: 'disabled',path:path.join(output,`ui-${tab}.png`)});
  }
 }
 await page.getByRole('navigation').getByRole('button',{name:/^History/}).click();
 await page.getByRole('button',{name:'Open folder',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.testState.opened),1);
 await page.getByRole('button',{name:'Clear all states',exact:true}).click();
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.testState.cleared),false);
 await page.getByRole('button',{name:'Clear all states',exact:true}).click();
 await page.getByRole('button',{name:'Delete all states',exact:true}).click();
 await page.getByText('No saved states. Background collection will add new samples.',{exact:true}).waitFor();
 await page.waitForTimeout(1300);
 assert.equal(await page.locator('tbody tr').count(),0);
 await page.getByRole('button',{name:'↻ Refresh state',exact:true}).click();
 await page.locator('tbody tr').first().waitFor();
 fs.writeFileSync(path.join(output,'ui-results.json'),JSON.stringify({results,errors},null,2));
 console.log('Screenshots: '+output);
 console.log(JSON.stringify({checks:results.length,failures:results.filter(x=>x.scroll||x.overflow.length),errors},null,2));
 await browser.close();
 assert.equal(errors.length,0);
 assert.equal(results.filter(x=>x.scroll||x.overflow.length).length,0);
})().catch(e=>{console.error(e);process.exit(1)});
