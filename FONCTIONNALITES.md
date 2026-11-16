# Fonctionnalités de Clan Renard Bot

Ce document présente les fonctionnalités disponibles dans Clan Renard Bot.

Il décrit :

- les commandes accessibles aux membres ;
- les commandes administratives ;
- le fonctionnement des différents systèmes ;
- les interactions entre la progression, les profils et les boutiques.

Pour l’installation et le déploiement, consulter :

```text
README.md
```

---

# Liste générale des systèmes

Clan Renard Bot possède actuellement les systèmes suivants :

- calendrier de l’Avent individuel ;
- récompenses quotidiennes ;
- rattrapage des cases manquées ;
- points saisonniers ;
- boutique saisonnière ;
- profils graphiques personnalisables ;
- cosmétiques de profil ;
- inventaire personnel ;
- progression par XP ;
- niveaux ;
- XP gagnée par messages ;
- XP gagnée en vocal ;
- argent permanent ;
- rôles de niveau ;
- multiplicateurs d’XP ;
- classements ;
- boutique permanente ;
- vente de rôles Discord ;
- vente de cosmétiques ;
- importation depuis DraftBot ;
- panneaux administratifs interactifs ;
- récompense quotidienne avec série et rappel ;
- missions quotidiennes et hebdomadaires ;
- dons de pièces entre membres ;
- classements de la semaine et du mois ;
- statistiques personnelles ;
- rappels personnels ;
- rôles à la réaction ;
- commande d’aide ;
- sauvegarde de la base.

---

# Commandes principales

| Commande | Accès | Description |
|---|---:|---|
| `/avent` | Membres | Ouvre le calendrier de l’Avent personnel |
| `/avent-admin` | Administration | Ouvre le panneau d’administration de l’Avent |
| `/profil` | Membres | Affiche une carte de profil |
| `/profil-admin` | Administration | Gère les cosmétiques et les inventaires |
| `/progression` | Membres | Affiche le niveau, l’XP et l’argent |
| `/progression-admin` | Administration | Configure le système de progression |
| `/boutique` | Membres | Ouvre la boutique permanente |
| `/boutique-admin` | Administration | Gère les articles de la boutique |
| `/import_draftbot` | Administration | Importe une progression provenant de DraftBot |
| `/quotidien` | Membres | Récupère la récompense quotidienne |
| `/quotidien-admin` | Administration | Configure la récompense quotidienne |
| `/missions` | Membres | Affiche et réclame les missions |
| `/missions-admin` | Administration | Configure les missions |
| `/donner` | Membres | Donne des pièces à un membre |
| `/classement` | Membres | Classements XP, argent, série, semaine et mois |
| `/stats` | Membres | Statistiques d’un membre |
| `/rappel` | Membres | Programme un rappel |
| `/aide` | Membres | Liste les commandes |
| `/bilan` | Membres | Bilan de l’année (du 31 décembre au 31 janvier) |
| `/drop` | Administration | Fait apparaître un drop d’XP ou de pièces |
| `/giveaway lancer` | Administration | Lance un giveaway |
| `/giveaway terminer` | Administration | Termine un giveaway et tire les gagnants |
| `/giveaway retirer` | Administration | Tire de nouveaux gagnants |
| `/reaction-role` | Administration | Lie une réaction à un rôle |
| `/reaction-role-retirer` | Administration | Supprime une réaction-rôle |
| `/reaction-role-liste` | Administration | Liste les réactions-rôles |

Les commandes administratives sont généralement limitées aux membres possédant les permissions nécessaires, notamment **Gérer le serveur** ou une permission équivalente.

---

# Calendrier de l’Avent

## Commande `/avent`

La commande :

```text
/avent
```

ouvre le calendrier personnel du membre.

Chaque membre possède son propre état de progression :

- les cases déjà ouvertes ;
- les cases disponibles ;
- les cases verrouillées ;
- les cases manquées ;
- les récompenses reçues ;
- les points saisonniers accumulés.

Le calendrier est généré graphiquement avec Pillow.

Il peut contenir :

- le pseudo du membre ;
- son avatar ;
- les 24 cases ;
- l’état visuel de chaque case ;
- une apparence spéciale pour le 24 décembre ;
- les informations de la campagne.

## Boutons du calendrier

Selon la configuration de la campagne, le panneau peut proposer des actions telles que :

- ouvrir la case du jour ;
- rattraper une case ;
- actualiser le calendrier ;
- consulter ses récompenses ;
- consulter son historique ;
- consulter le classement ;
- ouvrir la boutique saisonnière ;
- consulter l’aide.

## Ouverture quotidienne

Une case peut être ouverte lorsque :

- la date correspond à la case ;
- l’heure d’ouverture configurée est atteinte ;
- le membre n’a pas déjà ouvert cette case ;
- la campagne est active.

PostgreSQL protège l’ouverture afin d’éviter qu’une même case soit récupérée plusieurs fois à cause de doubles clics ou de requêtes simultanées.

## Rattrapage

