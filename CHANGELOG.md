# Changelog

## 0.3.1 — the auto band mode reads the band order off the raster

- With no `mode` and no `bands`, `detect` samples nine windows and looks
  at the band medians: a 3-band raster whose second band is the darkest
  is CIR (NIR, R, G), one whose second band is the brightest is RGB; a
  4-band raster whose first band is the brightest is NIR, R, G, B. The
  first log line names the decision and the medians. Before, three bands
  were always RGB, and a CIR orthophoto run that way found almost nothing
  (Ramsowo 2024: 4 points on a 600 m crop against 230 in the CIR mode).
  `modes.guess_band_order` holds the rule; `mode=` / `bands=` override it.

## 0.3.0 — assets v2 and scene normalisation

- **Models (assets-v2).** The three segment forests and the object forest
  are retrained on the full reference: the seven research sites plus
  Mieszkowice (RGBN, 2022, resampled 0.15 -> 0.25 m), and for the CIR mode
  also Lębork (CIR, 2021) and Giżycko (CIR mosaic, 6460 verified crowns).
  Labels changed: a positive is now a whole reference crown (an eCognition
  crown that holds a surveyed top; 11 480 crowns over nine sites), not just
  the adaptel under the top, so the forests see three times more positive
  rows and the object forest is trained on out-of-fold scores of complete
  windows. Białowieża (four rasters) was never trained on and is the
  external test.

- **Scene normalisation.** A scene-wide colour cast moved the absolute
  spectral means (`sr.NDVI`, `sr.NDGR`, `sr.NDBR`, `sr.L`, `sr.C`) of two
  sites to where the forests had learnt background: Mieszkowice's
  background sits at NDGR 0.20 and chroma 10 where every other site sits at
  0.06-0.10 and 6-8, and its dead crowns transferred at F1 0.12 although
  they separate from their own background better than anywhere else. The
  RGBN and CIR forests are therefore trained on those five means
  standardised within each scene (median and MAD over the scene's
  adaptels, label-free); the manifest says so (`feature_transform`), and
  `detect` repeats it on a new raster with a first pass over 16 tiles
  before scoring (`scene_norm="auto"`, `--scene-norm`, `--norm-tiles`).
  Leave-one-site-out over eight RGBN sites, blind threshold: F1 0.583 ->
  0.606, Mieszkowice 0.12 -> 0.61, Kudypy 0.24 -> 0.36 (Niedźwiedzi and
  Szczepanowo lose 0.13). The RGB mode is shipped without it: there the
  absolute means carry the signal (0.551 -> 0.515 with it). Dropping the
  means altogether (0.530) or keeping both versions side by side (0.589)
  was worse. Pixel-level colour transforms (CIELAB, LCHab hue) do not do
  this job: measured over ten scenes, hue is the least transferable
  feature of all, because canopy is near-achromatic.

- **Operating point.** With whole-crown labels the calibrated cut moved:
  the manifest's `operating_point.threshold` is 0.7 for assets-v2 (0.5 for
  assets-v1), `assets.operating_threshold()` reads it, and `detect` /
  `geosnag detect --threshold` default to it (None = manifest). On Białowieża
  (bpn, 2018 flight, 13 945 ALS-mapped dead crowns), v2 at 0.7 matches v1
  at 0.5 on the trees dead by the flight (recall 61%, precision floor 25-26%
  against an ALS reference that is not the image's reference), and the v2
  object forest now separates true from false objects on a scene it has
  not seen: `p_object >= 0.4` keeps 40% of the trees at 36% precision where
  v1 gives 27%; the v1 object forest was flat at 22% whatever the cut.

- `assets.manifest_entry(key)` returns an asset's manifest record;
  `assets.RELEASE` is `assets-v2` (publish the release before shipping, or
  point `PYGEOSNAG_ASSETS` at a folder with the v2 files).

- `detect_array(..., scene_norm=)` and `tile_features()` for callers that
  drive the pipeline window by window.

## 0.2.1 (unreleased)

- The height gate works again on rasterio 1.4 and newer. `Dataset.index`
  now coerces its result with `int()`, which raises `TypeError` on the
  coordinate arrays the sampler passes, so `detect(chm=...)` failed outright
  on a recent rasterio; the row and column now come from the inverse
  transform. Caught by the test suite on CI, where rasterio is current, and
  invisible locally on rasterio 1.3.

- Height gate: `detect(chm=...)` or `detect(dsm=..., dtm=...)` drops points
  with nothing taller than `min_height` (3 m) within `height_radius` (3 m) --
  bare ground, roads and shadow edges that share the colour of a dead crown --
  and writes the height as `height_m`; `keep_low` keeps them flagged. The
  maximum in a neighbourhood, not the height under the point: an orthophoto
  and a height model rarely put the same crown in the same place, and the
  height under the point would drop 18% of the reference tops. Measured on
  six sites with vintage-matched GUGiK models: 0.5% of reference tops
  dropped, F1 0.472 -> 0.481. The Lasy Państwowe method (Onoszko) gates at
  10 m with a normalised surface model. On the command line: `--chm`,
  `--dsm`/`--dtm`, `--min-height`, `--height-radius`, `--keep-low`.

## 0.2.0 — 2026-09-02

The product is a point per dead tree, and the crowns grown from it.

- `detect` writes one point per dead tree (layer `dead_trees`): the
  area-weighted centroid of the merged adaptels above the threshold, which
  measured against the reference tops beats the highest-scoring and the
  brightest adaptel (median 0.47 m off the top); the weaker of two points
  closer than 3 m is dropped (F1 0.424 -> 0.435 on seven sites). Polygons are
  no longer written.
- `grow_crowns` / `geosnag grow`: the points grown into crown polygons with
  pygeoadaptels' seeded region growing on CIELAB and the crown recipe
  (weights 0.5, 2.5, 1.0; Delta-E 15; 20 px; holes filled).
- Removed from the package: `adapt`, `score`, `extract` and their commands.
  Scene adaptation is the research side's job; those scripts live with the
  research now.
- A failed model download is a readable error naming the cache folder;
  `detect` takes a progress callback with cancel for GUI front ends.

## 0.1.0

First cut of the detector frozen from the *Baza martwych drzew* research:
three band modes with granularity-matched adaptel thresholds, the 20/17
feature set (bit-identical parity with the research cache), absolute
probability threshold, tiled processing with an overlap, optional stand mask
and object forest, GeoPackage output, `geosnag` CLI.
