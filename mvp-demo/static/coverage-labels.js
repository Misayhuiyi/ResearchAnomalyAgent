/* Reading paper text is not the same as checking its numerical tables. */
(() => {
  const original=renderCoverage;
  renderCoverage=function(){
    const status=original();
    for(const item of document.querySelectorAll('#materialsList .material')){
      const name=item.querySelector('strong')?.textContent;
      const material=currentResult?.materials?.find(m=>m.filename===name);
      if(!material||material.numeric_cells||!material.pdf_reading)continue;
      const badge=item.querySelector('.badge');
      if(material.pdf_reading.status==='text')badge.textContent='文字已读，数值表未读';
      if(material.pdf_reading.status==='scanned')badge.textContent='扫描件暂不支持';
      if(material.pdf_reading.status==='encrypted')badge.textContent='加密 PDF 未读取';
    }
    return status;
  };
})();
