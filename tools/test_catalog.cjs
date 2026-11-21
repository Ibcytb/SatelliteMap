const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createCatalog} = require('../docs/model.js');
const catalog = {
  repository: 'Ibcytb/SatelliteMap', release: 'png-v4', version: 'v4',
  sizes: [512, 1000, 1536, 65536], standard: [512, 1536, 65536], thousands: [1000],
  assets: ['Land', 'Water', 'Combined'].flatMap((prefix, index) =>
    [512, 1000, 1536, 65536].map(size => ({layer: ['land','water','both'][index], size,
      filename: `${prefix}_v4_${size}x${size}.png`, width: size, height: size, bytes: 100+size, ready: true})))
};

test('both resolves to one combined file, not two individual files', () => {
  const model = createCatalog(catalog);
  assert.equal(model.fileFor('both',1536).filename,'Combined_v4_1536x1536.png');
  assert.equal(model.fileFor('both',1536).url,
    'https://github.com/Ibcytb/SatelliteMap/releases/download/png-v4/Combined_v4_1536x1536.png');
  assert.notEqual(model.fileFor('both',512).url,model.fileFor('both',65536).url);
});

test('sizes accept comma-separated input and reject non-preset or malformed values', () => {
  const model = createCatalog(catalog);
  for (const value of ['65536','65,536',' 65 536 ']) assert.equal(model.parseSize(value),65536);
  for (const value of ['',null,'511','513','65537','5.12e2','1,5,36','-512','1536.5']) {
    assert.equal(model.parseSize(value),null,String(value));
  }
});

test('wrong file dimensions and filenames never become download links', () => {
  const damaged = structuredClone(catalog);
  damaged.assets[0].width = 1000;
  damaged.assets[1].height = 0;
  damaged.assets[2].filename = 'Land_v4_512x512.png';
  const model = createCatalog(damaged);
  assert.equal(model.fileFor('land',512),null);
  assert.equal(model.fileFor('land',1000),null);
  assert.equal(model.fileFor('land',1536),null);
  assert.ok(model.fileFor('land',65536));
});

test('missing or unfinished combined files cannot reuse a water URL', () => {
  const partial = structuredClone(catalog);
  partial.assets = partial.assets.filter(a => a.layer !== 'both' || a.size !== 512);
  partial.assets.find(a => a.layer === 'both' && a.size === 1536).ready = false;
  const model = createCatalog(partial);
  assert.equal(model.fileFor('both',512),null);
  assert.equal(model.fileFor('both',1536),null);
  assert.ok(model.fileFor('water',512));
});

test('search normalizes pasted dimensions and returns no rows for unknown values', () => {
  const model = createCatalog(catalog);
  assert.deepEqual(model.searchSizes('1,536 px'),[1536]);
  assert.deepEqual(model.searchSizes('99999'),[]);
  assert.deepEqual(model.searchSizes(''),catalog.sizes);
});
