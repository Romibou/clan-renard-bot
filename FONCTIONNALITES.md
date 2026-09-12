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
- panneaux administratifs interactifs.

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

## Types de récompenses

Le calendrier peut distribuer :

- un message ;
- des points saisonniers ;
- un rôle Discord ;
- une récompense aléatoire ;
- une récompense choisie parmi plusieurs possibilités avec pondération ;
- un cosmétique de profil ;
- une autre récompense gérée par la campagne.

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