Si le rattrapage est activé, un membre peut ouvrir certaines cases précédentes qu’il a manquées.

Le membre sélectionne alors la case concernée dans un menu.

Si le rattrapage est désactivé, les anciennes cases non ouvertes restent manquées.

La limite se règle dans `/avent-admin` avec **Limiter le rattrapage (jours)**, qui ouvre un formulaire :

- un nombre de 1 à 23 : nombre maximal de jours en arrière (avec 3, le 10 décembre, les cases 7, 8 et 9 peuvent encore être ouvertes) ;
- `0` : rattrapage désactivé ;
- vide : rattrapage sans limite.

## Types de récompenses

Dans `/avent-admin`, **Ajouter ou modifier une récompense** propose de choisir le type, puis ouvre le formulaire correspondant. Une case peut donner :

| Type | Ce que reçoit le membre |
|---|---|
| Message | Un message surprise |
| Points de l’Avent | Des points pour la boutique de l’Avent |
| Pièces | Des pièces permanentes, utilisables dans `/boutique` |
| XP | De l’XP permanente (peut faire monter de niveau et donner un rôle de niveau) |
| Cosmétique de profil | Un cosmétique ajouté à l’inventaire de `/profil`, désigné par son identifiant |
| Rôle Discord | Un rôle attribué à l’ouverture |
| Aléatoire | Un tirage pondéré entre plusieurs récompenses (format JSON) |

Les pièces, l’XP et les cosmétiques sont versés au moment de l’ouverture. Si le versement échoue, l’ouverture reste enregistrée, le membre est prévenu et la récompense apparaît comme « non créditée » dans son historique et dans « Consulter un membre ».

Dans une récompense aléatoire, les types `coins` (`{"coins": 200}`), `xp` (`{"xp": 500}`) et `cosmetic` (`{"cosmetic_id": 12}`) sont aussi utilisables.

## Points saisonniers

Les points du calendrier sont liés à la campagne saisonnière.

Ils sont différents de l’argent permanent du système de progression.

Ils peuvent être utilisés dans la boutique saisonnière de l’Avent.

## Classement saisonnier

Le classement peut afficher les membres selon leurs performances pendant la campagne, par exemple :

- points obtenus ;
- nombre de cases ouvertes ;
- progression dans le calendrier.

## Annonces automatiques

Le bot peut publier automatiquement une annonce quotidienne dans un salon configuré.

Conditions : la campagne est activée, les annonces sont activées et un canal est choisi dans `/avent-admin`. L'annonce part moins d'une minute après l'heure d'ouverture, une seule fois par jour, avec les boutons du calendrier et la mention du rôle choisi (facultatif).

L’annonce peut prévenir les membres qu’une nouvelle case est disponible.

## Fuseau horaire

La campagne utilise un fuseau horaire configurable.

Cela permet d’ouvrir les cases selon l’heure locale souhaitée, par exemple :

```text
Europe/Paris
```

## Date de test

Un système de date de test peut être utilisé en développement pour simuler une date de décembre sans attendre le jour réel.

Cette option ne doit pas être utilisée involontairement en production.

---

# Administration du calendrier

## Commande `/avent-admin`

La commande :

```text
/avent-admin
```

ouvre le panneau administratif du calendrier.

Ce panneau centralise les anciennes commandes administratives dans une seule interface.

Selon la version du module, il permet notamment de :

- initialiser une campagne ;
- modifier son année ;
- définir le fuseau horaire ;
- définir l’heure quotidienne ;
- choisir le salon du calendrier ;
- activer ou désactiver le rattrapage ;
- activer ou désactiver les annonces ;
- créer les récompenses ;
- modifier les récompenses ;
- supprimer les récompenses ;
- prévisualiser le calendrier ;
- publier le panneau public ;
- gérer les membres ;
- gérer la boutique saisonnière ;
- consulter les informations de la campagne.

Les anciennes commandes administratives peuvent être conservées dans le code sans être affichées publiquement si elles ont été remplacées par le panneau.

---

# Boutique saisonnière de l’Avent

La boutique saisonnière utilise les points gagnés pendant la campagne.

Elle peut proposer :

- des rôles Discord ;
- des cosmétiques de profil ;
- des récompenses limitées à la campagne.

Les articles saisonniers peuvent avoir :

- un prix ;
- une quantité disponible ;
- une limite d’achat ;
- une période de disponibilité ;
- des conditions particulières.

Les achats sont enregistrés dans PostgreSQL pour éviter les doubles achats.

Les cosmétiques proposés doivent exister dans le système de profils avant d’être ajoutés à une boutique.

---

# Profils des membres

## Commande `/profil`

La commande :

```text
/profil
```

affiche le profil du membre qui utilise la commande.

Il est également possible de consulter le profil d’un autre membre avec l’option prévue :

```text
/profil membre:@Membre
```

La carte peut afficher notamment :

- l’avatar ;
- le pseudo ;
- la biographie ;
- la couleur personnelle ;
- le titre équipé ;
- le badge équipé ;
- l’arrière-plan équipé ;
- le cadre équipé ;
- l’effet équipé ;
- certaines informations communautaires ;
- certaines informations de progression.

