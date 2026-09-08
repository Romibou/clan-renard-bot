# Assets graphiques — Clan Renard

Le calendrier de l'Avent est recréé dynamiquement avec Pillow.

Il n'est pas nécessaire de préparer :

- 24 images de cadeaux ;
- une image par membre ;
- une image par combinaison de cases ;
- des images séparées pour les croix ou cadenas.

Le programme dessine automatiquement :

- le fond prune et violet ;
- le cadre rose ;
- les 24 cartes ;
- les cadeaux ;
- les rubans ;
- les cadenas ;
- les croix ;
- les coches ;
- les étoiles ;
- les flocons ;
- les fleurs et les branches ;
- un emblème de renard de remplacement.

## Logo facultatif

Pour utiliser le vrai logo de Clan Renard, place un PNG ici :

```text
assets/branding/clan_renard_logo.png
```

Conseils :

- format PNG transparent ;
- forme carrée ;
- au moins 512 × 512 pixels ;
- peu de marge autour de l'emblème ;
- éviter un fond noir ou blanc opaque.

En l'absence de ce fichier, le bot dessine son propre renard stylisé.

## Polices facultatives

Deux polices peuvent être ajoutées :

```text
assets/advent/fonts/title.ttf
assets/advent/fonts/regular.ttf
```

Si elles sont absentes, le projet cherche automatiquement DejaVu Sans,
Arial ou une police système compatible.

Vérifie que tu disposes du droit d'intégrer les polices choisies au dépôt.

## Prévisualisation locale

Une fois les dépendances installées :

```bash
python scripts/preview_calendar.py
```

Le résultat est créé ici :

```text
generated/apercu-calendrier.png
```

Il est également possible de personnaliser l'année et le pseudo :

```bash
python scripts/preview_calendar.py --year 2026 --name "Ton pseudo"
```

## Couleurs

La palette principale est définie dans :

```text
bot/features/advent/theme.py
```

Elle utilise notamment :

- fond presque noir violet ;
- prune profond ;
- rose poudré ;
- rose clair ;
- blanc rosé ;
- vert doux pour les cases ouvertes ;
- rouge rosé pour les cases manquées.

## Taille finale

Le calendrier mesure :

```text
1600 × 1000 pixels
```

Cette taille reste lisible sur ordinateur et téléphone tout en
conservant un poids raisonnable pour Discord.
