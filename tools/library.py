"""Shared, deterministic list of downloadable v4 maps."""
REPOSITORY = 'Ibcytb/SatelliteMap'
RELEASE = 'png-v4'
SOURCE_RELEASE = 'source-v4'
STANDARD = [512,1024,1536,2048,3072,4096,6144,8192,12288,16384,24576,32768,49152,65536]
THOUSANDS = list(range(1000,64001,1000))
SIZES = sorted(set(STANDARD + THOUSANDS))
LAYERS = {'land':'Land','water':'Water'}
assert len(SIZES) == 78

def filename(layer,size):
    return f'{LAYERS[layer]}_v4_{size}x{size}.png'

def asset_url(layer,size):
    return f'https://github.com/{REPOSITORY}/releases/download/{RELEASE}/{filename(layer,size)}'
