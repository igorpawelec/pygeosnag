# Changelog

## 0.4.1 — the tolerance tapers with the distance from the seed

- `growkernel.grow_within_reach(..., taper=)`: the tolerance is `max_cost`
  at the seed and `max_cost - taper` at `max_radius`, linear in between;
  `grow_crowns(taper=)` and `--taper` pass it through (rule "reach" only).
- The default ndvi_L recipe becomes 28 at the seed, 12 at the radius
  (`SPACES_REACH["ndvi_L"] = max_cost 28, taper 16`). Why: a flat tolerance
  cannot serve both dense clusters (their bleached crowns want 25-30 near
  the seed) and sparse stands (anything above 15 at the radius spills into
  shadow and bare ground). Benchmarked on 14 tolerance pairs
  (80_grow_bench --rule taper): 8 sites median IoU 0.698, 79% above 0.5,
  OS 0.07, US 0.13 (0.4.0: 0.652, 72%, 0.03, 0.22); Gizycko 0.562, 63%
  (0.4.0: 0.478, 45%); no site loses more than 0.01. Hajnowka against ALS
  crowns: 0.29 against 0.29 (0.4.0) and 0.24 (0.3.x).

## 0.4.0 — a new default crown recipe: within-reach growing on NDVI + L

- Default `grow_crowns(space="auto", rule="reach")`: the feature space is
  100 * NDVI and CIELAB L with a NIR band (`lab_w`, the old weighted CIELAB,
  without one), and the assignment rule is pygeosnag's own kernel
  (`growkernel.ift_within_reach`): a pixel goes to the seed within the
  radius and under the tolerance with the lowest minimax path cost, the
  cuts inside the growth. The old behaviour -- pygeoadaptels' single global
  IFT partition with every seed, cut by tolerance and radius afterwards --
  is kept as `rule="partition"`. Why: in a dense cluster of dead trees a
  pixel won by a farther seed and then cut by the radius never returned to
  the near seed; on Gizycko the seed of a crown kept 39% of its own pixels
  whatever the tolerance or radius.
- Measured (SDT_research2026/80_grow_bench): tolerance chosen on 2027
  Gizycko crowns, validated on 1113 crowns of the 8 publication sites, the
  detector's own points as competitors. New default: 8 sites median IoU
  0.652, 72% above 0.5, OS 0.03, US 0.22; Gizycko 0.478, 45%. Old recipe:
  0.526, 54%, OS 0.00, US 0.38; Gizycko 0.335, 14%. The within-reach kernel
  is also about five times faster than the partition on the same window.
- `--space` and `--rule` on the CLI; `SPACES_REACH` holds the tolerances
  per space under the new rule (raw is not benchmarked under it).

## 0.3.5 — a feature space for the growing, benchmarked

- `grow_crowns(space=...)` and `geosnag grow --space`: `lab_w` (the shipped
  recipe, CIELAB with a* weighted 2.5, tolerance 15), `lab` (unweighted,
  30), `ndvi_L` (100 * NDVI and L, 45; needs a NIR band), `raw` (digital
  numbers, 70). Benchmarked on 8 verified sites (1200 crowns with their
  tops) and Gizycko (6460 crowns), seeds = the reference tops, competitors
  = the detector's points, tolerance chosen on Gizycko, scored on the 8
  sites: median IoU 0.62 for `ndvi_L` against 0.53 for the shipped recipe,
  at the same over-segmentation (~0) and less under-segmentation (0.31
  against 0.38); unweighted CIELAB 0.55; the a* weighting hurts. The
  default stays `lab_w`. What no space fixes: in dense dead-tree clusters
  (Gizycko, IoU <= 0.49 for every space) a pixel won by a farther seed and
  then cut by the radius never returns to the near one -- a property of
  the single global IFT partition, not of the features. Report:
  SDT_research2026/80_grow_bench/RAPORT_GROW_BENCH.md.

## 0.3.4 — crowns grown tile by tile

- `grow_crowns` no longer reads the raster whole nor writes a CIELAB copy
  to a temporary file: the raster is cut into tiles (row bands on a
  striped GeoTIFF, squares on a tiled one), each tile that holds a point is
  read with a halo of twice `max_radius`, converted to CIELAB in memory and
  grown with every point in the window competing; only the crowns of the
  tile's own points are kept. Memory is bounded by the window (a 40 Mpx
  band peaks around 3 GB); a 796-megapixel CIR orthophoto with 11 804
  points, which killed the previous version at the temp drive, runs
  through. `tile`, `halo`, `workers` (parallel processes; keep 1 inside
  QGIS) and `progress` are new arguments; `--tile` and `--workers` on the
  CLI. Output is one MultiPolygon per point (`adaptel_id` = point index,
  `area_m2`, `perimeter`, `n_parts`) in layer `crowns`; the label raster is
  a tiled BigTIFF-safe GeoTIFF. Measured against the whole-window run on a
  2400 px Hajnówka crop with 1496 points: same crown count, differences
  only from IFT tie-breaking at crown boundaries (median 1.7 m² per
  affected crown, total area within 3%, unchanged by a larger halo).
- Depends on pygeoadaptels 0.10.4 for the hole filling that made whole-
  raster runs take hours (36 s per 2400 px tile before, 0.3 s now).

## 0.3.3 — radiometry matching is off by default

- Measured on the whole 200-scene batch: the "auto" trigger fired on 44
  scenes, 27 went from nothing to hundreds of points, 17 lost nearly all
  their points (0233111: 10 575 -> 0; 1117209: 27 097 -> 159), mostly RGB
  scenes triggered by a modest dark-end offset in blue. Mapping the bands
  separately changes NDVI, NDGR and NDBR, which the forests stand on. So
  `detect(radiometry="off")` is the default and "auto" is documented as a
  rescue for a scene that returned nothing; the CLI and the plugin follow.

## 0.3.2 — radiometry matching for hazy and flat scenes

- `radiometry.Radiometry`: the scene's per-band 2-98 percentiles (from the
  tiles the scene normalisation samples) are mapped linearly onto the
  training orthophotos' reference percentiles (`REFERENCE`, medians over
  the nine training rasters). `detect(radiometry="auto")` (default) does
  it only when the scene is hazy (dark end > 15 DN above the reference) or
  flat (range < 0.7 of the reference); `"match"` always, `"off"` never;
  `--radiometry` on the CLI. Measured on the 200-AOI batch of 2026-09-07:
  48 of 200 scenes trigger; on three that gave zero points a 600 m crop
  went from a highest probability of 0.21-0.59 to 11-61 points above 0.6,
  on grey crowns. Scene normalisation could not do this: it standardises
  the five absolute means, not the pixel-level contrasts the other
  fifteen features are built on.

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