Le profil est généré dynamiquement avec Pillow.

## Personnalisation

Un membre peut personnaliser son profil grâce aux options disponibles dans l’interface.

Selon la configuration, il peut notamment modifier :

- sa biographie ;
- sa couleur ;
- ses cosmétiques équipés.

## Inventaire

Les cosmétiques possédés sont conservés dans un inventaire permanent.

Un membre peut posséder plusieurs cosmétiques, mais ne peut généralement équiper qu’un seul élément de chaque type :

- un titre ;
- un badge ;
- un arrière-plan ;
- un cadre ;
- un effet.

---

# Types de cosmétiques

Le système de profils accepte les types suivants.

| Type | Valeur à utiliser | Image nécessaire |
|---|---|---:|
| Titre | `title` | Non |
| Badge | `badge` | Oui |
| Arrière-plan | `background` | Oui |
| Cadre | `frame` | Oui |
| Effet | `effect` | Selon l’effet |

## Titre

Un titre est une ligne de texte affichée sur le profil.

Exemple :

```text
Renard légendaire
```

Un titre ne nécessite pas d’image.

Il n’est donc pas nécessaire de créer un dossier :

```text
assets/profile/titles/
```

Exemple de création :

```text
Identifiant : titre-renard-legendaire
Type : title
Nom affiché : Renard légendaire
Chemin de l’image :
Valeur facultative : Renard légendaire
```

Le chemin de l’image doit rester vide.

La valeur facultative contient le texte réellement affiché.

## Badge

Un badge est une petite image affichée sur le profil.

Exemple :

```text
Identifiant : badge-flocon
Type : badge
Nom affiché : Flocon de Noël
Chemin de l’image : badges/flocon.png
Valeur facultative :
```

Fichier correspondant :

```text
assets/profile/badges/flocon.png
```

## Arrière-plan

Un arrière-plan remplace ou complète le fond de la carte.

Exemple :

```text
Identifiant : fond-noel
Type : background
Nom affiché : Nuit de Noël
Chemin de l’image : backgrounds/noel.png
Valeur facultative :
```

Fichier correspondant :

```text
assets/profile/backgrounds/noel.png
```

## Cadre

Un cadre est affiché autour de la carte ou de certaines parties du profil.

Exemple :

```text
Identifiant : cadre-givre
Type : frame
Nom affiché : Cadre givré
Chemin de l’image : frames/givre.png
Valeur facultative :
```

Fichier correspondant :

```text
assets/profile/frames/givre.png
```

## Effet

Un effet ajoute une apparence spéciale au profil.

Exemple :

```text
Identifiant : effet-neige
Type : effect
Nom affiché : Neige
Chemin de l’image : effects/neige.png
Valeur facultative : snow
```

Selon l’implémentation de l’effet, le chemin de l’image ou la valeur facultative peut être utilisé pour déterminer le rendu.

---

# Administration des profils

## Commande `/profil-admin`

La commande :

```text
/profil-admin
```

ouvre le panneau d’administration des profils.

Le panneau permet notamment de :

- créer un cosmétique ;
- distribuer un cosmétique ;
- supprimer définitivement un cosmétique.

## Créer un cosmétique

Le formulaire demande :

### Identifiant

Identifiant technique unique du cosmétique.

Exemples :

```text
titre-renard-legendaire
badge-noel-2026
fond-hiver
cadre-givre
effet-neige
```

L’identifiant ne doit normalement pas changer après la création.

### Type

Valeurs disponibles :

```text
title
badge
background
frame
effect
```

### Nom affiché

Nom lisible présenté aux membres et dans les interfaces administratives.

### Chemin de l’image

Chemin relatif à :

```text
assets/profile/
```

Exemple :

```text
badges/flocon.png
```

Pour un titre, ce champ doit rester vide.

### Valeur facultative

Ce champ dépend du type de cosmétique.

Il peut contenir :

- le texte d’un titre ;
- l’identifiant d’un effet procédural ;
- une valeur utilisée par le moteur de rendu ;
- aucune valeur pour les cosmétiques purement graphiques.

## Distribuer un cosmétique

Cette action ajoute directement un cosmétique existant à l’inventaire d’un membre.

Elle est utile pour :

- une récompense événementielle ;
- un concours ;
- une compensation ;
- un cadeau administratif ;
- un test.

## Supprimer un cosmétique

La suppression permanente retire le cosmétique du catalogue.

Selon les relations de la base de données, cette action peut également affecter :

- les inventaires ;
- les équipements ;
- les articles des boutiques qui utilisent ce cosmétique.

Il est conseillé de retirer d’abord le cosmétique des boutiques avant de le supprimer définitivement.

---

# Progression permanente

## Commande `/progression`

La commande :

```text
/progression
```

affiche la progression du membre.

Il est possible de consulter un autre membre avec :

```text
/progression membre:@Membre
```

La carte de progression peut afficher :

