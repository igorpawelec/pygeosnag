# Changelog

## 0.1.0 (unreleased)

First release: the detector frozen from the *Baza martwych drzew* research.

- Three band modes (RGB+NIR, CIR, RGB), each with its own adaptel granularity,
  feature set and random forest; the models ship as GitHub release assets and
  are downloaded on first use.
- Absolute probability threshold (default 0.5), merging of adjacent detections
  into objects, tiled processing with an overlap so no object is cut or
  written twice.
- Optional stand mask from forest-management polygons (age >= 10 years,
  -2 m buffer by default) and an optional object forest (RGBN mode).
- GeoPackage output with adaptel and object probabilities, area, shape,
  neighbouring-canopy descriptors, stand and nodata-edge flags; optional
  centroid layer and per-pixel probability raster.
- `geosnag detect` and `geosnag info` on the command line.
- `geosnag adapt`: refit the forest of a mode with labelled windows of a new
  scene (point layers of dead trees and of rejected objects), weighted; the
  result is used with `geosnag detect --model`.
