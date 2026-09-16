# Champs MOEX ISS observés avant le collecteur

Ce document fige les observations produites par `tests/explore_iss.py` sur
l'API publique MOEX ISS. Il distingue les faits retournés par la réponse des
choix de collecte qui devront être revalidés avant le moteur de courbe.

## Endpoint exploré

```text
/iss/engines/stock/markets/bonds/boards/TQOB/securities.json?iss.meta=off
```

L'endpoint a retourné les blocs `securities`, `marketdata` et
`marketdata_yields` pour le board `TQOB`.

## Identification des OFZ-PD

Retenir `LATNAME` contenant la valeur `OFZ-PD` pour identifier une OFZ-PD.
Dans les lignes observées, `SECNAME` fournit la même information en russe,
avec le texte `ОФЗ-ПД`. Exemples observés : `LATNAME = "OFZ-PD 26207"` et
`SECNAME = "ОФЗ-ПД 26207 03/02/27"`.

Les champs de référence associés sont `SECID`, `ISIN`, `MATDATE`,
`COUPONPERCENT`, `COUPONPERIOD`, `BONDTYPE` et `FACEVALUE_TYPE`.

## Prix

Champ à retenir : `marketdata.LAST`.

Dans les échantillons, `LAST` était égal à `marketdata_yields.PRICE` pour les
titres affichés. Il représente donc le choix le plus directement recoupé avec
le bloc qui fournit le rendement effectif et la duration.

- `WAPRICE` est écarté pour le prix de collecte : il différait de `LAST` dans
  les observations et possède son propre couple `EFFECTIVEYIELDWAPRICE` /
  `DURATIONWAPRICE` dans `marketdata_yields`.
- `LCURRENTPRICE` est écarté : il peut différer de `LAST` (par exemple,
  `97.955` contre `98.219` dans l'échantillon). La réponse JSON explorée ne
  donne pas de définition permettant de le préférer.

La convention prix propre/prix sale reste **À CONFIRMER** ; voir la section
des hypothèses non prouvées.

## Rendement

Champ à retenir : `marketdata_yields.EFFECTIVEYIELD`, associé à
`marketdata_yields.PRICE`.

Dans les exemples, cette valeur est la version plus précise du rendement
associé au prix observé : par exemple `EFFECTIVEYIELD = 13.2439` face à
`marketdata.YIELD = 13.24` pour `SU26207RMFS9`.

- `marketdata.YIELD` est écarté comme valeur principale : il est présent mais
  moins précis dans l'échantillon.
- `marketdata.YIELDATWAPRICE` est écarté : il correspond au prix pondéré
  `WAPRICE`, non au prix `LAST` retenu.
- `YIELDTOOFFER` existe mais était `null` dans les cinq lignes observées ; il
  ne peut donc pas servir de valeur primaire.

L'unité et la convention exacte du rendement restent **À CONFIRMER**.

## Duration

Champ à retenir : `marketdata_yields.DURATION`, associé au couple
`PRICE`/`EFFECTIVEYIELD` retenu.

`DURATIONWAPRICE` est écarté : il est explicitement le pendant de `WAPRICE`.
Les deux valeurs ont parfois différé dans les observations (par exemple,
`2473` contre `2472` pour `RU000A10FAK6`), ce qui confirme qu'elles ne doivent
pas être substituées silencieusement.

L'unité de duration reste **À CONFIRMER**.

## Liquidité et date de transaction

Champs disponibles et renseignés dans l'échantillon :

- `VOLTODAY` : volume ;
- `VALTODAY` : valeur échangée ;
- `NUMTRADES` : nombre de transactions ;
- `BID`, `OFFER` et `SPREAD` : meilleures cotations bid/ask et leur écart.

Champs présents dans la réponse mais vides (`null`) dans les cinq lignes
observées : `BIDDEPTH`, `OFFERDEPTH`, `NUMBIDS`, `NUMOFFERS`. Ils ne doivent
pas être considérés comme disponibles sans contrôle au moment de la collecte.

Champ à retenir comme proxy de dernière transaction :
`marketdata_yields.TRADEMOMENT`. C'est le seul horodatage complet explicitement
associé aux données de rendement dans le bloc observé. `UPDATETIME`, `TIME` et
`SYSTIME` existent aussi, mais ils ne sont pas documentés dans la réponse comme
une date de dernière transaction.

Aucun champ `LASTTRADEDATE` ou `TRADEDATE` explicite n'a été retourné dans
`marketdata`.

## Hypothèses non prouvées

Avant le prompt 5 de la Phase 1 (moteur de courbe), les points suivants doivent
être vérifiés, sans les résoudre ici :

1. **Unité des rendements et durations.** Les valeurs observées sont compatibles
   avec un pourcentage annuel pour les rendements et une durée en jours pour la
   duration, mais la documentation JSON elle-même ne le confirme pas.
2. **Convention de prix.** `LAST` et `WAPRICE` pourraient être des prix propres,
   `ACCRUEDINT` étant fourni séparément, mais cela n'est pas prouvé.

Le moteur de courbe du prompt 5 ne devra pas supposer silencieusement une
réponse à ces deux points. Il devra soit les vérifier par un calcul de
recoupement — par exemple en comparant un rendement calculé manuellement sur
une obligation connue avec le `YIELD` retourné — soit documenter explicitement
l'hypothèse retenue dans le code.
