# Méthode de courbe Phase 1

Le moteur ajuste le rendement observé en fonction de la duration sur les seules
OFZ-PD éligibles. Il utilise `scipy.optimize.least_squares` avec un polynôme de
degré configurable sur une duration centrée-réduite et une perte robuste
`soft_l1`. SciPy est déjà une dépendance maintenue du projet ; cette méthode est
transparente et ne requiert pas de moteur obligataire supplémentaire tant que le
fit porte directement sur les couples rendement/duration observés.

Le `soft_l1` réduit l'influence d'un titre isolé qui s'écarte fortement de la
courbe. La qualité affichée est la RMSE des résidus en points de base. Pour les
plus grands écarts, un diagnostic leave-one-out réajuste la courbe sans le titre
concerné et affiche son résidu de référence.

Le moteur refuse de démarrer tant que les unités rendement/duration et la
convention de prix signalées comme non prouvées dans `docs/moex-fields.md` ne
sont pas explicitement vérifiées dans `config/settings.py`.
