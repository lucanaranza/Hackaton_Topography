# Coordinate dei risultati precedenti

Gli orizzonti precedenti sono stati calcolati dal **centro geometrico di ciascun DEM**,
convertito nelle coordinate geografiche lunari tramite il CRS del GeoTIFF.
Non sono ancora verificati rispetto ai punti di atterraggio scelti dal gruppo.

- `horizon.json`: lat/lon indicano quel centro e l'orizzonte da quel centro.
- `summary.json` -> `center`: centro geografico del DEM.
- `site_cells.csv`: coordinate dei centri delle celle della griglia.

Le statistiche dell'intera mappa e la georeferenziazione delle celle restano
statistiche del DEM; non devono essere presentate come metriche di un punto
specifico di atterraggio. I valori numerici precedenti sono preservati per audit.

Lo script aggiornato richiede coordinate sito esplicite. Il catalogo da compilare
si trova in `config/site_coordinates.json` alla radice del progetto.
Il confronto tra punti sito e centri DEM e in `controllo_coordinate/README.md`.
Non viene eseguito alcun ricalcolo con valori mancanti o punti fuori DEM.
