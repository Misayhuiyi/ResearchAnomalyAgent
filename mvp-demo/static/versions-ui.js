(() => {
  const bar=document.createElement('div');bar.className='panel-body';
  bar.innerHTML='<button class="btn" id="newMaterialVersion">补充或更正材料</button><div id="materialVersions"></div>';
  $('resultView').prepend(bar);
  const notice=document.createElement('p');notice.id='versionNotice';$('dropZone').before(notice);
  const resetNotice=()=>{notice.replaceChildren()};
  window.addEventListener('material-version-started',resetNotice);
  $('newMaterialVersion').onclick=()=>{
    if(busy||!currentResult)return;
    const parent=currentResult.scan_id;
    clearFile();versionParent=parent;submissionAttempt=null;
    notice.textContent='正在建立新版本：保留原材料，加入新上传的文件；同名文件在新版本中替换，旧版本不变。';
    const cancel=document.createElement('button');cancel.className='link-btn';cancel.textContent='取消新版本';
    cancel.onclick=()=>{versionParent=null;submissionAttempt=null;resetNotice()};notice.append(cancel);
    $('dropZone').scrollIntoView({behavior:'smooth',block:'center'});
  };
  const render=renderResult;renderResult=function(){render();const scan=currentResult.scan_id;
    fetch('/api/versions/'+scan,{cache:'no-store'}).then(r=>r.json()).then(data=>{
      if(currentResult?.scan_id!==scan||!data.ok)return;
      $('materialVersions').innerHTML=data.versions.map(v=>`<button class="link-btn" data-version="${escapeHtml(v.job_id)}" ${v.status!=='succeeded'?'disabled':''}>材料版本 ${Number(v.material_version||1)}${v.job_id===scan?'（当前）':''} · ${escapeHtml(statusText(v.status))}</button>`).join(' ');
      $('materialVersions').querySelectorAll('[data-version]').forEach(button=>button.onclick=()=>openJob(button.dataset.version));
    }).catch(()=>{$('materialVersions').textContent='暂时无法读取材料版本。'});
  };
  const load=loadJobs;loadJobs=async function(){await load();
    $('jobList').querySelectorAll('.job[data-job-id]').forEach(row=>{
      const job={job_id:row.dataset.jobId,status:row.dataset.jobStatus,filename:row.querySelector('strong').textContent};
      if(!['failed','cancelled'].includes(job.status))return;
      const button=document.createElement('button');button.className='link-btn';button.textContent='重新检查';button.dataset.retry=job.job_id;
      const key=crypto.randomUUID();
      button.onclick=async()=>{if(busy)return;busy=true;button.disabled=true;updateControls();
        try{const r=await fetch('/api/jobs/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({parent_scan:job.job_id,request_key:key})}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'重试未完成');
          currentJobId=d.job.job_id;showView('scan');setJobStatus('正在重新检查',job.filename);
          currentResult=await waitForJob(currentJobId);renderResult();
        }catch(error){showError(error.message)}finally{busy=false;button.disabled=false;$('jobStatus').classList.add('hidden');updateControls()}
      };row.append(button);
    });
  };
  $('refreshJobsBtn').onclick=loadJobs;
  $('resetBtn').onclick=()=>resetResult();
})();
