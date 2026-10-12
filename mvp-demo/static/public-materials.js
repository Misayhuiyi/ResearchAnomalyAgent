/* Public-material entry shares the existing selection, limits and scan pipeline. */
async function materialRequest(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body), signal:controller.signal});
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || '获取未完成，可直接上传材料。');
    return data;
  } catch(error) {
    if(error.name === 'AbortError') throw new Error('获取材料超时，请重试或直接上传。');
    throw error;
  } finally { clearTimeout(timer); }
}

async function discoverMaterials() {
  if (busy || materialBusy) return;
  const reference = $('paperReference').value.trim();
  if (!reference) { $('sourceMessage').textContent='请输入 DOI 或论文链接。'; return; }
  materialBusy=true; updateControls();
  $('sourceResults').classList.add('hidden'); $('sourceCandidates').replaceChildren();
  $('sourceConfirm').checked=false; $('sourceMessage').textContent='正在查找公开材料…';
  try {
    const {discovery} = await materialRequest('/api/materials/discover', {reference});
    $('paperTitle').textContent=discovery.title;
    $('paperSource').href=discovery.source_url;
    $('sourceMessage').textContent=discovery.message;
    $('sourceResults').classList.remove('hidden');
    $('sourceConfirm').parentElement.classList.toggle('hidden', !discovery.candidates.length);
    for (const candidate of discovery.candidates) {
      const row=document.createElement('div'); row.className='source-item';
      row.innerHTML=`<div><strong>${escapeHtml(candidate.label)}</strong><small>${escapeHtml(new URL(candidate.url).hostname)}</small></div><button class="btn">加入材料</button>`;
      const button=row.querySelector('button');
      button.onclick=()=>importPublicMaterial(candidate, button);
      $('sourceCandidates').append(row);
    }
  } catch(error) { $('sourceMessage').textContent=error.message; }
  finally { materialBusy=false; updateControls(); }
}

async function importPublicMaterial(candidate, button) {
  if(busy || materialBusy || !$('sourceConfirm').checked) return;
  if(selectedFiles.length >= limits.files) { showError(`最多同时提交 ${limits.files} 份材料，请先移除部分文件。`); return; }
  materialBusy=true; updateControls(); $('sourceMessage').textContent='正在获取所选文件…';
  try {
    const {material} = await materialRequest('/api/materials/import', {url:candidate.url, confirmed:true});
    materialBusy=false;
    const file={name:material.filename, size:material.size, source_id:material.source_id, source_url:material.provenance.source_url};
    addFiles([file]);
    if(selectedFiles.includes(file)) {
      button.dataset.sourceId=material.source_id; button.textContent='已加入';
      $('sourceMessage').textContent=`已加入 ${file.name}，可继续补充材料或开始筛查。`;
    } else { $('sourceMessage').textContent='文件已获取，但未加入本次筛查。请检查下方提示。'; }
  } catch(error) { $('sourceMessage').textContent=error.message; }
  finally { materialBusy=false; updateControls(); }
}

$('discoverBtn').onclick=discoverMaterials;
$('paperReference').onkeydown=event=>{if(event.key==='Enter')discoverMaterials();};
$('paperReference').oninput=()=>{
  $('sourceResults').classList.add('hidden'); $('sourceCandidates').replaceChildren();
  $('sourceConfirm').checked=false; $('sourceMessage').textContent='';
};
$('sourceConfirm').onchange=updateControls;
