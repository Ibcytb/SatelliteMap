(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const format = n => Number(n).toLocaleString('ko-KR');
  const names = {land: '육지', water: '바다·물', both: '둘 다'};
  const bytes = n => n >= 1073741824 ? `${(n / 1073741824).toFixed(2)} GiB`
    : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MiB` : `${Math.ceil(n / 1024)} KiB`;
  let catalog;
  try { catalog = window.SatelliteMapLibrary.createCatalog(window.ATLAS_CATALOG); }
  catch (error) {
    $('status').hidden = false;
    $('status').textContent = '파일 목록을 불러오지 못했습니다. 새로고침해 주세요.';
    return;
  }

  const state = {layer: 'both', size: 4096, series: 'standard', zoom: 1, x: 0, y: 0};
  const lastSize = {standard: 4096, thousands: 1000};
  try {
    const savedSize = catalog.parseSize(localStorage.getItem('satellitemap-size'));
    const savedLayer = localStorage.getItem('satellitemap-layer');
    if (savedSize) state.size = savedSize;
    if (catalog.layers.includes(savedLayer)) state.layer = savedLayer;
  } catch (error) { /* Storage is optional. */ }
  state.series = catalog.series.standard.includes(state.size) ? 'standard' : 'thousands';
  lastSize[state.series] = state.size;
  $('size').value = state.size;

  function saveSelection() {
    try {
      localStorage.setItem('satellitemap-layer', state.layer);
      if (state.size) localStorage.setItem('satellitemap-size', String(state.size));
    } catch (error) { /* Private mode must not break downloads. */ }
  }

  function renderPresets() {
    document.querySelector('.preset-grid').replaceChildren(...catalog.series[state.series].map(size => {
      const button = document.createElement('button');
      button.className = 'preset';
      button.dataset.size = size;
      button.textContent = format(size);
      button.setAttribute('aria-label', `${format(size)} 픽셀`);
      button.setAttribute('aria-pressed', String(size === state.size));
      return button;
    }));
    document.querySelectorAll('[data-series]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.series === state.series));
    });
  }

  function updateDownload() {
    const file = catalog.fileFor(state.layer, state.size);
    $('size-error').hidden = state.size !== null;
    $('size-error').textContent = state.size === null ? '목록에 있는 크기를 입력하세요.' : '';
    $('size').setAttribute('aria-invalid', String(state.size === null));
    $('mirror-size').textContent = state.size ? format(state.size) : '—';
    $('output-size').textContent = state.size ? `${format(state.size)} × ${format(state.size)} px` : '—';
    $('file-bytes').textContent = file ? bytes(file.bytes) : '—';
    const link = $('export');
    link.setAttribute('aria-disabled', String(!file));
    link.tabIndex = file ? 0 : -1;
    if (file) {
      link.href = file.url;
      link.download = file.filename;
      link.setAttribute('aria-label', `${names[state.layer]} ${format(state.size)} × ${format(state.size)} 픽셀 PNG 다운로드`);
    } else {
      link.removeAttribute('href');
      link.removeAttribute('download');
      link.setAttribute('aria-label', 'PNG 다운로드');
    }
    $('status').hidden = !state.size || !!file;
    $('status').textContent = '선택한 파일을 준비하고 있습니다.';
    document.querySelectorAll('[data-size]').forEach(button => {
      button.setAttribute('aria-pressed', String(Number(button.dataset.size) === state.size));
    });
    saveSelection();
  }

  function applyTransform() {
    const bounds = $('map-stage').getBoundingClientRect();
    const limitX = bounds.width * (state.zoom - 1) / 2;
    const limitY = bounds.height * (state.zoom - 1) / 2;
    state.x = Math.max(-limitX, Math.min(limitX, state.x));
    state.y = Math.max(-limitY, Math.min(limitY, state.y));
    $('map-transform').style.transform = `translate(${state.x}px, ${state.y}px) scale(${state.zoom})`;
    $('map-stage').classList.toggle('zoomed', state.zoom > 1);
    $('zoom-out').disabled = state.zoom <= 1;
    $('zoom-in').disabled = state.zoom >= 8;
    $('zoom-reset').disabled = state.zoom === 1 && state.x === 0 && state.y === 0;
  }

  function resetView() {
    state.zoom = 1;
    state.x = 0;
    state.y = 0;
    applyTransform();
  }

  function chooseLayer(layer) {
    if (!catalog.layers.includes(layer)) return;
    state.layer = layer;
    document.querySelector('.backgrounds').hidden = layer === 'both';
    document.querySelectorAll('[data-layer]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.layer === layer));
    });
    document.querySelectorAll('[data-preview]').forEach(button => {
      const selected = button.dataset.preview === layer;
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    for (const name of catalog.layers) $('preview-' + name).hidden = name !== layer;
    const image = $('preview-' + layer);
    if (!image.getAttribute('src')) image.src = image.dataset.src;
    $('preview-error').hidden = !image.complete || image.naturalWidth > 0;
    $('map-stage').setAttribute('aria-labelledby', 'tab-' + layer);
    resetView();
    updateDownload();
  }

  function chooseSize(value, replaceInput = true) {
    state.size = catalog.parseSize(value);
    if (state.size) {
      const series = catalog.series.standard.includes(state.size) ? 'standard' : 'thousands';
      lastSize[series] = state.size;
      if (series !== state.series) {
        state.series = series;
        renderPresets();
      }
    }
    if (replaceInput) $('size').value = state.size || value;
    updateDownload();
  }

  document.querySelectorAll('[data-layer], [data-preview]').forEach(button => {
    button.addEventListener('click', () => chooseLayer(button.dataset.layer || button.dataset.preview));
  });
  document.querySelector('.tabs').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const index = catalog.layers.indexOf(state.layer);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2
      : (index + (event.key === 'ArrowRight' ? 1 : -1) + 3) % 3;
    chooseLayer(catalog.layers[next]);
    $('tab-' + state.layer).focus();
  });
  document.querySelectorAll('[data-series]').forEach(button => {
    button.addEventListener('click', () => {
      state.series = button.dataset.series;
      const list = catalog.series[state.series];
      const size = list.includes(state.size) ? state.size : lastSize[state.series] || list[0];
      renderPresets();
      chooseSize(size);
    });
  });
  document.querySelector('.preset-grid').addEventListener('click', event => {
    const button = event.target.closest('[data-size]');
    if (button) chooseSize(button.dataset.size);
  });
  $('size').addEventListener('input', () => chooseSize($('size').value, false));
  $('export').addEventListener('click', event => {
    if ($('export').getAttribute('aria-disabled') === 'true') event.preventDefault();
  });
  document.querySelectorAll('.swatch').forEach(button => {
    button.addEventListener('click', () => {
      $('map-stage').dataset.bg = button.dataset.bg;
      document.querySelectorAll('.swatch').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
    });
  });

  $('zoom-in').addEventListener('click', () => { state.zoom = Math.min(8, state.zoom + .5); applyTransform(); });
  $('zoom-out').addEventListener('click', () => { state.zoom = Math.max(1, state.zoom - .5); applyTransform(); });
  $('zoom-reset').addEventListener('click', resetView);
  let drag = null;
  $('map-stage').addEventListener('pointerdown', event => {
    if (state.zoom === 1 || event.button !== 0 || event.target.closest('button')) return;
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY, startX: state.x, startY: state.y};
    $('map-stage').setPointerCapture(event.pointerId);
    $('map-stage').classList.add('dragging');
  });
  $('map-stage').addEventListener('pointermove', event => {
    if (!drag || drag.id !== event.pointerId) return;
    state.x = drag.startX + event.clientX - drag.x;
    state.y = drag.startY + event.clientY - drag.y;
    applyTransform();
  });
  function endDrag() { drag = null; $('map-stage').classList.remove('dragging'); }
  $('map-stage').addEventListener('pointerup', endDrag);
  $('map-stage').addEventListener('pointercancel', endDrag);
  $('map-stage').addEventListener('lostpointercapture', endDrag);
  $('map-stage').addEventListener('keydown', event => {
    if (event.target !== $('map-stage')) return;
    if (event.key === 'Escape' || event.key === '0') { resetView(); return; }
    if (state.zoom <= 1 || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    state.x += event.key === 'ArrowRight' ? -40 : event.key === 'ArrowLeft' ? 40 : 0;
    state.y += event.key === 'ArrowDown' ? -40 : event.key === 'ArrowUp' ? 40 : 0;
    applyTransform();
  });
  window.addEventListener('resize', applyTransform);

  function renderTable() {
    const sizes = catalog.searchSizes($('catalog-search').value);
    const rows = sizes.map(size => {
      const row = document.createElement('tr');
      const dimension = document.createElement('th');
      dimension.scope = 'row';
      dimension.textContent = format(size);
      row.append(dimension);
      for (const layer of catalog.layers) {
        const cell = document.createElement('td');
        const file = catalog.fileFor(layer, size);
        if (file) {
          const link = document.createElement('a');
          link.className = 'table-link';
          link.textContent = 'PNG';
          link.href = file.url;
          link.download = file.filename;
          link.dataset.downloadLayer = layer;
          link.dataset.downloadSize = size;
          link.setAttribute('aria-label', `${names[layer]} ${format(size)} 픽셀 PNG 다운로드`);
          const length = document.createElement('small');
          length.textContent = bytes(file.bytes);
          cell.append(link, length);
        } else {
          cell.className = 'pending';
          cell.textContent = '준비 중';
        }
        row.append(cell);
      }
      return row;
    });
    if (!rows.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 4;
      cell.textContent = '일치하는 크기가 없습니다.';
      row.append(cell);
      rows.push(row);
    }
    $('catalog-rows').replaceChildren(...rows);
  }
  $('catalog-search').addEventListener('input', renderTable);
  $('catalog-rows').addEventListener('click', event => {
    const link = event.target.closest('[data-download-layer]');
    if (link) {
      chooseSize(link.dataset.downloadSize);
      chooseLayer(link.dataset.downloadLayer);
    }
  });
  document.querySelectorAll('.map-image').forEach(image => {
    image.addEventListener('error', () => { if (!image.hidden) $('preview-error').hidden = false; });
    image.addEventListener('load', () => { if (!image.hidden) $('preview-error').hidden = true; });
  });

  renderPresets();
  chooseLayer(state.layer);
  renderTable();
})();