- le pseudo ;
- l’avatar ;
- le niveau ;
- l’XP totale ;
- la progression vers le niveau suivant ;
- le rang sur le serveur ;
- le portefeuille ;
- l’argent total gagné.

## Courbe d’XP

La progression utilise une courbe où chaque niveau demande progressivement plus d’XP.

Le niveau est calculé à partir de l’XP totale.

La progression affichée sur la carte correspond à :

- l’XP gagnée depuis le début du niveau actuel ;
- l’XP nécessaire pour atteindre le niveau suivant.

## Classement XP

Le bouton **Classement XP** affiche les meilleurs membres du serveur selon :

1. leur XP totale ;
2. leur argent en cas d’égalité ;
3. leur identifiant pour stabiliser le classement.

## Classement argent

Le bouton **Classement argent** affiche les meilleurs portefeuilles du serveur.

---

# Gain d’XP par message

Lorsqu’un membre envoie un message valide, il peut recevoir :

- une quantité aléatoire d’XP ;
- une quantité aléatoire d’argent.

Un délai configurable empêche de gagner une récompense à chaque message envoyé rapidement.

Exemple :

```text
Cooldown : 60 secondes
XP : entre 15 et 25
Argent : entre 2 et 4 pièces
```

Les bots et les webhooks ne reçoivent pas de progression.

Lorsqu’un membre monte de niveau, le bot peut envoyer une notification.

---

# Gain d’XP en vocal

Le système peut attribuer automatiquement de l’XP chaque minute passée dans un salon vocal.

La quantité d’XP est configurable depuis `/progression-admin`.

## Conditions d’activité

Un membre est considéré comme actif s’il :

- n’est pas un bot ;
- se trouve dans un salon vocal ou une scène ;
- n’est pas dans le salon AFK du serveur ;
- n’est pas rendu muet ;
- ne s’est pas rendu muet lui-même ;
- n’est pas rendu sourd ;
- ne s’est pas rendu sourd lui-même.

Au moins deux membres humains actifs doivent être présents dans le même salon.

## Récompense vocale

Le vocal attribue :

- de l’XP ;
- aucun argent.

Les multiplicateurs d’XP liés aux rôles s’appliquent également au vocal.

Une valeur de :

```text
0 XP par minute
```

désactive le gain d’XP vocal.

Les minuteurs sont enregistrés en base de données pour limiter les récompenses incorrectes après un changement d’état vocal.

---

# Multiplicateurs d’XP

Un rôle Discord peut donner un multiplicateur d’XP.

Exemples :

```text
VIP → x1.5 XP
Booster → x2 XP
Événement → x3 XP
```

Le multiplicateur s’applique :

- aux récompenses de messages ;
- aux récompenses vocales.

Si un membre possède plusieurs rôles avec multiplicateur, seul le multiplicateur le plus élevé est utilisé.

Les valeurs acceptées sont comprises entre :

```text
1 et 10
```

Entrer `0` dans le formulaire supprime la règle du rôle.

---

# Rôles de niveau

Des rôles Discord peuvent être associés à des niveaux.

Exemple :

```text
Niveau 10 → Jeune renard
Niveau 30 → Renard confirmé
Niveau 50 → Renard légendaire
```

Le bot vérifie automatiquement le niveau du membre après un gain ou une modification d’XP.

## Un seul rôle de niveau à la fois

Le système conserve uniquement le rôle correspondant au palier le plus élevé atteint.

Exemple :

- le membre atteint le niveau 30 ;
- il reçoit le rôle du niveau 30 ;
- il atteint ensuite le niveau 50 ;
- le rôle du niveau 30 est retiré ;
- le rôle du niveau 50 est ajouté.

Le membre ne conserve donc pas tous les anciens rôles de niveau.

Si son XP est réduite administrativement, le système peut également remplacer son rôle par le palier correspondant à son nouveau niveau.

## Conditions Discord

Pour gérer les rôles :

- le bot doit avoir la permission **Gérer les rôles** ;
- le rôle du bot doit être placé au-dessus des rôles de niveau ;
- le rôle ne doit pas être géré par une intégration ;
- `@everyone` ne peut pas être utilisé.

---

# Administration de la progression

## Commande `/progression-admin`

La commande :

```text
/progression-admin
```

ouvre le panneau d’administration de la progression.

## Configuration générale

Le bouton **Configuration** permet de modifier :

- le délai entre deux récompenses de messages ;
- l’XP minimale par message ;
- l’XP maximale par message ;
- l’argent minimal par message ;
- l’argent maximal par message.

## Activation du système

Le bouton **Activer/désactiver** contrôle le gain automatique :

- d’XP par messages ;
- d’argent par messages ;
- d’XP vocale.

## Notifications de niveau

Le bouton **Notifications de niveau** active ou désactive les annonces de montée de niveau.

## Modifier un membre

L’administrateur sélectionne d’abord un membre, puis peut :

- ajouter de l’XP ;
- retirer de l’XP ;
- ajouter de l’argent ;
- retirer de l’argent ;
- indiquer une raison.

