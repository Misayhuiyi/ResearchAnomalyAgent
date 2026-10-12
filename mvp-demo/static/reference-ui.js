/* Local, explicit version comparison. No model calls or correctness verdict. */
(() => {
  const el=id=>document.getElementById(id);
  let preview=null,scan=null,uploading=false,comparing=false,download=null,generation=0;
  const panel=document.createElement('section');panel.className='materials';panel.id='referencePanel';
  panel.innerHTML='<div class="panel-body"><h3>与参考版本核对</h3><p>选择本次原表及你提供的参考文件，按编号或已确认的数据顺序列出差异。只说明两个版本不同，不自动判定哪一版正确。</p><div class="actions"><label>原表 <select class="select" id="referenceSourceFile"></select></label><label>参考文件 <input id="referenceFileInput" type="file" accept=".csv,.tsv,.xlsx,.xlsm"></label><button class="btn" id="referenceUpload">读取参考文件</button></div><div id="referenceMapping" class="hidden"><div class="actions"><label>原工作表 <select class="select" id="referenceSourceSheet"></select></label><label>参考工作表 <select class="select" id="referenceSheet"></select></label></div><p>勾选匹配编号（可多列），再选要核对的列。每个匹配编号必须唯一；参考列的默认对应请自行核对。</p><div style="overflow:auto;max-height:320px"><table><thead><tr><th>原列</th><th>对应参考列</th><th>作为匹配编号</th><th>核对数值</th></tr></thead><tbody id="referenceColumns"></tbody></table></div><p><label><input type="checkbox" id="referenceOrderConfirm"> 没有唯一编号时，我确认两个版本的数据顺序一致，按数据顺序核对。</label></p><button class="btn primary" id="referenceCompare">开始版本核对</button></div><p id="referenceMessage" role="status"></p><div id="referenceResults"></div></div>';
  el('resultView').append(panel);
  function busy(){el('referenceUpload').disabled=uploading||comparing||!scan||!el('referenceSourceFile').value;el('referenceCompare').disabled=uploading||comparing||!preview;for(const id of ['referenceSourceFile','referenceFileInput','referenceSourceSheet','referenceSheet','referenceOrderConfirm'])el(id).disabled=uploading||comparing;el('referenceColumns').querySelectorAll('input,select').forEach(x=>x.disabled=uploading||comparing);}
  async function request(url,body){const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{cache:'no-store'});let data;try{data=await response.json();}catch{throw Error('版本核对服务暂不可用，原检查结果不受影响。');}if(!response.ok||!data.ok)throw Error(data.error||'版本核对未完成。');return data;}
  function show(result){
    if(download){URL.revokeObjectURL(download);download=null;}
    if(!result){el('referenceResults').replaceChildren();return;}
    download=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
    const cells=result.differences.slice(0,100);
    el('referenceResults').innerHTML=`<h4>已对应的数据有 ${Number(result.differences_total)} 处差异</h4><p>对应 ${Number(result.matched_rows)} 行；未匹配 ${Number(result.unmatched_rows.length)} 行。${result.status==='partial'?'本次仅完成部分核对；未匹配的行不参与数值比较，不能视为一致。':''}</p><p>${escapeHtml(result.boundary)}</p><p><a class="btn" href="${download}" download="版本核对.json">下载完整核对记录</a></p><div style="overflow:auto;max-height:500px"><table id="referenceEvidence"><thead><tr><th>原文件位置</th><th>原值</th><th>参考文件位置</th><th>参考值</th></tr></thead><tbody>${cells.map(c=>`<tr><td>${escapeHtml(c.source.file)} · ${escapeHtml(c.source.sheet)} · 行 ${Number(c.source.row)} · ${escapeHtml(c.source.column)}（列 ${Number(c.source.column_idx)}）</td><td>${escapeHtml(c.source.value??'空值')}</td><td>${escapeHtml(c.reference.file)} · ${escapeHtml(c.reference.sheet)} · 行 ${Number(c.reference.row)} · ${escapeHtml(c.reference.column)}（列 ${Number(c.reference.column_idx)}）</td><td>${escapeHtml(c.reference.value??'空值')}</td></tr>`).join('')}</tbody></table></div>${result.unmatched_rows.length?`<p>未匹配位置（前20行）：${result.unmatched_rows.slice(0,20).map(r=>`${escapeHtml(r.side==='source'?result.source_file:result.reference_file)} 行 ${Number(r.row)}`).join('；')}。完整列表见 JSON。</p>`:''}<small>页面最多显示前 100 处；完整 JSON 最多保留 5000 处，超出时需拆分后核对。生成复核报告会收录最新版本核对，Excel 明细列出全部已保存差异。</small>`;
  }
  function mapping(){
    show(null);
    const left=preview.source_sheets.find(s=>s.sheet===el('referenceSourceSheet').value),right=preview.reference_sheets.find(s=>s.sheet===el('referenceSheet').value);
    if(!left||!right)return;
    el('referenceColumns').innerHTML=left.columns.map(c=>{
      const matches=right.columns.filter(r=>r.label===c.label),defaultIndex=matches.length===1?matches[0].index:right.columns.some(r=>r.index===c.index&&r.label===c.label)?c.index:-1;
      return `<tr data-reference-source="${c.index}"><td>${escapeHtml(c.label)}（列 ${c.index+1}）</td><td><select class="select" data-reference-target><option value="-1">请选择</option>${right.columns.map(r=>`<option value="${r.index}" ${r.index===defaultIndex?'selected':''}>${escapeHtml(r.label)}（列 ${r.index+1}）</option>`).join('')}</select></td><td><input type="checkbox" data-reference-key></td><td><input type="checkbox" data-reference-compare ${defaultIndex>=0?'checked':''}></td></tr>`;
    }).join('');
    el('referenceColumns').querySelectorAll('[data-reference-key]').forEach(box=>box.onchange=()=>{if(box.checked)box.closest('tr').querySelector('[data-reference-compare]').checked=false;});busy();
  }
  async function load(){
    generation++;const current=generation;scan=currentResult?.scan_id||null;preview=null;el('referenceMapping').classList.add('hidden');el('referenceFileInput').value='';show(null);
    const names=(currentResult?.materials||[]).map(m=>m.filename).filter(n=>/\.(csv|tsv|xlsx|xlsm)$/i.test(n));
    el('referenceSourceFile').innerHTML=names.map(n=>`<option>${escapeHtml(n)}</option>`).join('');el('referenceMessage').textContent=names.length?'参考版本核对不调用 AI，也不改变原检查结果。':'版本核对需要本次已上传的 CSV、TSV、XLSX 或 XLSM 表格。';busy();
    if(!scan)return;
    try{const data=await request('/api/reference/'+scan);if(generation===current)show(data.comparisons[0]);}catch(error){if(generation===current)el('referenceMessage').textContent=error.message;}
  }
  const renderSource=renderResult;renderResult=function(){renderSource();load();};
  const resetSource=resetResult;resetResult=function(){generation++;scan=null;preview=null;show(null);resetSource();busy();};
  el('referenceSourceFile').onchange=()=>{generation++;preview=null;show(null);el('referenceMapping').classList.add('hidden');busy();};
  el('referenceSourceSheet').onchange=mapping;el('referenceSheet').onchange=mapping;
  el('referenceUpload').onclick=async()=>{
    const file=el('referenceFileInput').files[0];if(!file){el('referenceMessage').textContent='请先选择参考文件。';return;}
    if(file.size>20*1024*1024){el('referenceMessage').textContent='参考文件不能超过 20 MB。';return;}
    const active=scan,current=++generation;uploading=true;busy();show(null);el('referenceMessage').textContent='正在读取参考文件…';
    try{
      const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('参考文件无法读取。'));reader.readAsDataURL(file);});
      const data=await request('/api/reference/preview',{scan_id:active,source_file:el('referenceSourceFile').value,filename:file.name,content_base64:encoded});
      if(scan!==active||generation!==current)return;preview=data.reference;
      for(const [id,sheets] of [['referenceSourceSheet',preview.source_sheets],['referenceSheet',preview.reference_sheets]])el(id).innerHTML=sheets.map(s=>`<option>${escapeHtml(s.sheet)}</option>`).join('');
      el('referenceMapping').classList.remove('hidden');el('referenceOrderConfirm').checked=false;mapping();el('referenceMessage').textContent='请核对工作表、列对应和匹配方式，再开始核对。';
    }catch(error){if(generation===current)el('referenceMessage').textContent=error.message;}finally{uploading=false;busy();}
  };
  el('referenceCompare').onclick=async()=>{
    if(!preview||comparing)return;
    const active=scan,current=generation,keys=[],columns=[];
    for(const row of el('referenceColumns').querySelectorAll('tr')){
      const pair={source:Number(row.dataset.referenceSource),reference:Number(row.querySelector('[data-reference-target]').value)};
      if(row.querySelector('[data-reference-key]').checked)keys.push(pair);
      if(row.querySelector('[data-reference-compare]').checked)columns.push(pair);
    }
    comparing=true;busy();el('referenceMessage').textContent='正在核对两个版本…';
    try{
      const data=await request('/api/reference/compare',{scan_id:active,reference_id:preview.reference_id,source_sheet:el('referenceSourceSheet').value,reference_sheet:el('referenceSheet').value,keys,columns,confirm_order:el('referenceOrderConfirm').checked});
      if(generation!==current)return;show(data.reference);el('referenceMessage').textContent='版本核对已保存。';window.dispatchEvent(new Event('reference-review-changed'));
    }catch(error){if(generation===current)el('referenceMessage').textContent=error.message;}finally{comparing=false;busy();}
  };
  busy();
})();
