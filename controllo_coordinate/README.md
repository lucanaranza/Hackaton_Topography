# Controllo coordinate prima del calcolo

Le coordinate dei siti sono separate dai centri dei DEM. Nessun centro viene usato automaticamente.
Siti pronti: 0/27. Calcolo autorizzabile dai dati: False.

| Sito | Lat sito | Lon sito | Lat centro DEM | Lon centro DEM | Distanza (m) | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| Sito_01 | - | - | -89.463163 | -137.489553 | - | MISSING_COORDINATES |
| Sito_04 | - | - | -89.766811 | -171.869898 | - | MISSING_COORDINATES |
| Sito_06 | - | - | -85.438100 | 37.366669 | - | MISSING_COORDINATES |
| sito_07 | - | - | -88.811008 | 123.690068 | - | MISSING_COORDINATES |
| Sito_11 | - | - | -88.683418 | -67.932100 | - | MISSING_COORDINATES |
| Sito_20 | - | - | -85.426577 | 31.742761 | - | MISSING_COORDINATES |
| Sito_20v2 | - | - | -85.426577 | 31.742761 | - | MISSING_COORDINATES |
| Sito_23 | - | - | -85.994785 | -0.235784 | - | MISSING_COORDINATES |
| Sito_42 | - | - | -85.829551 | -116.322016 | - | MISSING_COORDINATES |
| Sito_DM1 | - | - | -84.228739 | 69.443955 | - | MISSING_COORDINATES |
| Sito_DM2 | - | - | -83.954017 | 58.822055 | - | MISSING_COORDINATES |
| Sito_Haworth | - | - | -86.763942 | -22.777024 | - | MISSING_COORDINATES |
| Sito_LM1 | - | - | -89.524389 | 56.309932 | - | MISSING_COORDINATES |
| Sito_LM2 | - | - | -88.079236 | 11.888658 | - | MISSING_COORDINATES |
| Sito_LM3 | - | - | -88.382845 | 16.587339 | - | MISSING_COORDINATES |
| Sito_LM4 | - | - | -88.964502 | 37.234834 | - | MISSING_COORDINATES |
| Sito_LM5 | - | - | -88.631979 | 74.623749 | - | MISSING_COORDINATES |
| Sito_LM6 | - | - | -87.945775 | 71.274212 | - | MISSING_COORDINATES |
| Sito_LM7 | - | - | -87.889654 | 90.000000 | - | MISSING_COORDINATES |
| Sito_LM8 | - | - | -87.341715 | 60.255119 | - | MISSING_COORDINATES |
| Sito_NPA | - | - | -86.924324 | -71.565051 | - | MISSING_COORDINATES |
| Sito_NPB | - | - | -83.904646 | 89.535450 | - | MISSING_COORDINATES |
| Sito_NPC | - | - | -84.539700 | 126.904476 | - | MISSING_COORDINATES |
| Sito_NPD | - | - | -84.803401 | 8.387032 | - | MISSING_COORDINATES |
| Sito_Shoemaker | - | - | -87.183514 | 62.835015 | - | MISSING_COORDINATES |
| Sito_SL2 | - | - | -88.229978 | -64.628438 | - | MISSING_COORDINATES |
| Sito_SL3 | - | - | -89.032416 | -101.999287 | - | MISSING_COORDINATES |

Compilare config/site_coordinates.json con i punti reali e la fonte del gruppo effemeridi.
I valori mancanti restano vuoti. Le coordinate approssimate dei crateri e i centri delle regioni non sono sostituti automatici dei punti scelti.
Il JSON contiene anche X/Y lunari e riga/colonna del pixel, quando le coordinate sono disponibili.