Exemples :

```text
XP : 500
Argent : 100
```

ou :

```text
XP : -200
Argent : -50
```

L’XP et le portefeuille ne peuvent pas devenir négatifs.

## Réinitialiser un membre

La réinitialisation supprime :

- son XP ;
- son niveau ;
- son argent ;
- ses statistiques de messages ;
- ses informations de récompenses vocales ;
- ses transactions de progression.

Une confirmation est demandée avant l’exécution.

## Configurer un multiplicateur

Le bouton **Multiplicateur XP** permet de :

1. sélectionner un rôle ;
2. entrer un multiplicateur entre 1 et 10 ;
3. enregistrer la règle.

Entrer `0` supprime le multiplicateur.

## Configurer un rôle de niveau

Le bouton **Rôle de niveau** permet de :

1. sélectionner un rôle ;
2. indiquer le niveau nécessaire ;
3. enregistrer la récompense.

Entrer `0` supprime la règle.

## Voir les règles

Le bouton **Voir les règles** affiche :

- les multiplicateurs configurés ;
- les rôles de niveau ;
- la valeur actuelle de l’XP vocale.

## Configurer l’XP vocale

Le bouton **XP vocal** permet de choisir la quantité d’XP gagnée par minute.

Entrer `0` désactive l’XP vocale.

---

# Économie permanente

L’économie permanente utilise le portefeuille du système de progression.

L’argent peut être gagné notamment :

- en envoyant des messages ;
- grâce à une modification administrative ;
- grâce à de futures récompenses permanentes.

Deux valeurs peuvent être conservées :

- **portefeuille** : argent actuellement disponible ;
- **argent total gagné** : total historique des pièces reçues.

Dépenser de l’argent réduit le portefeuille mais pas nécessairement le total historique gagné.

---

# Boutique permanente

## Commande `/boutique`

La commande :

```text
/boutique
```

ouvre la boutique permanente du serveur.

La boutique utilise l’argent du système de progression.

Elle peut vendre :

- des rôles Discord ;
- des cosmétiques de profil.

Les articles peuvent imposer :

- un prix ;
- un niveau minimum ;
- une disponibilité particulière.

## Achat d’un rôle

Lorsqu’un membre achète un rôle :

1. le bot vérifie que l’article existe ;
2. le bot vérifie le niveau minimum ;
3. le bot vérifie le portefeuille ;
4. le prix est retiré ;
5. le rôle est distribué ;
6. l’achat est enregistré.

Si le membre a déjà acheté le rôle mais que celui-ci lui a été retiré manuellement, le bot peut le restaurer sans lui faire payer une deuxième fois.

## Achat d’un cosmétique

Lorsqu’un membre achète un cosmétique :

1. le bot vérifie que le cosmétique existe ;
2. le bot vérifie le niveau minimum ;
3. le bot vérifie le portefeuille ;
4. le prix est retiré ;
5. le cosmétique est ajouté à l’inventaire ;
6. l’achat est enregistré.

Le cosmétique devient ensuite disponible dans `/profil`.

---

# Administration de la boutique permanente

## Commande `/boutique-admin`

La commande :

```text
/boutique-admin
```

ouvre le panneau administratif de la boutique permanente.

Le panneau propose notamment :

- **Ajouter un rôle** ;
- **Ajouter un cosmétique** ;
- **Liste** ;
- **Supprimer**.

## Ajouter un rôle

Cette action crée un article vendant un rôle Discord.

L’administrateur choisit notamment :

- le rôle ;
- le prix ;
- le niveau minimum éventuel ;
- les informations d’affichage.

## Ajouter un cosmétique

La boutique ne crée pas elle-même le cosmétique.

Le cosmétique doit d’abord être créé avec :

```text
/profil-admin
```

Le fonctionnement correct est donc :

1. ouvrir `/profil-admin` ;
2. créer le titre, le badge, l’arrière-plan, le cadre ou l’effet ;
3. ouvrir `/boutique-admin` ;
4. cliquer sur **Ajouter un cosmétique** ;
5. sélectionner le cosmétique existant ;
6. définir son prix ;
7. définir son niveau minimum éventuel ;
8. publier l’article.

La boutique référence le cosmétique déjà enregistré dans le système de profils.

Il ne faut pas remettre le chemin de l’image lors de sa mise en vente.

## Liste des articles

Le bouton **Liste** affiche les articles actuellement disponibles et leurs identifiants.

## Supprimer un article

Le bouton **Supprimer** retire l’article de la boutique.

La suppression de l’article ne doit pas retirer les récompenses déjà achetées :

- les rôles achetés restent considérés comme achetés ;
- les cosmétiques déjà obtenus restent dans les inventaires.

Supprimer un article de la boutique est différent de supprimer définitivement un cosmétique avec `/profil-admin`.

---

# Différence entre les deux boutiques

## Boutique permanente

Commande :

```text
/boutique
```

Monnaie utilisée :

```text
Argent permanent de la progression
```

Contenu :

