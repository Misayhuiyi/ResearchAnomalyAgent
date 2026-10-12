/* Reviews remain separate from the immutable source result. No paid/model calls here. */
(() => {
  let review=null, loadingScan=null, saving=false, exporting=false, reportRequest=null;
  const drafts=new Map(), saveRequests=new Map();
  window.addEventListener('content-review-changed',()=>{reportRequest=null});
  const stateText={pending:'待复核',explained:'已有合理解释',further_check:'需要进一步核查'};
  const key=()=>crypto.randomUUID();
  const reviewBox=document.createElement('div');
  reviewBox.className='detail-block';
  reviewBox.innerHTML='<h4>我的复核</h4><label for="reviewState">复核状态</label> <select id="reviewState" class="select"><option value="pending">待复核</option><option value="explained">已有合理解释</option><option value="further_check">需要进一步核查</option></select><p><textarea id="reviewNote" rows="3" maxlength="2000" placeholder="填写核对依据或需要补充的材料" style="width:100%;box-sizing:border-box;font:inherit;padding:10px"></textarea></p><button class="btn primary" id="saveReview">保存复核</button> <button class="btn" id="refreshReview">刷新记录</button><p id="reviewMessage" role="status"></p>';
  $('detail').append(reviewBox);
  const reports=document.createElement('section'); reports.className='materials';
  reports.innerHTML='<div class="panel-body"><button class="btn" id="freezeReport">生成复核报告</button><p id="reportMessage" role="status"></p><div id="reportDownloads" class="actions"></div><details><summary>已生成的报告</summary><div id="reportHistory"></div></details></div>';
  $('resultView').append(reports);
  const cancelButton=document.createElement('button');cancelButton.id='cancelScan';cancelButton.className='btn';cancelButton.textContent='取消检查';$('jobStatus').append(cancelButton);
  cancelButton.onclick=async()=>{
    if(!currentJobId||!busy)return;
    cancelButton.disabled=true;
    try{const data=await request('/api/jobs/cancel',{job_id:currentJobId});setJobStatus(statusText(data.job.status),data.job.filename)}
    catch(error){showError(error.message)}finally{cancelButton.disabled=false}
  };
  async function request(url, body){
    const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{cache:'no-store'});
    const data=await response.json();
    if(!response.ok||!data.ok){const error=new Error(data.error||'本次操作未完成。');error.status=response.status;throw error}
    return data;
  }
  function identity(){return currentResult&&selectedFinding?currentResult.scan_id+'/'+selectedFinding:null}
  function stash(){const id=identity();if(id&&review){const value={state:$('reviewState').value,note:$('reviewNote').value},saved=review.reviews[selectedFinding]||{state:'pending',note:''};if(value.state===saved.state&&value.note===saved.note)drafts.delete(id);else drafts.set(id,value)}}
  function controls(){const ready=review&&review.scan_id===currentResult?.scan_id;$('saveReview').disabled=!ready||saving||!selectedFinding;$('refreshReview').disabled=saving;$('reviewState').disabled=!ready||saving;$('reviewNote').disabled=!ready||saving;$('freezeReport').disabled=!ready||saving||exporting}
  function showReview(){
    const id=identity(), saved=review?.reviews?.[selectedFinding]||{state:'pending',note:''}, value=drafts.get(id)||saved;
    $('reviewState').value=value.state;$('reviewNote').value=value.note;
    $('reviewMessage').textContent=review?'当前记录：'+stateText[saved.state]:'正在读取复核记录…';controls();
  }
  async function loadReview(){
    if(!currentResult)return;
    const scan=currentResult.scan_id;loadingScan=scan;review=null;controls();
    try{
      const data=await request('/api/reviews/'+scan);
      if(currentResult?.scan_id!==scan||loadingScan!==scan)return;
      review=data.review;
      $('reportHistory').innerHTML=data.reports.length?data.reports.map(item=>`<p>复核版本 ${Number(item.revision)} · ${escapeHtml(new Date(item.created_at).toLocaleString())} ${item.ready?['report.docx','report.pdf','details.xlsx'].map(name=>`<a href="/api/reports/${escapeHtml(item.report_id)}/${name}" download>${({ 'report.docx':'Word','report.pdf':'PDF','details.xlsx':'Excel' })[name]}</a>`).join(' · '):'生成未完成'}</p>`).join(''):'<p>尚未生成复核报告。</p>';
      showReview();
    }catch(error){if(currentResult?.scan_id===scan){$('reviewMessage').textContent=error.message;$('reportMessage').textContent=error.message;controls()}}
  }
  // Hook the existing workbench entry points so old-history and new scans share one flow.
  const renderSource=renderResult;
  renderResult=function(){review=null;reportRequest=null;$('reportDownloads').replaceChildren();$('reportMessage').textContent='';renderSource();loadReview()};
  const showSource=showFinding;
  showFinding=function(id){stash();showSource(id);showReview()};
  const resetSource=resetResult;
  resetResult=function(){stash();review=null;loadingScan=null;resetSource();controls()};
  $('reviewState').onchange=stash;$('reviewNote').oninput=stash;
  $('refreshReview').onclick=async()=>{stash();await loadReview()};
  $('saveReview').onclick=async()=>{
    if(!review||saving||!selectedFinding)return;
    stash();const id=identity(), scan=review.scan_id, finding=selectedFinding, draft=drafts.get(id)||review.reviews[selectedFinding]||{state:'pending',note:''};
    const content={scan_id:scan,finding_id:finding,state:draft.state,note:draft.note,revision:review.revision};
    const signature=JSON.stringify(content), prior=saveRequests.get(id);
    const operation=prior?.signature===signature?prior:{signature,key:key()};saveRequests.set(id,operation);
    saving=true;controls();
    try{
      const data=await request('/api/reviews',{...content,request_key:operation.key});
      drafts.delete(id);saveRequests.delete(id);
      if(currentResult?.scan_id===scan){review=data.review;if(selectedFinding===finding)showReview();$('reviewMessage').textContent='复核已保存。'}
    }catch(error){if(currentResult?.scan_id===scan)$('reviewMessage').textContent=error.message+' 未保存的说明已保留。'}
    finally{saving=false;controls()}
  };
  $('freezeReport').onclick=async()=>{
    if(!review||saving||exporting)return;
    if(Array.from(drafts.keys()).some(id=>id.startsWith(review.scan_id+'/'))){$('reportMessage').textContent='请先保存本次修改的复核意见，再生成报告。';return}
    const scan=review.scan_id, revision=review.revision;
    if(!reportRequest||reportRequest.scan_id!==scan||reportRequest.revision!==revision)reportRequest={scan_id:scan,revision,request_key:key()};
    exporting=true;controls();$('reportMessage').textContent='正在生成报告…';
    try{
      const data=await request('/api/reports',reportRequest);
      if(currentResult?.scan_id!==scan)return;
      $('reportMessage').textContent=`已生成复核版本 ${data.report.revision} 的报告。`;
      $('reportDownloads').innerHTML=Object.entries(data.report.downloads).map(([name,url])=>`<a class="btn" href="${escapeHtml(url)}" download>${({'report.html':'HTML','report.docx':'Word','report.pdf':'PDF','details.xlsx':'Excel明细'})[name]}</a>`).join('');
      await loadReview();
    }catch(error){if(currentResult?.scan_id===scan)$('reportMessage').textContent=error.message}
    finally{exporting=false;controls()}
  };
  fetch('/api/checks',{cache:'no-store'}).then(r=>r.json()).then(data=>{
    if(!data.ok)return;
    $('additionalChecks').innerHTML=data.checks.filter(item=>!['count_percent','sd_se'].includes(item.key)).map(item=>`<label><input type="checkbox" data-check="${escapeHtml(item.key)}"> ${escapeHtml(item.name)}</label><p>${escapeHtml(item.assumption)}</p>`).join('');updateControls();
  }).catch(()=>{$('additionalChecks').textContent='暂时无法读取更多核对项目。'});
  controls();
})();
