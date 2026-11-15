# Sito_NPD

Analisi del centro del DEM; osservatore a 2 m.

| Metrica | Valore |
| --- | --- |
| Centro (lat, lon lunari) | -84.803401, 8.387032 gradi |
| Quote min / max | -2463.47 / -1337.34 m |
| Pendenza media calcolata | 6.18 gradi |
| Area con pendenza <=10 gradi | 325.88 km2 (81.55%) |
| Incertezza verticale media fornita | 0.502 m |
| Pixel con LDEC zero | 94.75% |
| Orizzonte minimo / massimo | 2.354 / 13.044 gradi |
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
Ostruzione aumentata in 360 direzioni; aumento massimo 10.3044 gradi.
Il LDSM identifica il prodotto LDEM: le quote regionali provengono dal LDEM 60S a 240 m/pixel.
Il passo di campionamento regionale di 100 m non aumenta la risoluzione del DEM.
La copertura completa riguarda i campioni; rimangono i limiti del dettaglio e del raggio scelto.
