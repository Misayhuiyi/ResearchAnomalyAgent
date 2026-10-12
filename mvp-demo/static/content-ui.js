/* Evidence-backed content review. Payment consent is always explicit. */
(() => {
  const box=document.createElement('section');box.className='materials';box.id='contentReview';
  box.innerHTML='<div class="panel-body"><h3>结合原文核对</h3><p id="contentMessage" role="status"></p><div id="contentRoles"></div><div id="contentScope"></div><p id="contentFees"></p><div class="actions"><button class="btn" id="prepareContent">查看范围与费用</button><button class="btn primary hidden" id="startContent">确认费用并开始</button><button class="btn hidden" id="quoteContent">查看追加费用</button><button class="btn hidden" id="cancelContent">停止内容核对</button></div><div id="contentEvidence"></div></div>';
  $('resultView').append(box);
  let state=null,scan=null,timer=null,working=false,signature='',grant=null;
  const money=v=>(Number(v||0)/1000000).toFixed(6).replace(/0+$/,'').replace(/\.$/,'');
  const e=escapeHtml;
  async function request(url,body){const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{cache:'no-store'});const d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'本次操作未完成。');return d.content}
  function render(){
    if(!state)return;
    const changed=JSON.stringify([state.status,state.next_step,state.cap_micros]);
    if(signature!==changed){signature=changed;window.dispatchEvent(new Event('content-review-changed'))}
    $('contentMessage').textContent=state.message||'可结合正文、主表和补充材料，核对数值对应关系与已有解释。';
    $('prepareContent').classList.toggle('hidden',state.status!=='not_started');$('prepareContent').disabled=working||!state.available;
    $('startContent').classList.toggle('hidden',!state.quote||!['awaiting_confirmation','paused'].includes(state.status));
    $('startContent').textContent=state.cap_micros?'确认追加费用并继续':'确认费用并开始';
    $('quoteContent').classList.toggle('hidden',!['awaiting_confirmation','paused'].includes(state.status)||!!state.quote||state.stopped||!!state.held_micros);
    $('cancelContent').classList.toggle('hidden',!['running','paused','awaiting_confirmation'].includes(state.status));
    for(const id of ['startContent','quoteContent','cancelContent'])$(id).disabled=working;
    $('contentRoles').querySelectorAll('select').forEach(select=>select.disabled=working||state.status!=='not_started');
    if(state.roles)$('contentRoles').querySelectorAll('select').forEach(select=>select.value=state.roles[select.dataset.file]);
    $('contentFees').textContent=state.budget_id?`本版累计授权：${money(state.cap_micros)} ${state.currency}；已记录：${money(state.spent_micros)}；待核对：${money(state.held_micros)}。本论文各版本累计已记录 ${money(state.paper_spent_micros)} ${state.currency}。${state.quote?`本次确认后本版累计最高 ${money(state.quote.cap_micros)} ${state.currency}。`:''}费用按配置单价保守估算，实际扣费以 DeepSeek 账单为准。`:'';
    $('contentScope').innerHTML=state.budget_id?`<p>将发送已读取的 ${Number(state.source_count)} 个片段给 DeepSeek V4.1 Flash，预计最多 ${money(state.estimated_max_micros)} ${e(state.currency)}；分批确认，未经确认不追加费用。</p><p>已完成 ${Number(state.next_step)} / ${Number(state.planned_calls)} 批。${e(state.boundary)}</p><details><summary>材料范围</summary>${state.coverage.map(c=>`<p>${e(c.file)}：${Number(c.source_count)} 个片段 ${e(c.reason||'')}</p>`).join('')}</details>`:'';
    const items=[];
    for(const step of state.outputs||[]){
      for(const item of step.suggestions){const title=currentResult?.findings?.find(f=>f.id===item.finding_id)?.title_cn||'原文依据';items.push(`<div class="material"><strong>${e(title)} · ${e(item.summary)}</strong>${item.citations.map(c=>`<small>${e(c.file)} · ${e(c.location)}</small><blockquote>${e(c.quote)}</blockquote>`).join('')}<small>请核对依据后，自行填写复核意见。</small></div>`)}
      for(const item of step.tool_results){if(!item.summary)continue;items.push(`<div class="material"><strong>${e(item.summary)}</strong>${(item.citations||[]).map(c=>`<small>${e(c.file)} · ${e(c.location)} · 原始值：${e(c.original)} ${e(c.unit)}</small>`).join('')}</div>`)}
    }
    $('contentEvidence').innerHTML=items.join('')||(state.status==='completed'?'<p>本次未形成有充分引用依据的建议，不代表论文不存在异常。</p>':'');
  }
  async function refresh(){const id=scan;if(!id)return;try{const value=await request('/api/content/'+id);if(id!==scan)return;state=value;render();if(state.status==='running')timer=setTimeout(refresh,1200)}catch(error){if(id===scan)$('contentMessage').textContent=error.message}}
  const previous=renderResult;renderResult=function(){previous();clearTimeout(timer);scan=currentResult.scan_id;state=null;signature='';grant=null;
    $('contentRoles').innerHTML=(currentResult.material_sources||[]).map(m=>`<label style="display:block;margin:8px 0">${e(m.filename)} <select class="select" data-file="${e(m.filename)}"><option value="">请选择用途</option><option value="body">论文正文</option><option value="table">主表</option><option value="supplement">补充材料</option></select></label>`).join('');
    $('contentMessage').textContent='正在读取内容核对状态…';$('contentEvidence').replaceChildren();$('contentFees').textContent='';$('contentScope').replaceChildren();refresh()};
  const reset=resetResult;resetResult=function(){clearTimeout(timer);scan=null;state=null;reset()};
  async function action(name,body){const id=scan;if(!id||working)return;working=true;render();try{const value=await request('/api/content/'+name,{scan_id:id,...body});if(id!==scan)return;state=value;render();if(state.status==='running'){clearTimeout(timer);timer=setTimeout(refresh,600)}}catch(error){if(id===scan)$('contentMessage').textContent=error.message}finally{working=false;if(id===scan&&state){$('prepareContent').disabled=!state.available;for(const el of ['startContent','quoteContent','cancelContent'])$(el).disabled=false}}}
  $('prepareContent').onclick=()=>{const roles={};for(const select of $('contentRoles').querySelectorAll('select')){if(!select.value){$('contentMessage').textContent='请先确认每份材料的用途。';return}roles[select.dataset.file]=select.value}action('prepare',{roles})};
  $('startContent').onclick=()=>{if(!state?.quote)return;if(!grant||grant.quote!==state.quote.quote_id)grant={quote:state.quote.quote_id,key:crypto.randomUUID()};action('start',{quote_id:grant.quote,request_key:grant.key,confirmed:true})};
  $('quoteContent').onclick=()=>action('quote',{});$('cancelContent').onclick=()=>action('cancel',{});
})();
