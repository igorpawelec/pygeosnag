# pygeosnag

<img src="https://raw.githubusercontent.com/igorpawelec/pygeosnag/main/www/pygeosnag.png" align="right" width="200"/>

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**Standing dead tree (snag) detection on aerial orthophotos, without seeds, tree tops or a canopy height model.**

A raster goes in, a GeoPackage of dead-crown polygons with a confidence score comes out. The detector is a frozen pipeline: adaptel micro-segmentation ([pygeoadaptels](https://github.com/igorpawelec/pygeoadaptels)), twenty spectral and contextual features per adaptel ([pygeopalette](https://github.com/igorpawelec/pygeopalette) for the colour transform), a random forest trained on seven Polish forest sites, an absolute probability threshold, merging into objects, and an optional stand mask and object forest.

## Install

```bash
conda install -c conda-forge numpy numba scipy scikit-learn joblib rasterio fiona shapely
pip install pygeoadaptels pygeopalette pygeosnag --no-deps
```

The models are release assets, not part of the wheel. They are downloaded on first use into `~/.cache/pygeosnag/` and verified against a manifest. Set `PYGEOSNAG_ASSETS` to a directory that already holds them to work offline.

## Use

```bash
geosnag detect ortho.tif -o snags.gpkg                          # 4 bands: R, G, B, NIR
geosnag detect cir.tif -o snags.gpkg --mode cir                 # 3 bands: NIR, R, G
geosnag detect ortho.tif -o snags.gpkg --bands nir,red,green,blue
geosnag detect ortho.tif -o snags.gpkg --stands stands.gpkg --stand-age 10 --stand-buffer -2
geosnag detect ortho.tif -o snags.gpkg --threshold 0.4 --prob-raster prob.tif --points
geosnag info
```

```python
from pygeosnag import detect
detect("ortho.tif", "snags.gpkg", stands="stands.gpkg")
```

The output layer `snags` carries, per object: `prob_max`, `prob_mean`, `prob_min` (adaptel probabilities), `area_m2`, `n_segments`, `elongation`, `ring_ndvi` and `ring_L` (the neighbouring canopy), `p_object` (the object forest, RGBN mode), `in_stands`, `edge_px` (distance to nodata), `mode` and `model`.

## What to expect

Measured on seven sites (13 255 reference trees, 0.25 m orthophotos, leaf-on) with the site under test never seen in training:

| mode | bands | recall | precision against the reference | estimated true precision |
|---|---|---|---|---|
| rgbn | R, G, B, NIR | ~65% | 31% | 55-64%, with a stand mask 64-75% |
| cir | NIR, R, G | lower by ~15% | | |
| rgb | R, G, B | lower by ~15% | | |

The reference marks one top per tree and misses many dead trees; a field review of 60 objects the detector found without a reference top classified 42% as trees (25% clearly dead), 30% as roads, 20% as bare soil. Precision against the reference is therefore a floor. The stand mask (`--stands`, polygons with a stand age field; stands of at least 10 years, shrunk by 2 m) removed a quarter of all objects and, on the reviewed sample, only roads and fields.

Three things the detector does not do: it does not separate dead from dying trees (the labels do not), it does not know species, and it has not seen leaf-off imagery. A scene from a different acquisition can transfer badly; a few labelled windows from that scene, added to the training table, recover most of the loss (see the adaptation notes in the research report).

## How it works

1. **Segmentation.** Adaptels at threshold 60 on the four bands, or at a threshold matched to the same granularity on three (RGB t40, CIR t50). Nodata is masked; adaptels smaller than 4 px are not scored.
2. **Features.** For NDVI, NDGR, NDBR, CIELCh lightness and chroma: mean, standard deviation and contrast to a 25 m box; hue as circular mean and variance; area; elongation. Without NIR there is no NDVI, without blue no NDBR; in the CIR mode the (NIR, R, G) triple goes through the RGB-to-CIELCh transform as if it were RGB.
3. **Forest.** One per mode, 200 trees, balanced subsampling, trained on ~2 million adaptels from seven sites.
4. **Threshold.** Absolute, p >= 0.5 by default; the useful range is 0.4-0.6. A per-scene quantile was tried and rejected: a scene without dead trees also has a top 1.5%.
5. **Objects.** Adjacent adaptels above the threshold are merged. Tiles overlap by 200 px and an object is written from the tile whose core holds its centroid.
6. **Optional stages.** Stand mask; object forest on the merged object's shape, scores and neighbouring canopy (`p_object`, RGBN only).

Input at another pixel size is resampled to 0.25 m. 8-bit input is what the models saw; 16-bit values are scaled so their 99.9th percentile lands at 255, with a warning.

## Citing

The method and its evaluation are described in the research report of the *Baza martwych drzew* project; the underlying segmentation in:

> Pawelec, I., Hawryło, P., Netzel, P., & Socha, J. (2026). Standing dead tree detection from adaptel micro-segmentation of aerial orthophotos.

See `CITATION.cff`.

## License

GPL-3.0-or-later. Copyright Igor Pawelec.
