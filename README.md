# pygeosnag

<img src="https://raw.githubusercontent.com/igorpawelec/pygeosnag/main/www/pygeosnag.png" align="right" width="200"/>

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**Standing dead trees on aerial orthophotos, as points — and the crowns grown from them.**

A raster goes in, one point per dead tree comes out, with a confidence. No seeds, no tree tops, no canopy height model. The points are seeds for the second step: `grow_crowns` grows each into a crown polygon with the seeded region growing of [pygeoadaptels](https://github.com/igorpawelec/pygeoadaptels) and a crown recipe.

## Install

```bash
conda install -c conda-forge numpy numba scipy scikit-learn joblib rasterio fiona shapely
pip install pygeoadaptels pygeopalette pygeosnag --no-deps
```

The models are release assets, not part of the wheel. They are downloaded on first use into `~/.cache/pygeosnag/` and verified against a manifest. Set `PYGEOSNAG_ASSETS` to a directory that already holds them to work offline.

## Use

```bash
geosnag detect ortho.tif -o trees.gpkg                       # 4 bands: R, G, B, NIR
geosnag detect cir.tif -o trees.gpkg --mode cir              # 3 bands: NIR, R, G
geosnag detect ortho.tif -o trees.gpkg --bands nir,red,green,blue
geosnag detect ortho.tif -o trees.gpkg --stands stands.gpkg  # keep points inside stands >= 10 years
geosnag grow ortho.tif trees.gpkg -o crowns.gpkg             # points -> crown polygons
geosnag info
```

```python
from pygeosnag import detect, grow_crowns
detect("ortho.tif", "trees.gpkg", stands="stands.gpkg")
grow_crowns("ortho.tif", "trees.gpkg", "crowns.gpkg")
```

The point layer `dead_trees` carries, per tree: `p` (the highest adaptel probability of the object), `p_mean`, `p_object` (the object forest, RGB+NIR only), `area_m2` and `n_adaptels` of the detected object, `in_stands`, `edge_px` (distance to nodata), `mode` and `model`.

## What to expect

Measured on seven Polish forest sites (13 255 reference tree tops, 0.25 m orthophotos, leaf-on), a point counted as a hit within 1.5 m of a top, with the site under test never seen in training:

| mode | bands | recall | precision against the reference |
|---|---|---|---|
| rgbn | R, G, B, NIR | 63% | 33% |
| cir | NIR, R, G | lower by ~15% | |
| rgb | R, G, B | lower by ~15% | |

The reference marks one top per tree and misses many dead trees: a field review of 60 points the detector placed without a reference top classified 42% as trees (25% clearly dead), 30% as roads, 20% as bare soil. Precision against the reference is therefore a floor; against the review it is 55–65%, and 64–75% with a stand mask. The points sit a median 0.47 m from the reference top.

Three things the detector does not do: it does not separate dead from dying trees (the labels do not), it does not know species, and it has not seen leaf-off imagery. A scene from a different camera, species or decay stage can transfer badly: the ranking of the points is usually still right and the scale is not, so a lower threshold is the first thing to try there.

## How it works

1. **Segmentation.** Adaptels at threshold 60 on the four bands, or at a threshold matched to the same granularity on three (RGB t40, CIR t50). Nodata is masked; adaptels smaller than 4 px are not scored.
2. **Features.** For NDVI, NDGR, NDBR, CIELCh lightness and chroma: mean, standard deviation and contrast to a 25 m box; hue as circular mean and variance; area; elongation. Without NIR there is no NDVI, without blue no NDBR; in the CIR mode the (NIR, R, G) triple goes through the RGB-to-CIELCh transform as if it were RGB.
3. **Forest.** One per mode, 200 trees, balanced subsampling, trained on ~2 million adaptels from seven sites.
4. **Threshold.** Absolute, p >= 0.5 by default; the useful range is 0.4–0.6. A per-scene quantile was tried and rejected: a scene without dead trees also has a top 1.5%.
5. **Points.** Adjacent adaptels above the threshold are merged; the point is the object's area-weighted centroid (it beats the highest-scoring and the brightest adaptel); the weaker of two points closer than 3 m is dropped. Tiles overlap by 200 px and a point is written from the tile whose core holds it.
6. **Optional.** A stand mask (polygons with a stand age field; stands of at least 10 years, shrunk by 2 m); the object forest (`p_object`, RGB+NIR).
7. **Crowns.** `grow_crowns` converts the mode's RGB-like trio to CIELAB and runs pygeoadaptels' `grow_seeds` with weights (0.5, 2.5, 1.0), a Delta-E tolerance of 15, a radius of 20 px and hole filling — the recipe worked out on a spruce plot with bleached snags.

Input at another pixel size is resampled to 0.25 m. 8-bit input is what the models saw; 16-bit values are scaled so their 99.9th percentile lands at 255, with a warning.

## Citing

The method and its evaluation are described in the research report of the *Baza martwych drzew* project; the underlying segmentation in:

> Pawelec, I., Hawryło, P., Netzel, P., & Socha, J. (2026). Standing dead tree detection from adaptel micro-segmentation of aerial orthophotos.

See `CITATION.cff`.

## License

GPL-3.0-or-later. Copyright Igor Pawelec.
