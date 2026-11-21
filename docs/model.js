(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SatelliteMapLibrary = api;
})(typeof window === 'object' ? window : globalThis, () => {
  'use strict';
  const layers = ['land', 'water', 'both'];
  const prefixes = {land: 'Land', water: 'Water', both: 'Combined'};

  function createCatalog(data) {
    if (!data || !Array.isArray(data.sizes) || !Array.isArray(data.assets)) {
      throw new Error('Missing catalog');
    }
    const sizes = [...new Set(data.sizes)].filter(n => Number.isInteger(n) && n >= 512 && n <= 65536).sort((a, b) => a - b);
    const valid = new Set(sizes);
    const assets = new Map();
    const version = /^v\d+$/.test(data.version) ? data.version : 'v4';
    for (const asset of data.assets) {
      if (!layers.includes(asset.layer) || !valid.has(asset.size)) continue;
      const expected = `${prefixes[asset.layer]}_${version}_${asset.size}x${asset.size}.png`;
      if (asset.filename !== expected || (asset.width !== undefined && asset.width !== asset.size) ||
          (asset.height !== undefined && asset.height !== asset.size)) continue;
      if (asset.ready !== true || !Number.isSafeInteger(asset.bytes) || asset.bytes <= 0) continue;
      assets.set(`${asset.layer}:${asset.size}`, {...asset,
        url: `https://github.com/${data.repository}/releases/download/${encodeURIComponent(data.release)}/${encodeURIComponent(expected)}`});
    }
    function parseSize(value) {
      const raw = String(value).trim().replace(/\s/g, '');
      if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)$/.test(raw)) return null;
      const n = Number(raw.replace(/,/g, ''));
      return valid.has(n) ? n : null;
    }
    return {
      sizes, layers, parseSize,
      series: {
        standard: (data.standard || []).filter(n => valid.has(n)),
        thousands: (data.thousands || []).filter(n => valid.has(n))
      },
      fileFor: (layer, size) => assets.get(`${layer}:${size}`) || null,
      searchSizes: value => {
        const query = String(value).replace(/[\s,]/g, '').replace(/px$/i, '');
        return sizes.filter(n => String(n).includes(query));
      }
    };
  }
  return {createCatalog};
});
