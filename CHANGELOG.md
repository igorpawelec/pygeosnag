# Changelog

## 0.2.1 (unreleased)

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
