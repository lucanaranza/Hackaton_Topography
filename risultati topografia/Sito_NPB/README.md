# Sito_NPB

Analisi del centro del DEM; osservatore a 2 m.

| Metrica | Valore |
| --- | --- |
| Centro (lat, lon lunari) | -83.904646, 89.535450 gradi |
| Quote min / max | -3891.10 / -2859.21 m |
| Pendenza media calcolata | 5.25 gradi |
| Area con pendenza <=10 gradi | 338.47 km2 (84.70%) |
| Incertezza verticale media fornita | 1.088 m |
| Pixel con LDEC zero | 98.08% |
| Orizzonte minimo / massimo | 1.467 / 8.337 gradi |
| Celle | 40000 |
| Verifica | PASS |

## Risultati

- [Orizzonte regionale a 360 valori](horizon.json)
- [Orizzonte solo locale](horizon_local.json)
- [Mappa e profilo](horizon.png)
- [Statistiche complete](summary.json)
- [Celle topografiche](site_cells.csv)
- [Rapporto di verifica e qualita](validation.json)

## Interpretazione e limiti

La pendenza descrive tutto il DEM, mentre il profilo orizzonte riguarda soltanto il suo centro.
Il centro del raster non e necessariamente il punto di atterraggio associato al nome del sito.
Le percentuali sono riferite ai pixel con pendenza calcolabile; le aree sono proiettate.
Le celle sono 100 x 100 m, piu piccole ai bordi quando necessario.
LDEC zero non e NoData: il DEM contiene anche terreno interpolato.
Il filtro di pendenza non certifica un sito sicuro e non impone aree connesse.
Non sono stati calcolati luce, visibilita terrestre, temperatura o presenza di ghiaccio.
Output compatti: nessun GeoTIFF derivato, per contenere lo spazio su disco.
Terreno lontano incluso fino a 200 km: 360/360 direzioni con tutti i campioni disponibili.
Ostruzione aumentata in 360 direzioni; aumento massimo 7.7168 gradi.
Il LDSM identifica il prodotto LDEM: le quote regionali provengono dal LDEM 60S a 240 m/pixel.
Il passo di campionamento regionale di 100 m non aumenta la risoluzione del DEM.
La copertura completa riguarda i campioni; rimangono i limiti del dettaglio e del raggio scelto.
