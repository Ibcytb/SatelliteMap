(() => {
  'use strict';
  const $=id=>document.getElementById(id), fmt=n=>Number(n).toLocaleString('ko-KR');
  const data=window.ATLAS_CATALOG, names={land:'육지',water:'바다·물',both:'육지와 바다·물'};
  const assets=new Map(data.assets.map(a=>[a.layer+':'+a.size,a]));
  const validSizes=new Set(data.sizes);
  const state={layer:'water',preview:'water',series:'standard',zoom:1,selected:[]};
  const get=(layer,n)=>assets.get(layer+':'+n);
  const selectedLayers=()=>state.layer==='both'?['land','water']:[state.layer];
  const bytes=n=>n>=1073741824?(n/1073741824).toFixed(2)+' GB':n>=1048576?(n/1048576).toFixed(1)+' MB':Math.ceil(n/1024)+' KB';
  const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function available(a){return !!a&&a.ready===true&&Number.isInteger(a.bytes)&&a.bytes>0;}
  function url(a){
    // Build links only to this library's known Release, without a browser blob.
    return 'https://github.com/'+data.repository+'/releases/download/'+data.release+'/'+encodeURIComponent(a.filename);
  }
  function sizeValue(){const raw=$('size').value,n=Number(raw);return raw.trim()&&Number.isInteger(n)&&validSizes.has(n)?n:null;}
  try{const saved=Number(localStorage.getItem('satellitemap-size'));if(validSizes.has(saved))$('size').value=saved;}catch(e){}

  function showPresets(){
    const list=data[state.series],n=sizeValue();
    document.querySelector('.preset-grid').innerHTML=list.map(v=>`<button class="preset" data-size="${v}" aria-label="${fmt(v)} 픽셀" aria-pressed="${v===n}">${fmt(v)}</button>`).join('');
    document.querySelectorAll('[data-series]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.series===state.series)));
  }
  function update(){
    const n=sizeValue(),files=n?selectedLayers().map(l=>get(l,n)):[],ready=files.length&&files.every(available);
    $('size-error').textContent=n===null?'준비된 78개 크기 중에서 선택해 주세요.':'';
    $('size').setAttribute('aria-invalid',String(n===null));$('mirror-size').textContent=n?fmt(n):'—';
    $('output-size').textContent=n?`${fmt(n)} × ${fmt(n)} px`:'—';
    $('output-layer').textContent=state.layer==='both'?'육지 + 바다·물, 각각 1개':names[state.layer]+' 1개';
    $('file-bytes').textContent=ready?bytes(files.reduce((s,a)=>s+a.bytes,0)):'—';
    $('export').disabled=!ready;
    $('export-label').textContent=state.layer==='both'?'두 파일의 다운로드 보기':'PNG 다운로드';
    $('large-note').hidden=!n||n<16384;
    document.querySelectorAll('[data-size]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.size)===n)));
    if(n)try{localStorage.setItem('satellitemap-size',String(n));}catch(e){}
  }
  function preview(layer){
    state.preview=layer;state.zoom=1;
    document.querySelectorAll('[data-preview]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.preview===layer)));
    for(const k of ['land','water']){$('preview-'+k).hidden=k!==layer;$('preview-'+k).style.transform='scale(1)';}
    $('map-stage').setAttribute('aria-labelledby','tab-'+layer);$('map-caption').textContent=(layer==='land'?'LAND':'WATER')+' / v4';
  }
  document.querySelectorAll('[data-preview]').forEach(b=>b.onclick=()=>preview(b.dataset.preview));
  document.querySelector('.tabs').onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const n=state.preview==='land'?'water':'land';preview(n);$('tab-'+n).focus();}};
  document.querySelectorAll('[data-layer]').forEach(b=>b.onclick=()=>{state.layer=b.dataset.layer;document.querySelectorAll('[data-layer]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));if(state.layer!=='both')preview(state.layer);update();});
  document.querySelectorAll('[data-series]').forEach(b=>b.onclick=()=>{state.series=b.dataset.series;showPresets();});
  document.querySelector('.preset-grid').onclick=e=>{const b=e.target.closest('[data-size]');if(!b)return;$('size').value=b.dataset.size;update();};
  $('size').oninput=update;
  document.querySelectorAll('.swatch').forEach(b=>b.onclick=()=>{$('map-stage').dataset.bg=b.dataset.bg;document.querySelectorAll('.swatch').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));});
  function zoom(d){state.zoom=Math.max(1,Math.min(4,state.zoom+d));$('preview-'+state.preview).style.transform=`scale(${state.zoom})`;}
  $('zoom-in').onclick=()=>zoom(.5);$('zoom-out').onclick=()=>zoom(-.5);$('zoom-reset').onclick=()=>{state.zoom=1;zoom(0);};
  let timer;function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(timer);timer=setTimeout(()=>$('toast').hidden=true,5000);}
  function cards(files){
    state.selected=files;$('empty').hidden=files.length>0;$('queue-count').textContent=`${files.length}개 파일`;
    $('jobs').innerHTML=files.map(a=>`<article class="job"><div class="job-main"><div><div class="job-name">${escape(names[a.layer])} <span style="font-weight:400;color:#87927b">/ ${fmt(a.size)} px</span></div><div class="job-meta">${bytes(a.bytes)} · 투명 PNG · v4</div></div><div class="job-status"><span>준비 완료</span><a class="job-save" href="${url(a)}" download="${escape(a.filename)}" aria-label="${escape(names[a.layer])} ${fmt(a.size)} 픽셀 PNG 저장">저장 ↓</a></div></div></article>`).join('');
  }
  $('export').onclick=()=>{
    const n=sizeValue();if(!n)return;const files=selectedLayers().map(l=>get(l,n));if(!files.every(available))return;cards(files);
    if(files.length===1){const a=document.createElement('a');a.href=url(files[0]);a.download=files[0].filename;document.body.append(a);a.click();a.remove();toast('미리 준비된 PNG 다운로드를 시작합니다.');}
    else{$('queue-count').scrollIntoView({behavior:'smooth',block:'nearest'});toast('육지와 바다·물을 각각 저장해 주세요.');}
  };

  function table(){
    const search=$('catalog-search').value.replace(/[ ,]/g,'');
    $('catalog-rows').innerHTML=data.sizes.filter(n=>String(n).includes(search)).map(n=>`<tr><td>${fmt(n)} px</td>${['land','water'].map(layer=>{const a=get(layer,n);return available(a)?`<td><a class="table-link" href="${url(a)}" download="${escape(a.filename)}" aria-label="${escape(names[layer])} ${fmt(n)} 픽셀 다운로드">저장 ↓</a><small>${bytes(a.bytes)}</small></td>`:'<td><span class="pending">준비 중</span></td>';}).join('')}</tr>`).join('');
  }
  $('catalog-search').oninput=table;
  const readyCount=data.assets.filter(available).length;
  $('connection').hidden=data.complete&&readyCount===156;
  $('connection').textContent=`PNG 라이브러리를 준비하고 있습니다. ${fmt(readyCount)} / 156개 파일이 확인됐습니다. 준비된 크기는 바로 받을 수 있습니다.`;
  showPresets();update();table();
})();
