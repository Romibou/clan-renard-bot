# Fonctionnalités de Clan Renard Bot

Ce document décrit tout ce que fait le bot : les commandes des membres, les panneaux d’administration et le fonctionnement de chaque système.

Pour l’installation et le déploiement, voir `README.md`.

## Sommaire

1. [Commandes](#commandes)
2. [Progression : XP, niveaux et rôles](#progression--xp-niveaux-et-rôles)
3. [Récompense quotidienne](#récompense-quotidienne)
4. [Missions](#missions)
5. [Économie : pièces, dons, drops et giveaways](#économie--pièces-dons-drops-et-giveaways)
6. [Boutique permanente](#boutique-permanente)
7. [Profils, cosmétiques et collections](#profils-cosmétiques-et-collections)
8. [Classements, statistiques et bilan](#classements-statistiques-et-bilan)
9. [Calendrier de l’Avent](#calendrier-de-lavent)
10. [Mini-jeux et bingo](#mini-jeux-et-bingo)
11. [Outils : rappels, rôles à la réaction, aide](#outils--rappels-rôles-à-la-réaction-aide)
12. [Bienvenue et départs](#bienvenue-et-départs)
13. [Annonces](#annonces)
14. [Modération](#modération)
15. [Maintenance : sauvegardes, import, permissions](#maintenance--sauvegardes-import-permissions)

---

# Commandes

## Membres

| Commande | Description |
|---|---|
| `/aide` | Liste toutes les commandes, classées par thème |
| `/progression [membre]` | Carte de niveau, XP et argent |
| `/classement` | Classements XP, argent, série, XP de la semaine et du mois |
| `/stats [membre] [periode]` | Statistiques du jour ou des 7 derniers jours |
| `/bilan [membre]` | Bilan de l’année (du 31 décembre au 31 janvier) |
| `/quotidien` | Récompense quotidienne et réglage du rappel |
| `/hebdomadaire` | Récompense de la semaine |
| `/mensuel` | Récompense du mois |
| `/missions` | Missions du jour et de la semaine |
| `/boutique` | Boutique permanente (rôles et cosmétiques) |
| `/role-perso` | Voir et gérer son rôle personnalisé : date de fin, couleur, nom et icône, prolonger, supprimer (voir [Rôles perso](#rôles-perso)) |
| `/profil [membre]` | Carte de profil, personnalisation, inventaire, collections |
| `/collections [membre]` | Tableau des collections de cosmétiques |
| `/donner` | Donne des pièces à un membre |
| `/rappel` | Programme un rappel personnel |
| `/ping` | Vérifie que le bot répond : connexion à Discord, temps de réponse, base de données, durée en ligne |
| `/anniversaire` | Enregistre ton anniversaire, voir les prochains |
| `/anniversaires-liste` | Liste publique des prochains anniversaires du serveur |
| `/jeu morpion`, `/jeu puissance4`, `/jeu pfc`, `/jeu pendu` | Mini-jeux contre un membre (avec mise possible), contre l’IA ou en solo |
| `/jeu classement [jeu] [tri]` | Classement des meilleurs joueurs aux mini-jeux |
| `/jeu stats [membre]` | Victoires, défaites et gains aux mini-jeux |
| `/avent` | Calendrier de l’Avent personnel (quand la campagne est activée) |

## Administration

| Commande | Permission | Description |
|---|---|---|
| `/progression-admin` | Gérer le serveur | XP, multiplicateurs, rôles de niveau, XP vocale, bonus d’XP, modifier ou réinitialiser un membre |
| `/quotidien-admin` | Gérer le serveur | Récompenses quotidienne, hebdomadaire et mensuelle, bonus de série, réinitialiser un membre |
| `/missions-admin` | Gérer le serveur | Missions en JSON |
| `/boutique-admin` | Gérer le serveur | Articles de la boutique permanente |
| `/profil-admin` | Gérer le serveur | Créer, distribuer et supprimer des cosmétiques |
| `/avent-admin` | Administrateur | Tout le calendrier de l’Avent |
| `/drop` | Gérer le serveur | Fait apparaître un drop d’XP ou de pièces |
| `/giveaway lancer` / `terminer` / `retirer` | Gérer le serveur | Giveaways |
| `/bingo lancer` / `nombre` / `arreter` | Gérer le serveur | Bingo « trouve le nombre » dans un salon |
| `/anniversaire-admin` | Gérer le serveur | Souhaits d’anniversaire : salon, heure, message, carte, rôle du jour, cadeau |
| `/bienvenue-admin` | Gérer le serveur | Messages et cartes de bienvenue et de départ (voir [Bienvenue et départs](#bienvenue-et-départs)) |
| `/annonce creer` / `modifier` / `programmees` / `historique` | Gérer le serveur | Studio d’annonces publiées par le bot (voir [Annonces](#annonces)) |
| `/reaction-role`, `/reaction-role-retirer`, `/reaction-role-liste` | Gérer les rôles | Rôles à la réaction |
| `/membres-role` | Gérer les rôles | Liste des membres qui ont (ou n’ont pas) un rôle (voir [Membres par rôle](#membres-role)) |
| `/import_draftbot` | Administrateur | Import d’une progression DraftBot |
| `/warn`, `/mute`, `/unmute`, `/amende`, `/pardon`, `/casier`, `/note` | Exclure temporairement | Sanctions, annulations, casier (voir [Modération](#modération)) |
| `/kick` | Expulser | Expulsion |
| `/ban`, `/unban` | Bannir | Bannissement définitif ou temporaire |
| `/clear` | Gérer les messages | Suppression de messages |
| `/lock`, `/unlock` | Gérer les salons | Verrouillage d’un salon |
| `/moderation-admin` | Gérer le serveur | Journal, contestations, échelle de sanctions, AutoMod |

Les commandes d’administration n’apparaissent pas aux membres qui n’ont pas la permission. Dans les panneaux d’administration, les menus déroulants se vident après chaque action (on peut relancer la même action sans retaper la commande), et les choix de salon, de rôle ou de membre s’ouvrent dans un nouveau message : le panneau reste ouvert. Dans `/aide`, les administrateurs voient en plus la liste de ces commandes.

Les anciennes commandes `/avent-profil`, `/avent-boutique`, `/avent-admin-…` existent encore dans le code mais sont retirées de Discord : tout passe par les boutons de `/avent` et le panneau `/avent-admin`.

---

# Progression : XP, niveaux et rôles

## XP par message

Un message rapporte une quantité aléatoire d’XP et de pièces, au plus une fois par délai (par exemple toutes les 60 secondes). Les messages envoyés pendant ce délai ne rapportent rien. Les bots et les webhooks ne gagnent rien.

Réglages dans `/progression-admin` → **Configuration** : délai, XP minimale et maximale, pièces minimales et maximales.

## XP en vocal

Chaque minute, les membres actifs en vocal gagnent de l’XP (pas de pièces). Un membre est actif s’il n’est pas dans le salon AFK, ni rendu muet ou sourd (par lui-même ou par un modérateur), et s’il y a au moins **deux** membres actifs dans le salon.

Réglage dans `/progression-admin` → **XP vocal** (XP par minute, `0` pour désactiver).

## Niveaux

Le niveau est calculé à partir de l’XP totale, avec une courbe où chaque niveau demande un peu plus d’XP que le précédent. Quand un membre monte de niveau, le bot peut l’annoncer dans le salon (`/progression-admin` → **Notifications de niveau**).

`/progression [membre]` affiche la carte : niveau, XP totale, progression vers le niveau suivant, rang, portefeuille et argent total gagné.

## Multiplicateurs de rôle

Un rôle peut multiplier l’XP gagnée (messages et vocal), de ×1 à ×10. Si un membre a plusieurs rôles avec multiplicateur, seul le plus élevé compte.

`/progression-admin` → **Multiplicateur XP** : choisir le rôle, puis la valeur (`0` supprime la règle).

## Bonus d’XP temporaire

`/progression-admin` → **Bonus d’XP** ouvre un formulaire :

- **Multiplicateur** : par exemple `2` pour doubler l’XP, de 1,1 à 5. `1` arrête le bonus en cours.
- **Début** et **Fin**, heure de Paris : par exemple `24/12 00:00` et `26/12 23:59`. Début vide = tout de suite. Sans heure, le début est à 00:00 et la fin à 23:59.
- **Nom** : affiché dans les annonces (« Bonus de Noël »).
- **Annonce** : `oui` publie un message au début et à la fin du bonus, dans le salon où le formulaire a été rempli.

Le bonus vaut pour tout le serveur, sur l’XP des messages et du vocal. Il se multiplie avec les multiplicateurs de rôle : un VIP ×1,5 pendant un bonus ×2 gagne ×3. Un seul bonus peut être programmé à la fois ; en enregistrer un nouveau remplace l’ancien.

## Rôles de niveau

Un rôle peut être associé à un niveau (`/progression-admin` → **Rôle de niveau**, `0` supprime la règle). Le membre garde **uniquement** le rôle du plus haut palier atteint : en passant du niveau 30 au niveau 50, le rôle du niveau 30 est remplacé par celui du niveau 50. Si son XP baisse (modification admin, piège d’un drop), le rôle redescend aussi.

**Voir les règles** liste les multiplicateurs, les rôles de niveau et l’XP vocale.

## Modifier ou réinitialiser un membre

Dans `/progression-admin`, sélectionner un membre puis :

- **Modifier le membre** : ajouter ou retirer de l’XP et des pièces (nombres négatifs pour retirer), avec une raison. L’XP et le portefeuille ne descendent jamais sous 0.
- **Réinitialiser le membre** : efface son XP, son argent, ses statistiques de messages et de vocal et ses transactions, après confirmation.

**Activer/désactiver** coupe ou rallume tous les gains automatiques (messages et vocal).

---

# Récompense quotidienne

## `/quotidien`

Une récompense d’XP et de pièces, **une fois par jour** ; le compteur repart à **minuit, heure de Paris**.

- Récupérer la récompense deux jours de suite fait monter la **série** ; sauter un jour la remet à 1.
- La meilleure série est conservée (classement « Meilleure série quotidienne », `/bilan`).
- Des **bonus de série** (règles JSON dans `/quotidien-admin`, voir **Exemple JSON**) peuvent multiplier ou augmenter la récompense certains jours, par exemple tous les 7 jours ou au 30e.

## Rappel en message privé

Sous la réponse de `/quotidien` :

- **Activer / désactiver rappel** ;
- le menu **Choisir l’heure du rappel** fixe l’heure (heure de Paris) et active le rappel.

L’heure par défaut est **09:00**. Le rappel part une seule fois, le jour où la récompense redevient disponible, et n’arrive pas si le membre a fermé ses messages privés.

## `/hebdomadaire` et `/mensuel`

Une récompense par semaine et une par mois, en plus de `/quotidien`.

- **Semaine** : du lundi 00h00 au dimanche 23h59 (heure de Paris). **Mois** : du 1er à 00h00 à la fin du mois.
- Par défaut : **700 XP et 100 pièces** par semaine, **3 000 XP et 500 pièces** par mois.
- **Série** : réclamer plusieurs semaines (ou mois) d’affilée ajoute un bonus de **+10 %** par période, jusqu’à **+50 %**. Une période sautée remet la série à 1. Le record est affiché.
- Si c’est déjà récupéré, le bot indique quand revenir.
- L’argent compte comme de l’argent gagné (comme `/quotidien`), et l’XP peut faire monter de niveau (rôles de niveau donnés automatiquement).
- Les réponses ne sont visibles que par le membre, comme `/quotidien`.

## `/quotidien-admin`

Les boutons **🗓️ Hebdomadaire** et **📅 Mensuel** (en bas du panneau) règlent `/hebdomadaire` et `/mensuel` : XP, pièces, bonus de série par période, bonus maximum, activée ou non. Le panneau affiche leurs réglages actuels.

**Récompense** (XP et pièces de base), **Bonus de série** (JSON), **Activer/désactiver**, **Voir la configuration**, **Exemple JSON** et **Réinitialiser un membre**.

---

# Missions

## `/missions`

Affiche les missions du jour et de la semaine avec la progression du membre ; une mission terminée se réclame avec **Réclamer**.

- Missions quotidiennes : remises à zéro à minuit (heure de Paris).
- Missions hebdomadaires : remises à zéro le lundi à minuit.
- La progression compte depuis le **début réel** de la période, même si le membre n’a pas encore ouvert `/missions`.

| Objectif (`metric`) | Ce qui est compté |
|---|---|
| `messages` | Messages récompensés en XP (un seul par délai entre deux récompenses) |
| `voice_minutes` | Minutes en vocal avec au moins un autre membre |
| `xp` | XP gagnée |
| `coins` | Pièces gagnées (les dons reçus avec `/donner` ne comptent pas) |
| `daily_claims` | Récompenses quotidiennes récupérées |
| `streak` | Série quotidienne en cours |

## `/missions-admin`

Active le système et configure jusqu’à 25 missions en JSON (**Exemple JSON** donne un modèle). Chaque mission peut donner de l’XP, des pièces et un cosmétique de profil.

---

# Économie : pièces, dons, drops et giveaways

## Portefeuille

Les pièces se gagnent avec les messages, `/quotidien`, les missions, les cases de l’Avent, les drops et les giveaways. Elles se dépensent dans `/boutique`.

Deux valeurs sont suivies : le **portefeuille** (pièces disponibles) et l’**argent total gagné** (historique). Dépenser ou perdre des pièces ne réduit pas le total gagné.

## `/donner`

```text
/donner membre:@Membre montant:100 raison:Merci !
```

- **500 pièces par jour** au maximum par donneur (heure de Paris). La limite se règle dans le code (`DAILY_GIFT_LIMIT` dans `bot/extensions/donner.py`).
- Impossible de se donner des pièces ou d’en donner à un bot.
- Le don est annoncé dans le salon.
- Les pièces reçues ne comptent pas comme de l’argent gagné : elles ne font pas avancer les missions `coins` (pour éviter la triche avec un second compte).

## `/drop` (administration)

```text
/drop xp:500 pieces:100 gagnants:3 duree:10m mystere:False message:Le premier qui clique !
```

Un message avec un bouton **Récupérer** apparaît : les premiers membres à cliquer (`gagnants`, 1 par défaut, 50 au maximum) reçoivent l’XP et/ou les pièces, une fois chacun. Le drop disparaît quand toutes les places sont prises ou au bout de `duree` (10 minutes par défaut, 1 jour au maximum).

- **Pièges** : `xp` et `pieces` acceptent des nombres négatifs. L’XP et le portefeuille ne descendent jamais sous 0, et le rôle de niveau suit si le membre redescend.
- **Mystère** : `mystere:True` cache le contenu jusqu’au clic ; les montants sont révélés sur le message une fois le drop terminé. Indispensable pour qu’un piège fonctionne.
- Même avec des clics simultanés, il n’y a jamais plus de gagnants que de places. Le bouton fonctionne après un redémarrage.

## `/giveaway` (administration)

```text
/giveaway lancer lot:Nitro duree:2j gagnants:1 pieces:500 role:@Gagnant niveau_minimum:5 salon:#annonces
```

Seuls `lot` et `duree` sont obligatoires (durée de 1 minute à 30 jours).

- Les membres cliquent sur **Participer** ; un second clic les retire. Le message affiche le nombre de participants.
- À la fin, le bot tire au sort parmi les participants **encore présents** sur le serveur, annonce les gagnants et remet automatiquement les pièces et le rôle s’ils sont configurés. Un lot en texte (un Nitro…) est à remettre à la main.
- `niveau_minimum` réserve la participation aux membres de ce niveau ou plus.
- `/giveaway terminer numero:12` tire les gagnants tout de suite.
- `/giveaway retirer numero:12` tire de nouveaux gagnants (par exemple si un gagnant ne répond pas), en excluant les précédents, qui gardent leur lot.
- Le numéro est indiqué en bas du message du giveaway. Le bouton fonctionne après un redémarrage.

---

# Boutique permanente

## `/boutique`

Vend des **rôles Discord** et des **cosmétiques de profil** contre des pièces. Un article peut exiger un niveau minimum.

- Le menu indique pour chaque article : possédé, niveau requis, solde insuffisant ou disponible. Un cosmétique **déjà possédé** autrement (distribué, gagné à un giveaway, dans une case de l’Avent…) apparaît aussi comme **✅ Possédé**, dans les deux boutiques : on ne peut pas le racheter.
- Au-delà de 25 articles, des boutons **◀ Page 1/3 ▶** apparaissent (250 articles au maximum).
- Un rôle acheté puis retiré peut être récupéré gratuitement avec **Restaurer le rôle**.
- Un cosmétique acheté arrive dans l’inventaire de `/profil`.
- **👁️ Essayer** (cosmétiques) : montre au membre **sa propre carte de profil avec le cosmétique**, en privé, avant d’acheter. Rien n’est acheté ni équipé, et ça marche même sans assez de pièces. Aussi dans la boutique de l’Avent.
- **📜 Historique** (boutique du serveur seulement) : la liste privée de **tes** achats, du plus récent au plus ancien, en tableau aligné (date, article, pièces), avec le nombre d’achats et le total dépensé. Les remboursements (achat de rôle échoué) apparaissent avec **↩**. 12 lignes par page avec ◀️ ▶️.

## `/boutique-admin`

- **Ajouter un rôle** : rôle, prix, niveau minimum, nom et description.
- **Ajouter un cosmétique** : sélectionner un cosmétique déjà créé dans `/profil-admin`, puis son prix et son niveau minimum.
- **Liste** : articles actifs et leurs identifiants.
- **Supprimer** : retire un article. Les rôles et cosmétiques déjà achetés sont conservés.
- **🎨 Rôles perso** : réglages des rôles personnalisés (voir [Rôles perso](#rôles-perso)).

Supprimer un article de la boutique est différent de supprimer un cosmétique dans `/profil-admin`.

## Rôles perso

Un membre peut acheter **son propre rôle** : il choisit le nom, la couleur et une icône (emoji), paie, et le staff valide.

### Réglages (`/boutique-admin` → 🎨 Rôles perso)

| Réglage | Par défaut | Rôle |
|---|---|---|
| État | désactivés | Affiche ou non le bouton **🎨 Rôle perso** dans `/boutique` |
| Prix | 50 000 pièces | Prix de l’achat, et de chaque prolongation |
| Durée | 90 jours (3 mois) | Durée du rôle à partir de la validation, et de chaque prolongation |
| Salon des demandes | à choisir | Salon (privé) où le staff accepte ou refuse |

Le panneau montre aussi le nombre de rôles actifs et de demandes en attente, la **📋 Liste des rôles** (tableau : membre, rôle, date de fin) et **🗑️ Retirer un rôle** (sans remboursement, le membre reçoit la raison en MP).

### Achat (`/boutique` → 🎨 Rôle perso)

1. Le membre remplit **le nom** (2 à 25 caractères, sans emoji), **la couleur** (code hex, ex. `#FF9AD5`) et **l’icône** (un emoji, facultatif, placé après le nom : « Renard 🦊 »).
2. Un récapitulatif dans la couleur choisie lui demande de confirmer, puis il paie.
3. La demande arrive dans le salon des demandes avec **✅ Accepter** et **✖️ Refuser** (il faut la permission *Gérer les rôles*). Les boutons marchent même après un redémarrage du bot.
   - **Accepter** : le bot crée le rôle **tout en bas de la liste des rôles**, sans aucune permission et **non mentionnable**, puis le donne au membre.
   - **Refuser** : on peut écrire une raison. Le membre est **remboursé** et reçoit la raison en MP.

Un seul rôle perso (ou demande en attente) par membre. L’achat et un éventuel remboursement apparaissent dans **📜 Historique** de la boutique.

> Le rôle est en bas de la liste : sa couleur ne s’affiche pas sur le pseudo des membres qui ont déjà un rôle coloré au-dessus (le but est d’avoir **son** rôle, pas une couleur). Discord ne permet pas de réserver la mention d’un rôle à son propriétaire (ce serait tout le monde ou personne) : le rôle n’est donc pas mentionnable. L’icône est un emoji dans le nom, car les vraies icônes de rôle demandent le boost de niveau 2.

### `/role-perso`

Montre le rôle, son nom, sa couleur, sa date de création et **sa date de fin**, avec :

| Bouton | Effet |
|---|---|
| ✏️ **Nom et icône** | Nouvelle demande dans le salon des demandes, **gratuite**. Le rôle change seulement si le staff accepte (MP au membre dans les deux cas) |
| 🎨 **Couleur** | Change tout de suite |
| ⏳ **Prolonger** | Repaie le prix pour ajouter une durée complète (à partir de la date de fin actuelle), sans nouvelle validation |
| 🗑️ **Supprimer mon rôle** | Supprime le rôle, sans remboursement |

### Fin du rôle

- **7 jours avant la fin**, le membre reçoit un rappel en MP pour prolonger.
- **À la fin**, le rôle est supprimé du serveur (vérification toutes les 10 minutes) et le membre est prévenu.
- **Si le membre quitte le serveur**, son rôle est supprimé tout de suite, sans remboursement.
- Si un rôle perso est supprimé à la main dans Discord, sa fiche est close.

## Boutique permanente et boutique de l’Avent

| | Boutique permanente | Boutique de l’Avent |
|---|---|---|
| Accès | `/boutique` | Bouton **Boutique** du calendrier |
| Monnaie | Pièces (portefeuille) | Points de l’Avent de la campagne |
| Condition | Niveau minimum | Nombre de cases ouvertes |

Les deux monnaies sont indépendantes.

---

# Profils, cosmétiques et collections

## `/profil`

Affiche la carte de profil (avatar, pseudo, phrase personnalisée, couleur, cosmétiques équipés, progression). `/profil membre:@Membre` affiche celle d’un autre membre.

Boutons :

- **Personnaliser** : phrase personnalisée et couleur (hexadécimale, par exemple `#E268A1`).
- **Inventaire** : équiper un cosmétique possédé (un par type), ou **Tout retirer**. Au-delà de 25 cosmétiques, l’inventaire se répartit sur plusieurs menus.
- **Collections** : tableau des collections (voir ci-dessous).
- **Actualiser** : régénère la carte.

## Types de cosmétiques

| Type | Valeur | Image | Rôle sur la carte |
|---|---|---|---|
| Titre | `title` | Non | Ligne de texte (champ « valeur facultative ») |
| Badge | `badge` | Oui | Petite image |
| Arrière-plan | `background` | Oui | Fond de la carte |
| Cadre | `frame` | Oui | Cadre autour de la carte |
| Effet | `effect` | Selon l’effet | Effet visuel (par exemple `snow`) |

Les images sont rangées dans `assets/profile/` (`badges/`, `backgrounds/`, `frames/`, `effects/`).

## `/profil-admin`

| Bouton | Rôle |
|---|---|
| 🆕 **Créer un cosmétique** | Un cosmétique avec son image envoyée depuis ton PC, aperçu sur ta carte |
| 📦 **Créer une collection** | Fond, cadre, badge et effet d’un même thème en une fois (+ un titre), avec aperçu et confirmation |
| ✏️ **Modifier un cosmétique** | Choisir un thème puis un cosmétique, voir sa fiche et son aperçu, changer son image ou le renommer |
| ❔ **Guide des images** | Rappel des formats attendus pour chaque type |
| 🎁 **Distribuer** | Donne un cosmétique à un membre (plusieurs menus au-delà de 25 cosmétiques) |
| 📚 **Catalogue** | Tous les cosmétiques par thème, avec ID, nom affiché, identifiant, prix et nombre de membres qui l’ont |
| 🗑️ **Supprimer un cosmétique** | Le retire définitivement (retire-le d’abord des boutiques) |

### Les 5 types et leurs images

| Type | Ce que c’est | Image à envoyer | Ce que fait le bot |
|---|---|---|---|
| 🖼️ **Fond** (`background`) | L’arrière-plan de la carte de profil | Toute image, idéalement **1200 × 500** (2,4 fois plus large que haute), pas besoin de transparence | Recadrée au centre en 1200 × 500. Prévient si l’image est petite (flou) ou d’un format très différent |
| 🔲 **Cadre** (`frame`) | Le contour posé par-dessus la carte | **PNG 1200 × 500 avec le centre transparent** et le contour opaque | Redimensionné en 1200 × 500. La carte est découpée selon la forme du cadre (coins arrondis compris). **Refusé** si le centre n’est pas transparent (il cacherait toute la carte) |
| 🏅 **Badge** (`badge`) | La petite icône en haut à droite | **PNG carré, idéalement 256 × 256, fond transparent** | Mis dans un carré 256 × 256 sans déformation. Prévient s’il n’est pas carré ou sans transparence |
| ✨ **Effet** (`effect`) | Un calque par-dessus tout (neige, paillettes, lumière…) | **PNG 1200 × 500 surtout transparent** | Redimensionné en 1200 × 500. **Refusé** s’il n’est pas assez transparent. Avec la valeur `snow` (ou « snow » / « neige » dans le thème), le bot ajoute en plus une neige dessinée par-dessus |
| 🏷️ **Titre** (`title`) | Un texte affiché sous le pseudo | Pas d’image : juste le texte | — |

Formats acceptés : PNG, JPG, WEBP, GIF (première image), 25 Mo et 50 mégapixels maximum. **Pour un cadre, un badge ou un effet, utilise un PNG** : le JPG n’a pas de transparence.

### 🆕 Créer un cosmétique

Le formulaire demande :

1. **Type** : fond, cadre, badge, effet ou titre.
2. **Thème** : par exemple `volcan-2026`. L’identifiant est construit tout seul : **`type-thème`**, donc `frame-volcan-2026`. Les accents et espaces sont convertis (`Hiver Éternel` → `hiver-eternel`).
3. **Nom affiché** : ce que voient les membres, par exemple « Cadre volcan ».
4. **Image** : envoyée depuis ton PC (sauf pour un titre).
5. **Texte du titre / valeur d’effet** : le texte d’un titre (obligatoire pour un titre), ou `snow` pour un effet neige.

Le bot prépare l’image, crée le cosmétique, puis t’envoie un **aperçu de ta carte de profil avec ce cosmétique** (rien n’est équipé pour de vrai), son **ID** et les étapes suivantes. Un identifiant qui existe déjà est refusé : pour modifier un cosmétique, utilise ✏️ **Modifier un cosmétique**.

### 📦 Créer une collection

Le formulaire demande :

1. **Thème** : `volcan-2026`.
2. **Nom de la collection** : `Volcan` → les noms affichés seront « Fond Volcan », « Cadre Volcan », « Badge Volcan », « Effet Volcan ».
3. **Images** : 1 à 4 fichiers d’un coup.
4. **Titre de la collection** (facultatif) : crée aussi un titre `title-volcan-2026` avec ce texte (« Titre Volcan »).

**Comment le bot sait quelle image est quoi** : d’abord grâce au **nom du fichier** (`fond`, `background`, `bg` · `cadre`, `frame` · `badge`, `icone`, `logo` · `effet`, `effect`, `fx`, par exemple `volcan-cadre.png`). Sinon, il regarde l’image : carrée → badge ; opaque → fond ; centre transparent et contour plein → cadre ; sinon → effet. Testé sur tous les cosmétiques actuels : chacun est reconnu correctement.

Avant de créer quoi que ce soit, il affiche **la liste de ce qu’il a compris** (type, nom, identifiant, fichier d’origine, avertissements) et **l’aperçu de ta carte avec toute la collection équipée**. Tu confirmes avec ✅ **Créer la collection** ou tu annules. Deux images reconnues comme le même type, ou un identifiant déjà pris, sont refusés avec une explication.

La collection apparaît dans `/collections` dès qu’elle a au moins 2 objets.

### ✏️ Modifier un cosmétique

Rien à taper : tout se fait avec des menus.

1. **Choisis le thème** (🎃 Halloween 2026, 🌋 Volcan 2026…).
2. **Choisis le cosmétique** de ce thème (Fond, Cadre, Badge, Effet, Titre).
3. Sa **fiche** s’affiche : nom, type, identifiant, ID, thème, prix en boutique et dans la boutique de l’Avent, nombre de membres qui l’ont, et **l’aperçu sur ta carte de profil**. Avec trois boutons :
   - **🔁 Changer l’image** : envoie juste le nouveau fichier. Il est préparé selon le type du cosmétique (mêmes règles qu’à la création) et remplace l’ancien tout de suite : **les membres qui l’ont gardent le cosmétique** et voient la nouvelle image. Grisé pour un titre ;
   - **✏️ Renommer** : le nom affiché, et aussi le texte pour un titre ou la valeur d’un effet (`snow`) ;
   - **👁️ Aperçu** : revoir le rendu.

La fiche se met à jour après chaque changement. Fonctionne aussi pour les anciens cosmétiques dont l’image est un fichier du projet (la nouvelle image est alors gardée dans la base de données).

### Où sont gardées les images ?

Render **efface les fichiers à chaque redéploiement**. Les images envoyées depuis Discord sont donc enregistrées **dans la base de données** (Supabase), puis réécrites dans `assets/profile/uploaded/` à chaque démarrage du bot. Rien n’est perdu, et ce dossier n’est pas envoyé sur GitHub. Les anciens cosmétiques (fichiers du projet) continuent de fonctionner comme avant.

### Parcours complet d’un cosmétique

1. `/profil-admin` → 🆕 **Créer un cosmétique** (ou 📦 **Créer une collection**) et vérifier l’aperçu.
2. Le tester pour de vrai : 🎁 **Distribuer** sur ton propre compte, puis `/profil` → Personnaliser.
3. Le proposer aux membres :
   - en boutique : `/boutique-admin` → **Ajouter un cosmétique** (choisi dans une liste) ;
   - dans la boutique de l’Avent : `/avent-admin` → **Ajouter un cosmétique à la boutique** avec son **identifiant** ;
   - en récompense d’une case de l’Avent (type Cosmétique, ou `"cosmetic_id": ID` dans une case mystère), d’une mission ou d’un giveaway.

## Collections

`/collections [membre]` (ou le bouton **Collections** de `/profil`) affiche, pour chaque thème, les cosmétiques possédés et manquants, par exemple « 🌋 Volcan 2026 — 3/4 ». Les collections complètes apparaissent en premier.

- Les collections sont formées automatiquement à partir des identifiants : le premier mot est le type (`background`, `frame`, `badge`, `effect`, `title`, ou `fond`, `cadre`, `effet`, `titre`), le reste est le thème.
- Une collection compte au moins 2 cosmétiques ; un cosmétique seul (comme `title-bot`) n’apparaît pas.
- Les thèmes connus ont un nom et un émoji : hiver/snow, noël, volcan, océan, eau, nocturne, désert, forêt, temple, halloween. Un nouveau thème s’affiche avec son nom.
- Si le serveur possède des émojis nommés `clanrenard_yes` et `clanrenard_no`, ils remplacent ✅ et ❌.

---

# Classements, statistiques et bilan

## `/classement`

| Type | Contenu |
|---|---|
| XP | XP totale |
| Argent | Portefeuille actuel |
| Meilleure série quotidienne | Plus longue série de `/quotidien` |
| XP de la semaine | XP gagnée depuis lundi minuit (heure de Paris) |
| XP du mois | XP gagnée depuis le 1er du mois |

La carte montre 10 membres par page (boutons Précédent, Suivant, Rechercher) et le rang de la personne qui a lancé la commande. Les classements de la semaine et du mois se mettent à jour environ une fois par minute.

Les membres qui ont quitté le serveur sont masqués de tous les classements et ne comptent plus dans les rangs. Leurs données sont conservées : ils retrouvent leur place s’ils reviennent.

## `/stats`

Statistiques d’un membre pour **aujourd’hui** ou les **7 derniers jours** : XP gagnée, pièces gagnées, meilleure série, messages récompensés, temps vocal récompensé, progression vers le niveau suivant et classements actuels.

## `/bilan`

Carte de l’année du membre : XP gagnée et classement de l’année, messages, temps en vocal, pièces gagnées, jour le plus actif, récompenses quotidiennes, meilleure série et cases de l’Avent ouvertes.

- Ouvert aux membres du **31 décembre au 31 janvier** (en janvier, il montre l’année écoulée). Avant, la commande annonce qu’il arrive bientôt.
- Les administrateurs peuvent le consulter à tout moment, en privé.
- Les chiffres viennent des statistiques quotidiennes : si elles ont commencé en cours d’année, la carte l’indique (« Statistiques enregistrées depuis le … »).

---

# Calendrier de l’Avent

## Ouverture aux membres

Le calendrier s’ouvre et se ferme depuis Discord, sans toucher au code : `/avent-admin` → **Activer ou désactiver**.

- **Campagne désactivée** : `/avent` et tous les boutons du calendrier (boutique comprise) répondent « 🔒 Le calendrier de l’Avent est fermé pour le moment ». Les administrateurs continuent de tout voir pour préparer, avec un rappel « Calendrier désactivé ».
- **Campagne activée** : tout s’ouvre immédiatement.
- **Commande cachée** : tant qu’aucune campagne n’est activée, `/avent` n’apparaît même pas dans la liste des commandes des membres (seuls les administrateurs la voient). Elle réapparaît dès l’activation ; Discord peut mettre une minute à mettre à jour la liste.
- Une campagne nouvellement initialisée démarre **désactivée**, et la réinitialiser ne change pas son état.

## `/avent` et ses boutons

Chaque membre a son propre calendrier : une image avec ses 24 cases (ouvertes, disponibles, verrouillées, manquées), ses cases ouvertes et ses points gagnés.

Boutons : **Ouvrir la case**, **Actualiser**, **Profil**, **Récompenses**, **Classement**, **Boutique**, **Aide**. Les réponses sont visibles uniquement par le membre qui clique.

Les membres peuvent aussi tout faire depuis l’annonce quotidienne ou le panneau public, sans taper `/avent`. Ces boutons fonctionnent après un redémarrage du bot, y compris sur les anciennes annonces (« Ouvrir la case » ouvre toujours la case du jour).

## Ouverture des cases

- La case N s’ouvre le N décembre à l’heure d’ouverture choisie (00:00 par défaut), dans le fuseau de la campagne (`Europe/Paris` par défaut).
- Une case ne peut être ouverte qu’une fois, même en double-cliquant.
- Après le 24 décembre, la campagne est terminée.

## Rattrapage

Avec le rattrapage, un membre peut ouvrir des cases passées qu’il a manquées : « Ouvrir la case » propose alors un menu.

`/avent-admin` → **Limiter le rattrapage (jours)** ouvre un formulaire :

- un nombre de 1 à 23 : nombre maximal de jours en arrière (avec 3, le 10 décembre, les cases 7, 8 et 9 peuvent encore être ouvertes ; les plus anciennes sont manquées) ;
- `0` : rattrapage désactivé ;
- vide : rattrapage sans limite.

**Activer ou désactiver le rattrapage** bascule le rattrapage sans changer la limite.

## Récompenses des cases

`/avent-admin` → **Ajouter ou modifier une récompense** : choisir le type, puis remplir le formulaire. Une case qui a déjà une récompense est remplacée.

| Type | Ce que reçoit le membre |
|---|---|
| Message | Un message surprise |
| Points de l’Avent | Des points pour la boutique de l’Avent |
| Pièces | Des pièces permanentes |
| XP | De l’XP permanente (peut faire monter de niveau) |
| Cosmétique de profil | Un cosmétique, désigné par son identifiant `/profil-admin` |
| Rôle Discord | Un rôle |
| Aléatoire | Un tirage pondéré entre plusieurs récompenses (JSON) |

Dans une récompense aléatoire, les types `coins` (`{"coins": 200}`), `xp` (`{"xp": 500}`) et `cosmetic` (`{"cosmetic_id": 12}`) sont aussi utilisables.

Si un rôle, des pièces, de l’XP ou un cosmétique ne peuvent pas être versés, la case reste ouverte, le membre est prévenu, et la récompense apparaît « non créditée » ou « attribution échouée » dans son historique et dans **Consulter un membre**.

**Liste des récompenses**, **Supprimer une récompense** et **Aperçu du calendrier** complètent la gestion.

## Points, classement et boutique de l’Avent

- Les **points de l’Avent** sont propres à la campagne et se dépensent dans la boutique de l’Avent. Le calendrier affiche les points gagnés ; la boutique affiche le solde restant.
- Le **classement** de l’Avent range les membres par cases ouvertes, puis par points. Les membres partis sont masqués.
- La **boutique de l’Avent** (avec le bouton **👁️ Essayer** pour les cosmétiques) vend des rôles et des cosmétiques contre des points, avec éventuellement un nombre minimum de cases ouvertes. Elle a des pages au-delà de 25 articles. Un rôle acheté puis retiré peut être restauré gratuitement.
- Articles : `/avent-admin` → **Ajouter un rôle à la boutique**, **Ajouter un cosmétique à la boutique**, **Gérer les articles de la boutique**.
- **Gérer les articles de la boutique** affiche la liste des articles avec leur **identifiant**, leur prix, leur type et leurs cases minimum. Choisis un article dans le menu, puis :
  - **✏️ Modifier** : formulaire prérempli (nom affiché pour un rôle, prix, cases minimum, emoji, message après l’achat) ;
  - **🗑️ Retirer** : le retire de la boutique (confirmation par ce bouton).

## Annonces quotidiennes

Chaque jour, moins d’une minute après l’heure d’ouverture, le bot publie dans le canal choisi « 🎄 Jour N — Calendrier de l’Avent », avec les boutons du calendrier et, en option, la mention d’un rôle. Le 24, le texte change pour la dernière case.

Conditions : campagne activée, annonces activées (**Activer les annonces**, avec choix du rôle à mentionner) et canal choisi (**Modifier le canal**). Une seule annonce par jour ; si le bot était éteint à l’heure d’ouverture, elle part à son retour. Le rôle mentionné doit être mentionnable.

**Publier le panneau public** poste un panneau fixe avec les mêmes boutons, par exemple à épingler.

### Textes personnalisés (« 📝 Textes des annonces »)

Dans le menu de `/avent-admin`, **Textes des annonces** ouvre un panneau pour écrire les annonces sans toucher au code. Sans réglage, le texte d’origine est utilisé.

- **✏️ Texte par défaut** : le titre et le message de chaque jour, le message de la dernière case (24), et l’encart « Ouverture » affiché ou masqué. Un champ vidé reprend le texte d’origine.
- **📅 Message spécial d’un jour** : choisis un jour dans le menu et écris son message (par exemple « Bonne Saint-Nicolas ! 🎅 » le 6). Il remplace le message par défaut ce jour-là ; vide = message par défaut. Les jours concernés sont marqués ✏️.
- **📢 Jours @everyone** : par exemple `1, 24`. Ces jours-là, l’annonce mentionne @everyone au lieu du rôle habituel. Le bot doit avoir la permission « Mentionner @everyone » (le panneau prévient sinon).
- **👁️ Aperçu d’un jour** : l’annonce exacte de ce jour (titre, message, mention), visible par toi seul et sans notifier personne.
- **🔄 Textes d’origine** : tout remettre comme au départ (deux clics pour confirmer).

Variables : `{jour}`, `{jours_restants}` (jours avant la case 24), `{titre}` (titre de la campagne), `{serveur}`, `{heure}` (heure d’ouverture). Les textes sont propres à chaque campagne (année).

## `/avent-admin` : toutes les actions

- **Campagne** : Configuration, Initialiser une campagne, Activer ou désactiver, Modifier le canal, Modifier le fuseau, Modifier l’heure d’ouverture.
- **Rattrapage** : Activer ou désactiver le rattrapage, Limiter le rattrapage (jours).
- **Annonces** : Activer les annonces, Désactiver les annonces, Publier le panneau public.
- **Récompenses** : Liste des récompenses, Ajouter ou modifier une récompense, Supprimer une récompense, Aperçu du calendrier.
- **Membres** : Consulter un membre, Réinitialiser un membre, Réinitialiser TOUT LE MONDE.
- **Boutique de l’Avent** : ajouter un rôle, ajouter un cosmétique, gérer les articles (modifier ou retirer).

## Réinitialisations

- **Réinitialiser un membre** : efface ses cases ouvertes et ses achats dans la boutique de l’Avent, après confirmation.
- **Réinitialiser TOUT LE MONDE** : efface les cases et les achats de **tous** les membres pour la campagne. Deux verrous : un avertissement avec le nombre de membres, cases et achats concernés (60 secondes pour confirmer), puis un formulaire où il faut taper **RÉINITIALISER**. Un mot incorrect n’efface rien.
- Dans les deux cas, les récompenses, la boutique et la configuration restent intactes, et les rôles ou cosmétiques déjà distribués ne sont pas retirés.

## Date de test

La variable d’environnement `ADVENT_TEST_DATE` (par exemple `2026-12-05`) fait croire au bot qu’on est à cette date, pour tester en local. Elle ne doit **jamais** être définie sur Render, sinon le calendrier resterait bloqué sur ce jour.

---

# Mini-jeux et bingo

## `/jeu` : les mini-jeux

| Commande | Jeu |
|---|---|
| `/jeu morpion` | Morpion : aligner 3 symboles sur une grille 3×3 |
| `/jeu puissance4` | Puissance 4 : aligner 4 jetons sur une grille de 6×7 |
| `/jeu pfc [manches]` | Pierre-feuille-ciseaux en 1, 3 ou 5 manches (les égalités se rejouent) |
| `/jeu pendu` | Pendu : trouver le mot avant que le bonhomme soit pendu (7 erreurs) |

- **Contre l’IA** : laisser `adversaire` vide. Trois niveaux (`facile`, `normal`, `difficile`). Au morpion, l’IA difficile est imbattable. Au pierre-feuille-ciseaux, l’IA difficile apprend les habitudes du joueur. Pas de mise contre l’IA.
- **Contre un membre** : `adversaire:@membre`. Le défi s’affiche dans le salon avec trois boutons pour le défié : **Accepter**, **Autre mise** (contre-proposition, que le défieur doit à son tour accepter) et **Refuser**. Sans réponse en 3 minutes, le défi expire.
- **Qui commence** : tiré au sort.
- **Délai** : 2 minutes par coup (60 secondes par manche au pierre-feuille-ciseaux). Celui qui ne joue pas à temps perd. Si personne ne joue une manche, la partie est annulée.
- **🏳️ Abandonner** donne la victoire à l’adversaire.
- Une seule partie ou un seul défi à la fois par membre.

### Le pendu

- **En solo** (sans `adversaire`) : le bot choisit un mot, tu le cherches seul. `difficulte` règle la longueur des mots : facile (3 à 6 lettres), normal (6 à 9), difficile (9 et plus).
- **En duel** (`adversaire:@membre`, mise possible) : les deux joueurs cherchent **le même mot à tour de rôle**. Une bonne lettre fait rejouer, une erreur passe la main. Celui qui complète le mot gagne. Si le bonhomme est pendu, personne ne gagne et les mises sont rendues.
- Les lettres se choisissent dans deux menus (A à M, N à Z), sans accent : « E » révèle aussi É, È, Ê. **🔤 Proposer le mot** permet de tenter le mot entier (une erreur si c’est faux).
- La catégorie du mot est affichée (animaux, jeux vidéo, nourriture, nature, maison, fêtes et hiver). 7 erreurs maximum, 2 minutes par tour.

### Les mises

```text
/jeu puissance4 adversaire:@Renard mise:500
```

- La mise (jusqu’à 100 000 pièces) est la même pour les deux joueurs. Il faut que **les deux acceptent** : le défieur en lançant le défi, le défié en cliquant sur Accepter. Une contre-proposition change de main jusqu’à ce que l’un des deux accepte.
- Au début de la partie, les deux mises sont **retirées des portefeuilles**. Si l’un des deux n’a plus assez, la partie ne démarre pas.
- Le gagnant reçoit le tout (2 × la mise). En cas d’égalité ou de partie annulée, chacun est remboursé.
- Si le bot redémarre pendant une partie, elle est perdue et **les mises sont remboursées** au démarrage.
- Les gains de mise ne comptent pas comme de l’argent « gagné » pour les missions et le total historique (comme les dons).

### 🔁 Revanche

À la fin de chaque partie, un bouton **🔁 Revanche** apparaît sur le message, pendant **10 minutes**.

- **Contre un membre** : un nouveau défi part avec **le même jeu, les mêmes options et la même mise**. L’autre joueur doit l’accepter (ou proposer une autre mise), comme pour un défi normal.
- **Contre l’IA ou au pendu en solo** : une nouvelle partie démarre tout de suite, avec la même difficulté.
- Une seule revanche par partie : le bouton disparaît dès qu’un joueur clique dessus.
- Refusée si un joueur est déjà dans une autre partie, si l’adversaire a quitté le serveur, ou si celui qui la demande n’a plus assez de pièces pour la mise (le bouton reste alors disponible).

### `/jeu classement`

```text
/jeu classement jeu:Pendu tri:Victoires contre des membres
```

Les 10 meilleurs joueurs, tous jeux confondus ou pour un seul jeu, avec trois façons de classer :

- **Victoires contre des membres** (par défaut), avec le pourcentage de victoires ;
- **Gains des mises** : le bilan en pièces de tous les paris ;
- **Victoires contre l’IA / en solo**.

Si tu n’es pas dans le top 10, ta place s’affiche en dessous. Les membres partis du serveur sont masqués, comme dans les autres classements.

### `/jeu stats`

Victoires, défaites et nuls par jeu, séparés entre parties contre des membres et contre l’IA (ou en solo pour le pendu), avec le bilan des mises.

## `/bingo` (administration)

```text
/bingo lancer pieces:1000 maximum:500 manches:3 duree:1h salon:#bingo
```

Le bot tire un nombre au hasard. Les membres **écrivent leurs nombres directement dans le salon**, autant qu’ils veulent : un message qui n’est qu’un nombre (`42`, `1 000`) compte comme une proposition, le reste de la discussion est ignoré. Le premier qui trouve gagne : le bot réagit 🎉, lui répond et verse la récompense.

**Les indices, c’est l’animateur** : l’admin qui lance le bingo reçoit le nombre en privé dans la confirmation, et le donne en indices comme il veut dans le salon (« plus grand ! », « il y a un 7 »…). À chaque nouvelle manche, il reçoit le nouveau nombre en message privé.

| Option | Rôle | Par défaut |
|---|---|---|
| `pieces`, `xp` | Récompense de chaque gagnant | rien (« pour la gloire ») |
| `minimum`, `maximum` | Bornes du nombre | 1 à 100 |
| `manches` | Nombre de manches : un nouveau nombre et un nouveau gagnant à chaque fois (10 max) | 1 |
| `duree` | Durée maximale (de 1 minute à 1 jour) | 30 minutes |
| `essais` | Nombre d’essais par membre et par manche (0 = illimité). Au-delà, le bot réagit ⛔ une fois | illimité |
| `message` | Texte affiché sur le bingo | — |
| `salon` | Salon du bingo | salon actuel |

| Commande | Rôle |
|---|---|
| `/bingo nombre [salon]` | Affiche en privé le nombre en cours (pour qu’un autre admin aide à animer) |
| `/bingo arreter [salon]` | Arrête le bingo et révèle le nombre |

- **Qui connaît le nombre ne joue pas** : l’admin qui a lancé le bingo et ceux qui ont fait `/bingo nombre`. Leurs nombres sont ignorés (le bot réagit 🤫 une fois).
- Anti-spam léger : un nombre toutes les 0,8 seconde par membre, les autres sont ignorés.
- Le message du bingo affiche le nombre de joueurs et de propositions (mis à jour toutes les 5 secondes) et les gagnants de chaque manche. À la fin du temps, le nombre est révélé.
- Un seul bingo à la fois par salon. Un bingo en cours continue après un redémarrage du bot.
- La récompense compte comme de l’argent gagné (comme un drop) et peut faire monter de niveau.
- Le bot doit pouvoir **ajouter des réactions** et **voir les anciens messages** dans le salon.

### Lecture des messages : « Message Content Intent »

Pour lire les nombres écrits dans le salon, l’option **Message Content Intent** doit être cochée sur le [Discord Developer Portal](https://discord.com/developers/applications) (application du bot → **Bot** → *Privileged Gateway Intents*), comme *Server Members Intent*.

Si elle n’est pas cochée, le bot ne reste pas hors ligne : il redémarre tout seul sans lire les messages (une erreur l’explique dans les logs Render), et les nouveaux bingos passent par un bouton **🎯 Proposer un nombre** qui ouvre une fenêtre de saisie.

---

# Outils : rappels, rôles à la réaction, aide

## `/rappel`

```text
/rappel raison:Lancer la partie temps:1h30 destination:Dans ce salon
```

- Durées acceptées : `10s`, `10m`, `5mn`, `2h`, `1h30`, `1j12h`, `3sem`, ou un nombre seul en minutes (`45`). De 10 secondes à 90 jours.
- Destination : dans le salon (y compris le chat d’un salon vocal) ou en message privé. Si l’une n’est pas possible, le rappel part par l’autre.
- **Relancer le rappel** reprogramme le même rappel avec la même durée.

## Anniversaires

### `/anniversaire` (membres)

Ouvre un panneau visible par le membre seul :

- **🎂 Enregistrer** / **Modifier ma date** : jour, mois et, si on veut, l’année de naissance (seulement pour afficher l’âge). La date peut être modifiée **une fois tous les 30 jours** ; en cas d’erreur, un admin peut la retirer.
- **🙈 Cacher mon âge** / **🎈 Afficher mon âge** : l’âge n’apparaît dans les souhaits que si le membre a donné son année et l’accepte.
- **🗑️ Retirer** (deux clics pour confirmer).
- **📅 Prochains anniversaires** du serveur (jour et mois seulement, jamais l’année ; membres partis masqués).
- Le panneau indique dans combien de jours tombe l’anniversaire. Né un 29 février : fêté le 28 février les années non bissextiles.

### `/anniversaires-liste` (public)

Affiche dans le salon, pour tout le monde, les 10 prochains anniversaires (jour et mois, compte à rebours, « aujourd’hui ! » le jour J). Les mentions de la liste ne notifient personne. N’importe quel membre peut la lancer.

### `/anniversaire-admin`

| Bouton | Rôle |
|---|---|
| ▶️ **Activer** / ⏸️ **Désactiver** | Souhaits automatiques |
| 📍 **Salon et rôle** | Salon des souhaits, et rôle donné pour la journée (retiré automatiquement le lendemain) |
| ⏰ **Heure et cadeau** | Heure des souhaits (Paris), pièces et XP offertes |
| ✏️ **Message et carte** | Message, titre (cadre et carte), sous-titre et texte du bas de la carte |
| 🖼️ **Fond** | Fond de la carte (même style que la carte de bienvenue) |
| 🎨 **Style** | **Cadre** (par défaut) : la mention du membre, puis un cadre rose aux couleurs du bot avec son avatar, le message, son âge et le cadeau, signé « L’équipe Clan Renard 🦊 ». **Carte image** : le message et la carte, comme la bienvenue. **Cadre + carte** : le cadre avec la carte en grande image |
| 📨 **Tester dans le salon** | Envoie les souhaits avec ton profil (sans rôle ni cadeau) |
| 📋 **Liste** | Tous les anniversaires enregistrés, dans l’ordre |
| 🗑️ **Retirer un membre** | Retire la date d’un membre (date fausse, troll…) |

Variables : `{membre}` (mention), `{nom}`, `{serveur}`, `{age}` (« 21 ans ! » si l’âge est connu et affiché, sinon rien).

- Le jour J, à l’heure choisie, le bot poste les souhaits (avec la carte), donne le rôle et le cadeau. Un membre qui enregistre sa date le jour même, après l’heure, est fêté dans les 5 minutes.
- **Une seule célébration par membre et par an**, même si la date est changée, retirée puis remise : impossible de récupérer le cadeau plusieurs fois.
- Le cadeau compte comme de l’argent gagné et peut faire monter de niveau. Les membres partis et les bots ne sont pas fêtés.
- Le bot doit pouvoir écrire et joindre des fichiers dans le salon, et, pour le rôle, avoir « Gérer les rôles » avec son rôle placé au-dessus du rôle d’anniversaire (le panneau prévient sinon).

## Rôles à la réaction

| Commande | Rôle |
|---|---|
| `/reaction-role` | Lie un émoji, sur un message, à un rôle. Le bot ajoute lui-même la réaction. |
| `/reaction-role-retirer` | Supprime une association. |
| `/reaction-role-liste` | Liste les associations du serveur. |

Réagir donne le rôle, retirer sa réaction l’enlève. Les émojis personnalisés restent reconnus s’ils sont renommés ou animés.

## `/membres-role`

Ouvre un panneau avec un menu de rôles. Choisir un rôle **répond dans un nouveau message** avec la liste de ses membres, puis **le menu se remet à zéro** : on peut rechoisir le même rôle pour avoir la liste à jour, sans retaper la commande.

La liste est un tableau aligné, au même format que « Donner aux membres actuels » de `/bienvenue-admin` :

| Colonne | Contenu |
|---|---|
| `#` | Numéro (triés par date d’arrivée, les plus anciens d’abord) |
| Compte | Nom du compte Discord (pas le pseudo du serveur) |
| ID | Identifiant du membre |
| Arrivée | Date d’arrivée sur le serveur |

- 15 membres par page, avec ◀️ ▶️ s’il y en a plus.
- 🔄 bascule entre les membres **qui ont** le rôle et ceux **qui ne l’ont pas**.
- 📄 envoie la liste complète en .txt (avec le pseudo du serveur).
- Les bots sont exclus de la liste (leur nombre est indiqué).

## `/aide`

Liste les commandes membres, classées par thème. La liste se construit automatiquement : une nouvelle commande y apparaît sans rien modifier. Les administrateurs voient aussi les commandes d’administration.

---

# Bienvenue et départs

Quand un membre arrive (ou part), le bot poste un message avec une **carte image**, dans l’esprit de Koya : le fond de ton choix, l’avatar du membre dans un cercle, un grand titre, un sous-titre en couleur et une ligne de texte.

## `/bienvenue-admin`

Ouvre un panneau, visible par toi seul, avec **l’aperçu de la carte** (avec ton profil), mis à jour à chaque changement. Le menu du haut passe des **👋 Arrivées** aux **🚪 Départs** : chacun a ses propres réglages.

| Bouton | Rôle |
|---|---|
| ▶️ **Activer** / ⏸️ **Désactiver** | Envoi automatique à chaque arrivée (ou départ) |
| 📍 **Salon** | Salon où le message est posté |
| ✏️ **Textes** | Message au-dessus de la carte, titre, sous-titre, texte du bas |
| 🖼️ **Fond** | Image de fond envoyée depuis ton PC (jusqu’à 50 Mo et 50 mégapixels ; Discord limite à 10 Mo sans Nitro), recadrée en 1024 × 500 et compressée, ou retour au fond par défaut |
| 🎨 **Couleurs** | Couleur du titre, du sous-titre, du texte et du contour de l’avatar, assombrissement du fond (0 à 90 %) |
| 🌫️ **Ombre du texte** | Effet derrière les textes : ombre douce (par défaut, comme Koya), contour, les deux ou aucun ; couleur, opacité, flou et décalage réglables (décalage 0 + flou fort = halo néon) |
| 🔤 **Police** | Roboto (par défaut), Poppins, ou **une police importée** (.ttf/.otf/.woff, 10 Mo max) gardée en base de données, jamais sur GitHub. Police exacte de Koya : « Uni Sans Heavy », gratuite sur fontsquirrel.com (licence : images autorisées, redistribution du fichier interdite) |
| 📐 **Disposition « classique »** | Mêmes proportions que la carte Classic de Koya (avatar 250 px en haut, textes mesurés sur une vraie carte Koya) |
| 📐 **Disposition** | Centre (avatar en haut, comme Koya), gauche ou droite (avatar sur le côté, texte à côté) |
| 🃏 **Carte : oui / non** | Message seul, sans image |
| 👁️ **Aperçu réel** | Le message complet (texte et carte) exactement comme les membres le verront, visible par toi seul |
| 🧩 **Modèles** | Enregistrer l’apparence actuelle sous un nom, charger un modèle (l’aperçu se met à jour), supprimer |
| 📨 **Tester dans le salon** | Envoie un vrai message avec ton profil, pour voir le rendu final |
| 🎭 **Rôles à l’arrivée** *(arrivées)* | Jusqu’à 3 rôles donnés à chaque nouveau membre dès son arrivée, et gardés ensuite (comme le rôle « Membre » de DraftBot). Aucun rôle = désactivé |
| 👥 **Donner aux membres actuels** *(arrivées)* | Donne ces rôles aux membres déjà présents qui ne les ont pas, après confirmation. La confirmation affiche la liste des membres concernés (n°, nom du compte, ID, date d’arrivée), 15 par page avec ◀️ ▶️, triée par date d’arrivée, et 📄 envoie la liste complète en .txt (avec le pseudo du serveur) |

Chaque changement est enregistré tout de suite (si l’envoi automatique est activé, il s’applique dès la prochaine arrivée).

**Modèles** : un modèle garde l’apparence (message, textes, couleurs, disposition, assombrissement, carte oui/non et fond), pas le salon ni l’activation. Un admin crée la carte et l’enregistre, un autre la charge depuis 🧩 Modèles et regarde l’aperçu. Un modèle s’applique aux arrivées ou aux départs, selon le menu du haut. 25 modèles maximum.

**Variables** (message et carte) : `{membre}` (mention dans le message, nom sur la carte), `{nom}` (nom affiché), `{pseudo}` (nom d’utilisateur), `{serveur}`, `{nombre}` (nombre de membres).

Par défaut : « Bienvenue {membre} ! » avec la carte **BIENVENUE / {nom} / Nous sommes {nombre} à présent !**, et pour les départs « **{nom}** nous a quittés. » avec la carte **AU REVOIR**. Les deux sont désactivés tant que tu ne les actives pas.

- Les bots qui rejoignent le serveur ne sont pas accueillis.
- **Rôles à l’arrivée** : donnés même si le message de bienvenue est désactivé, jamais aux bots. Si le serveur demande d’accepter le règlement avant d’entrer, le rôle est donné juste après l’acceptation. Le bot doit avoir « Gérer les rôles » et son rôle doit être au-dessus de ceux qu’il donne (le panneau prévient sinon). Pense à désactiver le rôle automatique de DraftBot.
- Au départ, le nom du membre n’est pas une mention qui notifie.
- Le bot doit pouvoir **voir le salon, y écrire et joindre des fichiers** : le panneau prévient s’il manque quelque chose.
- La police épaisse des titres (Roboto Black) est installée sur Render.

---

# Annonces

Le bot publie les annonces à ta place : le message est signé par le bot, avec le logo et le nom du serveur, et tout se règle depuis Discord.

## `/annonce creer` : le studio

Ouvre un panneau visible par toi seul. En haut, l’**aperçu exact** de l’annonce, mis à jour après chaque changement. En dessous, les boutons :

| Bouton | Rôle |
|---|---|
| ✏️ **Texte** | Titre, lien du titre, contenu du cadre (4 000 caractères), message au-dessus du cadre |
| 🎨 **Style** | Couleur de la barre (`#F28C28` ou `orange`, `rouge`, `bleu`…), en-tête, pied de page, date, logo du serveur |
| 🖼️ **Images** | Grande image et miniature, en **fichier envoyé depuis le PC** (8 Mo max) ou en lien |
| 📑 **Sections** | Blocs « titre + texte », côte à côte ou empilés |
| 🔗 **Boutons et réactions** | Boutons liens sous l’annonce (25 max), une ligne par bouton : `🎮 Texte \| https://lien`. Et les réactions que le bot ajoute sous l’annonce (20 max), séparées par des espaces : `👍 🎉 :clanrenard_yes:` |
| Menu **Cadre** | Choisir le cadre à modifier, en ajouter (10 max) ou en supprimer |
| 📣 **Salon et mention** | Salon de publication, mention (personne, @everyone, @here ou un rôle) |
| 🧩 **Modèles** | Charger, enregistrer ou supprimer une annonce type (25 max) |
| 📥 **Importer** / 📤 **Exporter** | Échange avec Discohook (voir plus bas) |
| ❔ **Aide** | Rappel de la mise en forme et des raccourcis |
| 🚀 **Publier** | Demande confirmation (salon, mention), puis publie |
| ⏰ **Programmer** | Publie automatiquement à la date choisie |
| 📐 **Format** | Classique, grand ou pleine largeur (voir plus bas) |
| 👁️ **Aperçu réel** | En format grand ou pleine largeur : montre l’annonce exactement comme elle sera publiée |
| 🔄 **Recommencer** | Efface le brouillon (deux clics pour confirmer) |

- **Brouillon enregistré** : chaque changement est sauvegardé. Le studio se ferme au bout de 14 minutes (limite de Discord), `/annonce creer` le rouvre exactement où tu en étais.
- **Signature automatique** : un nouveau brouillon a déjà l’en-tête « Clan Renard » avec le logo, le pied de page « L’équipe Clan Renard » et la date de publication. Tout se change dans 🎨 Style.
- **Sections** : une ligne `## Titre` puis le contenu en dessous.
- **Réactions** : le bot les ajoute juste après la publication (sur le dernier message d’une longue annonce). Les émojis du serveur s’écrivent `:nom:`. Un émoji d’un autre serveur ou supprimé est signalé sans bloquer l’annonce. En modification, le bot ajoute les nouvelles réactions et retire les siennes qui ne sont plus dans la liste (les réactions des membres restent). Il faut les permissions « Ajouter des réactions » et « Voir les anciens messages ».
- **Contrôles avant publication** : annonce vide, textes trop longs, salon manquant, permissions du bot (envoyer, intégrer des liens, joindre des fichiers, mentionner @everyone). Mentionner @everyone ou un rôle non mentionnable demande aussi que **toi** en aies le droit.

### Les trois formats

- **Classique** (par défaut) : le cadre habituel des bots. Sa largeur maximale est fixée par Discord.
- **Grand** : le nouveau type de message de Discord, où chaque cadre devient un bloc avec la barre de couleur. L’en-tête et le pied de page deviennent du petit texte gris, les sections s’empilent (pas de colonnes) et les boutons liens sont dans le dernier bloc. Discord y limite le texte total à 4 000 caractères.
- **Pleine largeur** : un **message texte normal**, sans cadre ni barre de couleur, qui prend toute la largeur du salon comme un message écrit par un membre. Le titre est en gros, l’en-tête et le pied de page en petit texte gris. Les images envoyées sont jointes en dessous, les liens d’images s’affichent en aperçu, pas de miniature.
  - **Longues annonces** : un bot est limité à 2 000 caractères par message (pas de Nitro pour les bots). Au-delà, l’annonce est publiée en **plusieurs messages à la suite** (5 maximum, environ 10 000 caractères), coupés entre deux paragraphes. Discord les colle, ça se lit comme un seul message. La mention est dans le premier (une seule notification), les images et les boutons dans le dernier. Le studio indique combien de messages seront publiés.
  - Si l’envoi d’un morceau échoue, les morceaux déjà partis sont supprimés : pas d’annonce coupée en deux.
  - `/annonce modifier` accepte le lien de n’importe quel morceau et met à jour tous les messages. Le texte peut raccourcir (les morceaux en trop sont supprimés), mais pas demander plus de messages qu’à la publication (on ne peut pas insérer un message au milieu du salon).
- Le bouton 📐 passe d’un format à l’autre : classique → grand → pleine largeur.
- L’aperçu du studio reste au format classique : 👁️ **Aperçu réel** montre les autres formats tels quels.
- Le format choisi est gardé pour l’annonce suivante. Une annonce publiée ne peut pas passer au format grand, ni en sortir (règle de Discord) : il faut en publier une nouvelle.
- Les :émojis: du serveur écrits sous la forme `:nom:` sont convertis automatiquement, dans les deux formats.

### Dates à l’heure de chaque membre

Dans les textes et les sections, ces raccourcis deviennent des dates Discord, affichées dans le fuseau de chaque membre :

| Raccourci | Affichage |
|---|---|
| `{date:25/12 18h}` | date et heure complètes |
| `{dans:25/12 18h}` | « dans 3 jours » (compte à rebours) |
| `{jour:25/12}` | « 25 décembre 2026 » |
| `{heure:18h30}` | « 18:30 » |

Formats compris : `25/12/2026 18:00`, `25/12 18h`, `01/12 18h30`, `demain 21h`, `aujourd’hui 20h`. Sans année, c’est la prochaine fois que la date arrive. L’heure saisie est celle de `DEFAULT_TIMEZONE` (Europe/Paris).

### Émojis, rôles et salons

Dans n’importe quel salon, taper `\:emoji:`, `\@Rôle` ou `\#salon` puis envoyer affiche leur code (`<:renard:123…>`, `<@&123…>`, `<#123…>`). Ce code se colle dans le studio.

## Programmer une annonce

⏰ **Programmer** accepte `01/12 18h`, `25/12/2026 18:00`, `demain 9h` ou `dans 2h` (d’une minute à un an). L’annonce est figée à ce moment-là et le studio repart sur un brouillon vide.

`/annonce programmees` liste les envois en attente :

- **Annuler un envoi** : il ne sera pas publié.
- **Reprendre dans le studio** : annule l’envoi et rouvre l’annonce pour la modifier, puis la reprogrammer.

Si l’envoi échoue au moment prévu (salon supprimé, permission retirée…), l’auteur reçoit un message privé et l’erreur est notée dans le journal de modération. Un envoi interrompu par un redémarrage du bot repart au démarrage suivant.

## `/annonce modifier`

```text
/annonce modifier lien:https://discord.com/channels/…
```

Le lien s’obtient par clic droit sur le message → **Copier le lien du message**. Le studio s’ouvre sur l’annonce publiée, et 💾 **Enregistrer les modifications** la corrige sur place, sans republier ni renvoyer de notification. **Quitter la modification** abandonne sans rien changer.

Seuls les messages du bot peuvent être modifiés. Pour un message qui n’a pas été créé avec le studio, le bot le reconstruit à partir de ce qui est affiché : il vaut mieux renvoyer ses images avec 🖼️.

Si tu avais un brouillon en cours, il est gardé automatiquement dans 🧩 Modèles (« Brouillon du … »).

## Discohook : les mises en page très précises

[discohook.app](https://discohook.app) est un éditeur web gratuit pour construire un message à la souris.

- **Importer** : sur Discohook, ouvrir l’éditeur JSON, copier, puis 📥 **Importer** dans le studio (coller le texte, ou envoyer un fichier `.json` pour les longs messages). Les sauvegardes Discohook sont acceptées (seul le premier message est pris). Les boutons liens sont gardés, les boutons d’action sont ignorés.
- **Exporter** : 📤 **Exporter** envoie un fichier `annonce.json` à coller dans l’éditeur JSON de Discohook. Les images envoyées depuis Discord ne sont pas exportées (seulement les liens).

## `/annonce historique` et journal

`/annonce historique` liste les 15 dernières annonces publiées, avec leur lien, l’auteur et la date de modification éventuelle. Chaque publication, modification, programmation ou annulation est aussi notée dans le salon de journal de la modération (s’il est réglé dans `/moderation-admin`).

Les images envoyées sont stockées dans la base. Celles qui ne servent plus à aucun brouillon, modèle, envoi programmé ou annonce publiée sont supprimées automatiquement après 2 jours.

---

# Modération

## Les sanctions

| Commande | Permission | Effet |
|---|---|---|
| `/warn membre raison` | Exclure temporairement | Avertissement (compte pour l’échelle automatique) |
| `/mute membre duree [raison]` | Exclure temporairement | Exclusion temporaire de Discord : le membre ne peut plus écrire, réagir ni parler (28 jours max) |
| `/unmute membre [raison]` | Exclure temporairement | Met fin à l’exclusion |
| `/kick membre [raison]` | Expulser | Expulse du serveur (retour possible avec une invitation) |
| `/ban membre [duree] [raison] [supprimer_messages]` | Bannir | Sans durée : définitif. Avec durée (`3j`, `2sem`…) : **bannissement temporaire**, levé automatiquement (1 an max) |
| `/unban identifiant [raison]` | Bannir | Lève un bannissement |
| `/amende membre montant raison` | Exclure temporairement | Retire des pièces du portefeuille (jamais sous 0) |
| `/pardon numero [raison]` | Exclure temporairement | **Annule** une sanction : retire l’avertissement du compte, démute, débannit ou rembourse l’amende |

Chaque sanction :

1. reçoit un **numéro de cas** (`#12`) et entre dans le casier du membre ;
2. est envoyée au membre en **message privé** (raison, durée, numéro), avant l’expulsion ou le bannissement pour qu’il la reçoive ;
3. est publiée dans le **salon du journal** ;
4. est confirmée au modérateur en privé, avec un avertissement si le message privé n’a pas pu partir.

Garde-fous : impossible de se sanctionner soi-même, de sanctionner le bot ou le propriétaire du serveur, ou un membre dont le rôle est égal ou supérieur au sien. Le bot prévient aussi si un membre est au-dessus de son propre rôle. Si Discord refuse l’action, aucun cas n’est enregistré.

## Échelle de sanctions automatiques

Les avertissements s’additionnent et déclenchent des sanctions automatiques. Par défaut :

```text
3 = mute 1h
5 = mute 1j
7 = ban 7j
```

- Un avertissement compte pendant **30 jours** (réglable). Un avertissement annulé avec `/pardon` ne compte plus.
- Le palier s’applique quand le membre atteint exactement ce nombre d’avertissements ; la sanction automatique a son propre numéro de cas, avec la raison « Sanction automatique : N avertissements ».
- Actions possibles : `mute <durée>`, `kick`, `ban <durée>` ou `ban` (définitif).
- Le casier affiche la prochaine sanction automatique (« Prochaine sanction automatique à 5 : exclusion de 1 j »).

## Contestations

Quand un salon de contestations est choisi dans `/moderation-admin`, le message privé d’un avertissement, d’une exclusion, d’un bannissement ou d’une amende contient un bouton **📨 Contester**.

1. Le membre explique sa version dans un formulaire (une seule contestation par sanction).
2. La contestation arrive dans le salon choisi, avec le détail de la sanction et deux boutons : **Accepter et annuler la sanction** / **Refuser**.
3. Accepter annule la sanction (comme `/pardon`) ; dans les deux cas, le membre reçoit la décision en message privé.

Seuls les membres ayant la permission « Exclure temporairement des membres » peuvent décider. Les boutons fonctionnent après un redémarrage du bot.

## Casier et notes

- `/casier membre` (privé) : identité, ancienneté du compte et sur le serveur, état actuel (exclu, banni…), avertissements actifs et prochaine sanction automatique, total par type, les 12 dernières sanctions (les annulées sont barrées) et les notes de l’équipe. Fonctionne aussi pour un membre parti ou banni.
- `/note ajouter membre texte` : note privée de l’équipe sur un membre (il n’en est pas informé).
- `/note supprimer numero` : supprime une note (`n7` dans le casier → numéro `7`).

## Outils de salon

- `/clear nombre [membre]` : supprime jusqu’à 100 messages récents, éventuellement d’un seul membre. Les messages épinglés sont conservés.
- `/lock [salon] [raison]` : plus personne ne peut écrire ni réagir dans le salon (sauf l’équipe) ; un message l’annonce.
- `/unlock [salon]` : rouvre le salon.

## Modération automatique

Réglée dans `/moderation-admin`. Les trois filtres utilisent l’**AutoMod de Discord** : Discord bloque le message **avant** qu’il soit publié et affiche un message au membre, puis le bot lui donne un avertissement (au plus un par minute et par filtre), ce qui alimente l’échelle de sanctions.

| Filtre | Effet |
|---|---|
| 🔗 Liens d’invitation | Bloque les invitations vers d’autres serveurs Discord |
| 🚫 Mots interdits | Bloque les messages contenant un mot de la liste (`*morceau*` pour une partie de mot) |
| 📣 Mentions de masse | Bloque les messages avec trop de mentions |
| 💬 Anti-spam | Trop de messages en peu de temps (par exemple 6 en 8 s) → exclusion de quelques minutes et suppression des messages |

Les membres qui ont la permission « Gérer le serveur » (ou « Gérer les messages » pour l’anti-spam) ne sont pas concernés. Les règles créées par le bot s’appellent « Clan Renard • … » dans Paramètres du serveur → AutoMod : modifie-les depuis `/moderation-admin`, pas à la main.

## `/moderation-admin`

| Bouton | Réglage |
|---|---|
| 📋 Salon du journal | Salon où sont publiées toutes les sanctions (réservé à l’équipe, de préférence) |
| 📨 Contestations | Salon des contestations, ou désactivation |
| ⚡ Échelle de sanctions | Paliers (un par ligne) et durée de validité d’un avertissement |
| 🔗 Liens d’invitation | Active ou désactive le filtre |
| 🚫 Mots interdits | Liste séparée par des virgules (vide = désactiver) |
| 📣 Mentions de masse | Nombre maximal de mentions par message (0 = désactiver) |
| 💬 Anti-spam | Nombre de messages, fenêtre en secondes, durée d’exclusion (0 message = désactiver) |

## Permissions du bot

Pour que tout fonctionne, le rôle du bot doit avoir : **Exclure temporairement des membres**, **Expulser des membres**, **Bannir des membres**, **Gérer les messages**, **Gérer les salons** et **Gérer le serveur** (pour l’AutoMod), et être placé au-dessus des rôles des membres à sanctionner. Discord ne permet pas d’exclure temporairement un administrateur.

---

# Maintenance : sauvegardes, import, permissions

## Sauvegarde de la base

Les données sont sur Supabase. Pour en garder une copie sur ton PC :

1. Ajouter dans le fichier `.env` du bot la ligne `DATABASE_URL=...` (la même valeur que sur Render). Ce fichier n’est jamais envoyé sur GitHub.
2. Depuis le dossier du bot :

```text
python scripts/sauvegarder_base.py
```

Le script crée `sauvegardes/clan-renard-AAAA-MM-JJ_HH-MM.zip` : un fichier CSV par table (lisible dans Excel) et `informations.json` avec le nombre de lignes de chaque table. Le dossier `sauvegardes/` est exclu de git et de l’image Docker, car la base contient les identifiants Discord des membres.

### Restaurer une sauvegarde

```text
python scripts/restaurer_base.py sauvegardes/clan-renard-AAAA-MM-JJ_HH-MM.zip
```

- Arrêter le bot pendant la restauration.
- Les tables sont **vidées puis remplies** avec la sauvegarde : tout ce qui a changé depuis est perdu. Le script demande de taper `RESTAURER`.
- En cas d’erreur, rien n’est modifié.
- Sur une base neuve, démarrer d’abord le bot une fois pour qu’il crée les tables.

## Import DraftBot

`/import_draftbot` importe niveaux et XP depuis un export HTML de DraftBot, en reconnaissant les membres par leur identifiant Discord.

- Sans `confirmer:Oui`, la commande affiche seulement un aperçu ; rien n’est importé.
- `remplacer_xp_existante:Oui` remplace l’XP du bot par celle de DraftBot ; sinon, l’XP est recalculée pour la courbe de Clan Renard.
- `attribuer_roles:Oui` donne ensuite les rôles de niveau.

Faire une sauvegarde avant un import ; l’extension peut être retirée une fois la migration terminée.

## Permissions et hiérarchie des rôles

Pour donner des rôles (niveaux, boutiques, Avent, giveaways, rôles à la réaction), le bot doit avoir la permission **Gérer les rôles**, et son rôle doit être placé **au-dessus** des rôles qu’il distribue. Il ne peut pas gérer `@everyone`, ni un rôle géré par Discord ou par une intégration.

## Données et redémarrages

Tout est enregistré dans PostgreSQL (Supabase) : un redémarrage ou un redéploiement ne perd ni l’XP, ni l’argent, ni les inventaires, ni les cases ouvertes, ni la configuration.

Après un redémarrage :

- les boutons du calendrier de l’Avent, des giveaways, des drops, des contestations et « Relancer le rappel » continuent de fonctionner ;
- les autres panneaux ouverts (boutique, profil, classement…) répondent « Ce panneau ne répond plus » : il suffit de relancer la commande.

## Images générées

Le bot dessine en mémoire, avec Pillow, le calendrier, le profil, la carte de progression, le classement, les statistiques et le bilan, à partir des données, des cosmétiques équipés et des images du dossier `assets/`. Elles ne sont pas enregistrées sur le disque.