- rôles permanents ;
- cosmétiques permanents.

## Boutique saisonnière

Accessible depuis le calendrier de l’Avent.

Monnaie utilisée :

```text
Points de la campagne de l’Avent
```

Contenu :

- rôles saisonniers ;
- cosmétiques saisonniers ;
- récompenses liées à la campagne.

Les deux monnaies sont indépendantes.

---

# Importation depuis DraftBot

## Commande `/import_draftbot`

La commande :

```text
/import_draftbot
```

permet d’importer une progression précédemment gérée par DraftBot.

L’import utilise un fichier HTML exporté depuis DraftBot.

Selon les options disponibles, l’administrateur peut :

- envoyer le fichier ;
- afficher une prévisualisation ;
- vérifier les membres reconnus ;
- confirmer l’import ;
- remplacer ou conserver certaines données existantes ;
- attribuer les rôles correspondant aux niveaux importés.

## Correspondance des membres

Le système doit utiliser les identifiants Discord lorsque ceux-ci sont présents dans l’export.

Les pseudonymes seuls ne sont pas suffisamment fiables, car ils peuvent :

- être modifiés ;
- contenir des caractères différents ;
- être partagés par plusieurs membres.

Les membres absents du serveur peuvent être ignorés selon le fonctionnement de l’import.

## Données importées

L’import peut restaurer notamment :

- le niveau ;
- l’XP ;
- la progression dans le niveau actuel ;
- les rôles de niveau correspondants.

L’XP totale est recalculée pour être compatible avec la courbe de progression de Clan Renard Bot.

## Après la migration

Si l’extension d’import ne sert plus après la migration, elle peut être désactivée ou retirée afin de ne pas conserver inutilement une commande administrative sensible.

Il est recommandé de conserver une sauvegarde de la base avant tout import important.

---

# Récompense quotidienne

## Commande `/quotidien`

Chaque membre peut récupérer une récompense **une fois par jour**. Le compteur repart à **minuit, heure de Paris**.

La récompense contient de l’XP et des pièces, configurées avec `/quotidien-admin`.

## Série

- Récupérer la récompense deux jours de suite fait monter la série.
- Sauter un jour remet la série à 1.
- La meilleure série est conservée et sert au classement **Meilleure série quotidienne**.

Des règles de bonus (au format JSON, voir le bouton **Exemple JSON** de `/quotidien-admin`) peuvent multiplier ou augmenter la récompense à certains jours de série, par exemple tous les 7 jours ou au 30e jour.

## Rappel en message privé

Sous la réponse de `/quotidien` :

- le bouton **Activer / désactiver rappel** active ou coupe le rappel ;
- le menu **Choisir l’heure du rappel** fixe l’heure du message privé (heure de Paris) et active le rappel.

L’heure par défaut est **09:00**. Le rappel est envoyé une seule fois, le jour où la récompense redevient disponible. Il n’arrive pas si le membre a fermé ses messages privés.

---

# Missions

## Commande `/missions`

Affiche les missions du jour et de la semaine, avec la progression du membre. Une mission terminée se réclame avec le bouton du panneau.

- Missions quotidiennes : remises à zéro à minuit (heure de Paris).
- Missions hebdomadaires : remises à zéro le lundi à minuit.

La progression compte depuis le début réel de la période, même si le membre n’a pas encore ouvert `/missions`.

## Objectifs possibles

| Valeur | Objectif |
|---|---|
| `messages` | Messages récompensés en XP (un seul par délai entre deux récompenses) |
| `voice_minutes` | Minutes passées en vocal avec au moins un autre membre |
| `xp` | XP gagnée |
| `coins` | Pièces gagnées (les dons reçus avec `/donner` ne comptent pas) |
| `daily_claims` | Récompenses quotidiennes récupérées |
| `streak` | Série quotidienne en cours |

## Administration

`/missions-admin` permet d’activer le système et de configurer jusqu’à 25 missions au format JSON (bouton **Exemple**). Chaque mission peut donner de l’XP, des pièces et un cosmétique de profil.

---

# Dons de pièces

## Commande `/donner`

```text
/donner membre:@Membre montant:100 raison:Merci !
```

- Un membre peut donner au total **500 pièces par jour** (heure de Paris).
- On ne peut pas se donner des pièces, ni en donner à un bot.
- Le don est annoncé dans le salon.
- Les pièces reçues s’ajoutent au portefeuille mais ne comptent pas comme de l’argent « gagné » : elles ne font pas avancer les missions `coins`.

La limite quotidienne se règle dans le code (`DAILY_GIFT_LIMIT` dans `bot/extensions/donner.py`).

---

# Classements

## Commande `/classement`

| Type | Contenu |
|---|---|
| XP | XP totale |
| Argent | Portefeuille actuel |
| Meilleure série quotidienne | Plus longue série de `/quotidien` |
| XP de la semaine | XP gagnée depuis lundi minuit (heure de Paris) |
| XP du mois | XP gagnée depuis le 1er du mois |

