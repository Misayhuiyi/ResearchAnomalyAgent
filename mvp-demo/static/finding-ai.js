/* A single finding's optional, paid explanation. Deterministic results remain visible. */
(() => {
  const el = id => document.getElementById(id);
  let active = null;
  let quote = null;
  let busy = false;

  function exportsForResult() {
    if (!currentResult?.artifacts) return;
    el('jsonExportBtn').href = currentResult.artifacts.result_json || '#';
    el('jsonExportBtn').download = '筛查结果.json';
    el('engineReportBtn').href = currentResult.artifacts.raw_scan || '#';
  }
  new MutationObserver(exportsForResult).observe(el('resultView'), {attributes:true, attributeFilter:['class']});

  function render(ai) {
    if (!ai || !active) return;
    el('aiQuoteBtn').classList.toggle('hidden', ai.status === 'completed' || ai.status === 'running');
    const ready = ai.status === 'awaiting_confirmation' && Boolean(ai.quote);
    el('aiConfirmBtn').classList.toggle('hidden', !ready);
    quote = ready ? ai.quote : null;
    el('aiOutput').classList.toggle('hidden', ai.status !== 'completed');
    if (ai.status === 'completed' && ai.explanation) {
      const x = ai.explanation;
      el('aiWhat').textContent = x.what;
      el('aiWhy').textContent = x.why;
      el('aiBenign').textContent = x.benign_explanations.join('；');
      el('aiSteps').textContent = x.check_steps.join('；');
      el('aiSummary').textContent = x.report_summary;
      el('aiBoundary').textContent = x.disclaimer;
      el('aiStatus').textContent = '已保存本条线索的辅助解释；原始检查结果未改变。';
    } else if (ready) {
      const currency = ai.currency === 'USD' ? '美元' : '元';
      el('aiStatus').textContent = `本条预计费用上限：${(ai.estimated_max_micros / 1000000).toFixed(6)} ${currency}。确认后仅发送本条线索的少量证据。`;
    } else {
      el('aiStatus').textContent = ai.message || (ai.status === 'not_started' ? '尚未生成解释。' : '');
    }
  }
  async function request(path, body) {
    const response = await fetch(path, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || '解释暂不可用，仍可查看原检查结果。');
    return data.ai;
  }
  window.addEventListener('finding-selected', async event => {
    active = {scan:currentResult?.scan_id, finding:event.detail.id};
    quote = null;
    el('aiQuoteBtn').classList.remove('hidden');
    el('aiConfirmBtn').classList.add('hidden');
    el('aiOutput').classList.add('hidden');
    el('aiStatus').textContent = '正在读取已有解释…';
    exportsForResult();
    const selected = active;
    try {
      const response = await fetch(`/api/explanations/${encodeURIComponent(selected.scan)}/${encodeURIComponent(selected.finding)}`);
      const data = await response.json();
      if (active === selected) render(data.ai);
    } catch {
      if (active === selected) el('aiStatus').textContent = '解释服务暂不可用，原检查结果仍可正常查看。';
    }
  });
  el('aiQuoteBtn').addEventListener('click', async () => {
    if (!active || busy) return;
    busy = true; el('aiQuoteBtn').disabled = true;
    const selected = active;
    try {
      const ai = await request('/api/explanations/quote', {scan_id:selected.scan, finding_id:selected.finding});
      if (active === selected) render(ai);
    } catch (error) {
      if (active === selected) el('aiStatus').textContent = error.message;
    } finally { busy = false; el('aiQuoteBtn').disabled = false; }
  });
  el('aiConfirmBtn').addEventListener('click', async () => {
    if (!active || !quote || busy) return;
    const selected = active, approved = quote;
    busy = true; el('aiConfirmBtn').disabled = true;
    el('aiStatus').textContent = '正在生成解释，请勿重复提交。';
    try {
      const ai = await request('/api/explanations/run', {
        scan_id:selected.scan, finding_id:selected.finding,
        quote_id:approved.quote_id, request_key:crypto.randomUUID(), confirmed:true
      });
      if (active === selected) render(ai);
    } catch (error) {
      if (active === selected) el('aiStatus').textContent = error.message;
    } finally { busy = false; el('aiConfirmBtn').disabled = false; }
  });
})();
