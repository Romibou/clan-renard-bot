# Checklist avant déploiement

## Projet

- [ ] Le générateur s'est terminé sans erreur.
- [ ] Le dossier `clan-renard-bot` existe.
- [ ] Le fichier `clan-renard-bot.zip` existe.
- [ ] `python scripts/check_project.py` réussit.
- [ ] `pytest` réussit.
- [ ] L'aperçu graphique est correct.
- [ ] Le vrai fichier `.env` n'est pas envoyé sur GitHub.

## Discord

- [ ] L'application Discord est créée.
- [ ] Le bot est créé.
- [ ] Le token a été ajouté uniquement aux secrets.
- [ ] `Server Members Intent` est activé.
- [ ] Le bot a été invité avec `bot` et `applications.commands`.
- [ ] Le bot peut voir le salon du calendrier.
- [ ] Le bot peut envoyer des messages.
- [ ] Le bot peut intégrer des liens.
- [ ] Le bot peut joindre des fichiers.
- [ ] Le bot peut gérer les rôles si nécessaire.
- [ ] Le rôle du bot est assez haut dans la hiérarchie.

## GitHub

- [ ] Le dépôt ne contient pas `.env`.
- [ ] Le dépôt ne contient pas le token Discord.
- [ ] Le dépôt ne contient pas de mot de passe PostgreSQL.
- [ ] Tous les fichiers et assets nécessaires sont publiés.
- [ ] La branche principale a été envoyée.

## Render

- [ ] Le dépôt GitHub est connecté.
- [ ] La base PostgreSQL existe.
- [ ] `DATABASE_URL` est liée à la base.
- [ ] `DISCORD_TOKEN` est configuré.
- [ ] Le service utilise le Dockerfile.
- [ ] Le contrôle `/health` répond.
- [ ] Les logs indiquent que Discord est connecté.

## Calendrier

- [ ] `/avent-admin-initialiser` a été utilisé.
- [ ] Le fuseau horaire est correct.
- [ ] L'heure d'ouverture est correcte.
- [ ] Le canal est configuré.
- [ ] Le rattrapage est configuré.
- [ ] Les 24 récompenses ont été vérifiées.
- [ ] Les rôles de récompense existent.
- [ ] `/avent-admin-apercu` fonctionne.
- [ ] Le panneau public a été publié.
- [ ] Les annonces automatiques ont été configurées.
