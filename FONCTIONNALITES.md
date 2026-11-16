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
10. [Outils : rappels, rôles à la réaction, aide](#outils--rappels-rôles-à-la-réaction-aide)
11. [Modération](#modération)
12. [Maintenance : sauvegardes, import, permissions](#maintenance--sauvegardes-import-permissions)

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
| `/missions` | Missions du jour et de la semaine |
| `/boutique` | Boutique permanente (rôles et cosmétiques) |
| `/profil [membre]` | Carte de profil, personnalisation, inventaire, collections |
| `/collections [membre]` | Tableau des collections de cosmétiques |
| `/donner` | Donne des pièces à un membre |
| `/rappel` | Programme un rappel personnel |
| `/avent` | Calendrier de l’Avent personnel (quand la campagne est activée) |

## Administration

| Commande | Permission | Description |
|---|---|---|
| `/progression-admin` | Gérer le serveur | XP, multiplicateurs, rôles de niveau, XP vocale, bonus d’XP, modifier ou réinitialiser un membre |
| `/quotidien-admin` | Gérer le serveur | Récompense quotidienne, bonus de série, réinitialiser un membre |
| `/missions-admin` | Gérer le serveur | Missions en JSON |
| `/boutique-admin` | Gérer le serveur | Articles de la boutique permanente |
| `/profil-admin` | Gérer le serveur | Créer, distribuer et supprimer des cosmétiques |
| `/avent-admin` | Administrateur | Tout le calendrier de l’Avent |
| `/drop` | Gérer le serveur | Fait apparaître un drop d’XP ou de pièces |
| `/giveaway lancer` / `terminer` / `retirer` | Gérer le serveur | Giveaways |
| `/reaction-role`, `/reaction-role-retirer`, `/reaction-role-liste` | Gérer les rôles | Rôles à la réaction |
| `/import_draftbot` | Administrateur | Import d’une progression DraftBot |
| `/warn`, `/mute`, `/unmute`, `/amende`, `/pardon`, `/casier`, `/note` | Exclure temporairement | Sanctions, annulations, casier (voir [Modération](#modération)) |
| `/kick` | Expulser | Expulsion |
| `/ban`, `/unban` | Bannir | Bannissement définitif ou temporaire |
| `/clear` | Gérer les messages | Suppression de messages |
| `/lock`, `/unlock` | Gérer les salons | Verrouillage d’un salon |
| `/moderation-admin` | Gérer le serveur | Journal, contestations, échelle de sanctions, AutoMod |

Les commandes d’administration n’apparaissent pas aux membres qui n’ont pas la permission. Dans `/aide`, les administrateurs voient en plus la liste de ces commandes.

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

## `/quotidien-admin`

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

- Le menu indique pour chaque article : acheté, niveau requis, solde insuffisant ou disponible.
- Au-delà de 25 articles, des boutons **◀ Page 1/3 ▶** apparaissent (250 articles au maximum).
- Un rôle acheté puis retiré peut être récupéré gratuitement avec **Restaurer le rôle**.
- Un cosmétique acheté arrive dans l’inventaire de `/profil`.

## `/boutique-admin`

- **Ajouter un rôle** : rôle, prix, niveau minimum, nom et description.
- **Ajouter un cosmétique** : sélectionner un cosmétique déjà créé dans `/profil-admin`, puis son prix et son niveau minimum.
- **Liste** : articles actifs et leurs identifiants.
- **Supprimer** : retire un article. Les rôles et cosmétiques déjà achetés sont conservés.

Supprimer un article de la boutique est différent de supprimer un cosmétique dans `/profil-admin`.

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

- **Créer un cosmétique** : identifiant, type, nom affiché, chemin de l’image (relatif à `assets/profile/`, vide pour un titre) et valeur facultative (texte d’un titre, nom d’un effet).
- **Distribuer** : donner un cosmétique à un membre. Au-delà de 25 cosmétiques, le choix se répartit sur plusieurs menus.
- **Supprimer un cosmétique** : retire définitivement le cosmétique du catalogue. Retire-le d’abord des boutiques.

### Identifiants : la convention à garder

Écris les identifiants sous la forme **`type-thème-année`** : `background-volcan-2026`, `frame-volcan-2026`, `badge-volcan-2026`, `effect-volcan-2026`. C’est ce qui forme les collections. L’identifiant ne doit plus changer après la création.

### Parcours complet d’un cosmétique

1. Déposer l’image dans `assets/profile/…` (sauf pour un titre), puis pousser sur GitHub.
2. `/profil-admin` → **Créer un cosmétique**.
3. Le tester avec **Distribuer** sur ton propre compte.
4. Le mettre en vente : `/boutique-admin` → **Ajouter un cosmétique**, ou dans la boutique de l’Avent, ou comme récompense de case, de mission ou de giveaway.

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
- La **boutique de l’Avent** vend des rôles et des cosmétiques contre des points, avec éventuellement un nombre minimum de cases ouvertes. Elle a des pages au-delà de 25 articles. Un rôle acheté puis retiré peut être restauré gratuitement.
- Articles : `/avent-admin` → **Ajouter un rôle à la boutique**, **Ajouter un cosmétique à la boutique**, **Supprimer un article de la boutique**.

## Annonces quotidiennes

Chaque jour, moins d’une minute après l’heure d’ouverture, le bot publie dans le canal choisi « 🎄 Jour N — Calendrier de l’Avent », avec les boutons du calendrier et, en option, la mention d’un rôle. Le 24, le texte change pour la dernière case.

Conditions : campagne activée, annonces activées (**Activer les annonces**, avec choix du rôle à mentionner) et canal choisi (**Modifier le canal**). Une seule annonce par jour ; si le bot était éteint à l’heure d’ouverture, elle part à son retour. Le rôle mentionné doit être mentionnable.

**Publier le panneau public** poste un panneau fixe avec les mêmes boutons, par exemple à épingler.

## `/avent-admin` : toutes les actions

- **Campagne** : Configuration, Initialiser une campagne, Activer ou désactiver, Modifier le canal, Modifier le fuseau, Modifier l’heure d’ouverture.
- **Rattrapage** : Activer ou désactiver le rattrapage, Limiter le rattrapage (jours).
- **Annonces** : Activer les annonces, Désactiver les annonces, Publier le panneau public.
- **Récompenses** : Liste des récompenses, Ajouter ou modifier une récompense, Supprimer une récompense, Aperçu du calendrier.
- **Membres** : Consulter un membre, Réinitialiser un membre, Réinitialiser TOUT LE MONDE.
- **Boutique de l’Avent** : ajouter un rôle, ajouter un cosmétique, supprimer un article.

## Réinitialisations

- **Réinitialiser un membre** : efface ses cases ouvertes et ses achats dans la boutique de l’Avent, après confirmation.
- **Réinitialiser TOUT LE MONDE** : efface les cases et les achats de **tous** les membres pour la campagne. Deux verrous : un avertissement avec le nombre de membres, cases et achats concernés (60 secondes pour confirmer), puis un formulaire où il faut taper **RÉINITIALISER**. Un mot incorrect n’efface rien.
- Dans les deux cas, les récompenses, la boutique et la configuration restent intactes, et les rôles ou cosmétiques déjà distribués ne sont pas retirés.

## Date de test

La variable d’environnement `ADVENT_TEST_DATE` (par exemple `2026-12-05`) fait croire au bot qu’on est à cette date, pour tester en local. Elle ne doit **jamais** être définie sur Render, sinon le calendrier resterait bloqué sur ce jour.

---

# Outils : rappels, rôles à la réaction, aide

## `/rappel`

```text
/rappel raison:Lancer la partie temps:1h30 destination:Dans ce salon
```

- Durées acceptées : `10s`, `10m`, `5mn`, `2h`, `1h30`, `1j12h`, `3sem`, ou un nombre seul en minutes (`45`). De 10 secondes à 90 jours.
- Destination : dans le salon (y compris le chat d’un salon vocal) ou en message privé. Si l’une n’est pas possible, le rappel part par l’autre.
- **Relancer le rappel** reprogramme le même rappel avec la même durée.

## Rôles à la réaction

| Commande | Rôle |
|---|---|
| `/reaction-role` | Lie un émoji, sur un message, à un rôle. Le bot ajoute lui-même la réaction. |
| `/reaction-role-retirer` | Supprime une association. |
| `/reaction-role-liste` | Liste les associations du serveur. |

Réagir donne le rôle, retirer sa réaction l’enlève. Les émojis personnalisés restent reconnus s’ils sont renommés ou animés.

## `/aide`

Liste les commandes membres, classées par thème. La liste se construit automatiquement : une nouvelle commande y apparaît sans rien modifier. Les administrateurs voient aussi les commandes d’administration.

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
