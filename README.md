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

Since assets-v2 the RGB+NIR and CIR forests are trained on spectral means standardised within each scene, and `detect` repeats that on your raster: a first pass over 16 tiles gathers the scene's medians and MADs of the five means, then every tile is scored on the standardised values (`--scene-norm auto`, the default; the manifest says which forests need it). This is what lets a forest trained on one set of flights score a flight with a different colour balance: the absolute means of a scene shift with the camera and the day, the contrast to the surrounding canopy does not. The calibrated cut for assets-v2 is `p >= 0.7` (`assets.operating_threshold()`; recall is flat from 0.6 to 0.8 while precision rises); `p_object` from the object forest is a second, stricter score -- on an unseen scene `p_object >= 0.4` roughly halves the false points at two thirds of the trees.

Since 0.3.2 there is a rescue for a scene where the forests see nothing at all: `--radiometry auto` compares the per-band 2nd and 98th percentiles of the sampled tiles with those of the training orthophotos and maps a hazy (dark end more than 15 DN above the reference) or flat (range below 0.7 of the reference) scene linearly onto the training range before segmentation. On a Radom 2017 pine scene the highest probability was 0.23 before and grey crowns passed 0.6 after. It is off by default for a reason: on 200 Polish scenes 44 met the trigger, 27 of them gained (mostly from zero), 17 lost nearly everything, because mapping the bands separately changes the band ratios the forests rely on. Run without it first; rerun with it on a scene that plainly holds dead trees and returned nothing.

## Use

```bash
geosnag detect ortho.tif -o trees.gpkg                       # 4 bands: R, G, B, NIR
geosnag detect cir.tif -o trees.gpkg --mode cir              # 3 bands: NIR, R, G
geosnag detect ortho.tif -o trees.gpkg --bands nir,red,green,blue
geosnag detect ortho.tif -o trees.gpkg --stands stands.gpkg  # keep points inside stands >= 10 years
geosnag detect ortho.tif -o trees.gpkg --chm chm.tif         # drop points with nothing taller than 3 m within 3 m (or --dsm/--dtm)
geosnag grow ortho.tif trees.gpkg -o crowns.gpkg             # points -> crown polygons
geosnag info
```

Without `--mode` or `--bands`, `detect` reads the band order off the raster: a 3-band file is CIR when its second band is the darkest over a sample of its pixels (vegetation absorbs red and reflects near infrared), else RGB; a 4-band file is NIR, R, G, B when its first band is the brightest, else R, G, B, NIR. The first log line says which; a CIR orthophoto read as RGB finds almost nothing.

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
4. **Threshold.** Absolute; the default is the operating point recorded in the models' manifest (p >= 0.7 for assets-v2, 0.5 for assets-v1), the useful range 0.6–0.8. A per-scene quantile was tried and rejected: a scene without dead trees also has a top 1.5%.
5. **Points.** Adjacent adaptels above the threshold are merged; the point is the object's area-weighted centroid (it beats the highest-scoring and the brightest adaptel); the weaker of two points closer than 3 m is dropped. Tiles overlap by 200 px and a point is written from the tile whose core holds it.
6. **Optional.** A stand mask (polygons with a stand age field; stands of at least 10 years, shrunk by 2 m); a height gate from a canopy height model or a DSM/DTM pair, a ground separator and nothing more: the height of a point is the maximum within 3 m, because an orthophoto and a height model rarely put the same crown in the same place, and a point with nothing taller than 3 m nearby is bare ground, a road or a shadow edge. Measured on six sites with GUGiK models of a vintage matched to the imagery: 0.5% of the reference tops dropped, F1 0.472 to 0.481 (a 2 m radius with a 5 m gate reaches 0.492 at 1.6% dropped); the height under the point itself would drop 18% of the reference tops. The model must not postdate the imagery, or it shows cleared stands where the dead trees stood. The Lasy Państwowe method of Onoszko gates at 10 m under the point; the object forest (`p_object`, RGB+NIR).
7. **Crowns.** `grow_crowns` grows every point into the pixels within 20 px that stay within a tolerance of the point's own signature in a feature space, and fills the holes. Since 0.4.0 the feature space is 100·NDVI and CIELAB lightness (tolerance 28 at the seed falling linearly to 12 at the radius since 0.4.1; CIELAB with a* weighted 2.5 and a flat tolerance of 15 when the raster has no NIR band) and the assignment rule is pygeosnag's within-reach kernel: a pixel goes to the seed within the radius and under the tolerance with the lowest minimax path cost. The previous recipe (pygeoadaptels' global IFT partition on weighted CIELAB, tolerance 15, cut by tolerance and radius afterwards) is kept as `rule="partition", space="lab_w"`. Benchmarked on 1200 verified crowns of 8 Polish sites with the detector's own points as competitors and the tolerance chosen on 6460 verified Giżycko crowns: median IoU 0.70 (79% above 0.5, over-segmentation 0.07, under-segmentation 0.13) against 0.53 (54%, 0.00, 0.38) for the previous recipe; Giżycko's dense bark-beetle clusters 0.56 against 0.34.

Input at another pixel size is resampled to 0.25 m. 8-bit input is what the models saw; 16-bit values are scaled so their 99.9th percentile lands at 255, with a warning.

## Citing

The method and its evaluation are described in the research report of the *Baza martwych drzew* project; the underlying segmentation in:

> Pawelec, I., Hawryło, P., Netzel, P., & Socha, J. (2026). Standing dead tree detection from adaptel micro-segmentation of aerial orthophotos.

See `CITATION.cff`.

## License

GPL-3.0-or-later. Copyright Igor Pawelec.