Les classements de la semaine et du mois donnent leur chance aux nouveaux membres face aux anciens. Ils se mettent à jour environ une fois par minute.

Les membres qui ont quitté le serveur sont masqués de tous les classements et ne comptent plus dans les rangs. Leurs données sont conservées : ils retrouvent leur place s’ils reviennent.

## Commande `/stats`

Affiche les statistiques d’un membre pour **aujourd’hui** ou les **7 derniers jours** : XP gagnée, pièces gagnées, meilleure série, messages récompensés, temps vocal récompensé, progression vers le niveau suivant et classements actuels.

---

# Rappels personnels

## Commande `/rappel`

```text
/rappel raison:Lancer la partie temps:1h30 destination:Dans ce salon
```

Formats de durée acceptés : `10s`, `10m`, `5mn`, `2h`, `1h30`, `1j12h`, `3sem`, ou un nombre seul en minutes (`45`).

- Durée minimale : 10 secondes. Durée maximale : 90 jours.
- Si le salon n’est plus accessible, le rappel part en message privé (et inversement).
- Le bouton **Relancer le rappel** reprogramme le même rappel avec la même durée.

---

# Rôles à la réaction

| Commande | Rôle |
|---|---|
| `/reaction-role` | Lie un émoji, sur un message, à un rôle. Le bot ajoute lui-même la réaction. |
| `/reaction-role-retirer` | Supprime une association. |
| `/reaction-role-liste` | Liste les associations du serveur. |

Ces commandes demandent la permission **Gérer les rôles**. Réagir donne le rôle, retirer sa réaction l’enlève.

Les émojis personnalisés restent reconnus s’ils sont renommés ou animés.

---

# Bonus d’XP temporaire

Dans `/progression-admin`, le bouton **Bonus d’XP** ouvre un formulaire :

- **Multiplicateur** : par exemple `2` pour doubler l’XP, de 1,1 à 5. `1` arrête le bonus en cours.
- **Début** et **Fin**, heure de Paris : par exemple `24/12 00:00` et `26/12 23:59`. Début vide = tout de suite. Sans heure, le début est à 00:00 et la fin à 23:59.
- **Nom** : affiché dans les annonces (« Bonus de Noël »).
- **Annonce** : `oui` publie un message au début et à la fin du bonus, dans le salon où le formulaire a été envoyé.

Le bonus s’applique à l’XP des messages et du vocal, pour tout le serveur. Il se multiplie avec les multiplicateurs de rôle : un membre VIP ×1,5 pendant un bonus ×2 gagne ×3. Un seul bonus peut être programmé à la fois ; en enregistrer un nouveau remplace l’ancien.

---

# Giveaways

```text
/giveaway lancer lot:Nitro duree:2j gagnants:1 pieces:500 role:@Gagnant niveau_minimum:5 salon:#annonces
```

Seuls `lot` et `duree` sont obligatoires.

- Les membres cliquent sur **Participer** ; un second clic les retire. Le message affiche le nombre de participants.
- Le bouton fonctionne même après un redémarrage du bot.
- À la fin, le bot tire au sort parmi les participants encore présents sur le serveur, annonce les gagnants et remet automatiquement les pièces et le rôle s’ils sont configurés. Le lot texte (par exemple un Nitro) est à remettre à la main.
- `niveau_minimum` réserve la participation aux membres de ce niveau ou plus.
- `/giveaway terminer numero:12` tire les gagnants tout de suite. `/giveaway retirer numero:12` tire de nouveaux gagnants (par exemple si un gagnant ne répond pas), en excluant les précédents. Le numéro est indiqué en bas du message du giveaway.

---

# Drops

```text
/drop xp:500 pieces:100 gagnants:3 duree:10m mystere:Non message:Le premier qui clique !
```

Un message avec un bouton **Récupérer** apparaît : les premiers membres à cliquer (`gagnants`, 1 par défaut) reçoivent l’XP et les pièces indiquées, une seule fois chacun. Le drop disparaît une fois toutes les places prises, ou au bout de `duree` (10 minutes par défaut, 1 jour maximum).

- **Pièges** : `xp` et `pieces` acceptent des nombres négatifs pour en retirer. L’XP et le portefeuille ne descendent jamais sous 0, et un rôle de niveau peut être retiré si le membre redescend de niveau.
- **Mystère** : `mystere:True` cache le contenu jusqu’au clic. Les montants sont révélés sur le message une fois le drop terminé.
- Les pièces gagnées comptent comme de l’argent gagné ; les pièces perdues n’annulent pas le total historique.

---

# Bilan de l’année

`/bilan` affiche une carte avec l’année du membre : XP gagnée et classement de l’année, messages, temps en vocal, pièces gagnées, jour le plus actif, récompenses quotidiennes, meilleure série et cases de l’Avent ouvertes.

- Les membres peuvent l’utiliser du **31 décembre au 31 janvier** (en janvier, il montre l’année écoulée). Avant, la commande annonce qu’il arrive bientôt.
- Les administrateurs peuvent le consulter à tout moment, en privé, pour le vérifier.
- `/bilan membre:@Membre` affiche le bilan d’un autre membre.
- Les chiffres viennent des statistiques quotidiennes : si elles ont commencé en cours d’année, la carte l’indique (« Statistiques enregistrées depuis le … »).

