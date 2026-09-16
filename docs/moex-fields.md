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

## Validation opérationnelle des conventions — 2026-09-16

### Rendement : pourcentage annuel

La méthodologie officielle MOEX définit `Y` comme le rendement à maturité « en
pourcentage annuel » et utilise `Y / 100` dans ses formules. Le champ ISS
retenu `EFFECTIVEYIELD` est donc stocké en pourcentage annuel : `13.2469`
signifie `13.2469 %`, non `0.132469`.

Source officielle : [Méthodologie MOEX](https://www.moex.com/files/43927heqa4mxe6xdq5xkkktdd7).

### Duration : jours dans le champ ISS retenu

La méthodologie définit la duration Macaulay financière `D` en années. Le
champ ISS observé `marketdata_yields.DURATION` est en jours : dans le snapshot
du 2026-09-16, `SU26207RMFS9` a `DURATION = 138`, pour une maturité le
2027-02-03. Une valeur de 138 années est impossible ; elle est cohérente avec
une duration d'environ 138 jours, proche des 140 jours jusqu'à maturité et de
la date de règlement. Le moteur utilise donc ce champ en jours.

Source de la définition financière : [Méthodologie MOEX](https://www.moex.com/files/43927heqa4mxe6xdq5xkkktdd7).

### Prix : prix propre en pourcentage du nominal

MOEX indique que le prix de marché des obligations est coté en pourcentage du
nominal et le nomme prix propre. Sa méthodologie définit `P` comme le prix sans
NCD et ajoute le NCD `A` séparément dans les formules (`P + A`). `LAST` est le
prix de la dernière transaction ; il est donc retenu comme prix propre, en
pourcentage du nominal, tandis que `ACCRUEDINT` reste distinct.

Sources officielles : [prix de marché MOEX](https://www.moex.com/a3156) et
[méthodologie de rendement](https://www.moex.com/files/43927heqa4mxe6xdq5xkkktdd7).

### TRADEMOMENT reste non vérifié

`TRADEMOMENT` n'est pas activé comme date de dernière transaction. Dans le
snapshot collecté à `2026-09-16T12:02:53+00:00`, des valeurs `TRADEMOMENT`
étaient `2026-09-16 14:47:xx`, postérieures à l'horodatage de collecte. Sans
clarification de fuseau horaire ou de sémantique par MOEX, le filtre le marque
comme donnée non vérifiée et l'exclut selon la politique configurée.

## Validation de TRADEMOMENT et fraîcheur de séance — 2026-09-16

### Ce qui est vérifié et ce qui ne l'est pas

La documentation officielle consultée définit `LAST` comme le prix de la
dernière transaction et `TIME` comme l'heure de cette transaction. Elle définit
également `NUMTRADES` comme le nombre de transactions du jour, `VOLTODAY` comme
le volume quotidien en titres, et `VALTODAY` comme le volume quotidien dans la
devise de règlement. En revanche, aucune définition officielle explicite de
`TRADEMOMENT` n'a été trouvée dans la documentation ISS/ASTS consultée.

Deux cycles réels confirment que les valeurs sont compatibles avec une heure de
marché Moscow time (GMT+3) servie par ISS avec retard : le second cycle a été
horodaté à `2026-09-16T12:33:33+00:00`, et les `TRADEMOMENT` observés étaient
autour de `2026-09-16 15:18:xx`. Converties de MSK vers UTC, elles précèdent la
collecte d'environ quinze minutes. Cette cohérence est compatible avec le délai
public ISS, mais n'est pas une documentation de la sémantique du champ.

`TRADEMOMENT` reste donc **non vérifié** et n'est pas présenté comme une preuve
de dernière transaction à la minute.

Sources : [interface ISS](https://www.moex.com/a8531),
[description ASTS des champs de marché](https://ftp.moex.com/pub/ClientsAPI/Spectra/CGate/prod/Scheme/6.18/docs/p2micexgate_en.pdf),
et [horaires du marché actions/obligations, GMT+3](https://www.moex.com/torgovye-sessii-na-fondovom-rynke).

### Règle alternative de fraîcheur retenue

Quand `TRADEMOMENT_IS_VERIFIED_LAST_TRANSACTION = False`, le filtre ne tente
pas de calculer un âge de transaction. Il exige plutôt une activité vérifiée de
la séance : `NUMTRADES > 0` et `VOLTODAY > 0`, puis applique les seuils
configurables `MIN_SESSION_TRANSACTIONS` et `MIN_SESSION_VOLUME`.

Cette règle établit seulement qu'au moins une transaction a eu lieu dans la
séance en cours ; elle ne prétend jamais prouver une transaction récente à la
minute. Les titres dont ces données sont absentes ou nulles sont signalés
distinctement. Le spread est calculé à partir de `BID` et `OFFER` uniquement
lorsque les deux valeurs sont présentes.

`VALTODAY` est officiellement une valeur de séance utile comme contrôle
supplémentaire, mais il n'est pas actuellement conservé dans `snapshots` ; il
ne participe donc pas au filtre historique actuel.

### Résultat opérationnel

Avec cette règle sur le dernier cycle complet : 36 OFZ-PD ont été collectées,
31 sont éligibles et 5 sont exclues. Le fit robuste a utilisé 31 titres et a
produit une RMSE de 23,08 bp. Les z-scores sont `NULL` au démarrage, faute
d'historique propre à chaque obligation, conformément à la règle du moteur.

## Hypothèses non prouvées — historique, remplacées le 2026-09-16

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