---

# Aide

`/aide` liste toutes les commandes membres, classées par thème. Les administrateurs voient aussi la liste des commandes d’administration.

La liste est construite automatiquement à partir des commandes chargées : une nouvelle commande y apparaît sans rien modifier.

---

# Sauvegarde de la base

Les données sont stockées sur Supabase. Pour en garder une copie sur ton PC :

1. Ajoute dans le fichier `.env` du bot la ligne `DATABASE_URL=...` (la même valeur que sur Render). Ce fichier n’est jamais envoyé sur GitHub.
2. Depuis le dossier du bot, lance :

```text
python scripts/sauvegarder_base.py
```

Un fichier `sauvegardes/clan-renard-AAAA-MM-JJ_HH-MM.zip` est créé. Il contient un fichier CSV par table (lisible dans Excel) et un fichier `informations.json` avec le nombre de lignes de chaque table.

Le dossier `sauvegardes/` est exclu de git : la base contient les identifiants Discord des membres et ne doit pas finir sur le dépôt public.

## Restaurer une sauvegarde

```text
python scripts/restaurer_base.py sauvegardes/clan-renard-AAAA-MM-JJ_HH-MM.zip
```

- Arrête le bot pendant la restauration.
- Les tables sont **vidées puis remplies** avec la sauvegarde : tout ce qui a changé depuis est perdu. Le script demande de taper `RESTAURER` pour confirmer.
- En cas d’erreur, rien n’est modifié.
- Sur une base neuve, démarre d’abord le bot une fois pour qu’il crée les tables.

---

# Images dynamiques

Le bot génère plusieurs images en mémoire :

- calendrier personnel ;
- profil personnel ;
- carte de progression.

Les images sont composées à partir :

- des données PostgreSQL ;
- de l’avatar Discord ;
- du pseudo ;
- des ressources présentes dans `assets/` ;
- des cosmétiques équipés ;
- de la progression du membre.

Les images ne sont pas nécessairement conservées sur le disque après leur envoi.

---

# Permissions et hiérarchie des rôles

Pour distribuer correctement des rôles, le bot doit respecter la hiérarchie Discord.

Le rôle du bot doit être situé au-dessus :

- des rôles de niveau ;
- des rôles vendus dans les boutiques ;
- des rôles distribués par le calendrier.

Le bot ne peut pas gérer :

- `@everyone` ;
- un rôle situé au-dessus de son propre rôle ;
- un rôle géré par Discord ;
- un rôle géré par une intégration.

---

# Données permanentes

Les données importantes sont enregistrées dans PostgreSQL.

Un redémarrage du bot ne supprime pas :

- les cases ouvertes ;
- les récompenses ;
- les points ;
- les achats ;
- les profils ;
- les inventaires ;
- les cosmétiques équipés ;
- l’XP ;
- les niveaux ;
- l’argent ;
- les articles de boutique ;
- les rôles de niveau configurés ;
- les multiplicateurs ;
- la configuration vocale.

Les panneaux persistants prévus à cet effet peuvent continuer à fonctionner après un redémarrage si leurs vues sont correctement réenregistrées au lancement du bot.

---

# Résumé du parcours d’un cosmétique

Pour créer puis vendre un cosmétique :

## Étape 1 — Préparer l’image

Cette étape ne concerne pas les titres.

Exemple :

```text
assets/profile/badges/flocon.png
```

## Étape 2 — Créer le cosmétique

Utiliser :

```text
/profil-admin
```

Puis **Créer un cosmétique**.

Exemple :

```text
Identifiant : badge-flocon
Type : badge
Nom affiché : Flocon
Chemin de l’image : badges/flocon.png
Valeur facultative :
```

## Étape 3 — Tester ou distribuer

Le cosmétique peut être distribué avec `/profil-admin` pour vérifier son rendu.

## Étape 4 — Ajouter à la boutique

Utiliser :

```text
/boutique-admin
```

Puis **Ajouter un cosmétique**.

Sélectionner le cosmétique créé précédemment et définir son prix.

## Étape 5 — Achat par un membre

Le membre utilise :

```text
/boutique
```

Après l’achat, le cosmétique apparaît dans son inventaire de profil.

---

# Exemple complet pour un titre

Un titre ne nécessite aucun fichier graphique.

Dans `/profil-admin` :

```text
Identifiant : titre-renard-legendaire
Type : title
Nom affiché : Renard légendaire
Chemin de l’image :
Valeur facultative : Renard légendaire
```

Puis dans `/boutique-admin` :

1. cliquer sur **Ajouter un cosmétique** ;
2. sélectionner `titre-renard-legendaire` ;
3. définir le prix ;
4. définir le niveau minimum si nécessaire ;
5. enregistrer l’article.

Aucun chemin `titles/...` ne doit être indiqué.
