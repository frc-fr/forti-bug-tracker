---
type: Project Rules
title: Règles de forti-bug-tracker
description: Règles communes aux bug trackers et particularités de FortiOS.
resource: https://github.com/frc-fr/forti-bug-tracker
tags: [rules, fortios, fortinet, bug-tracker]
timestamp: 2026-11-09T18:30:00+01:00
product: FortiOS
site: https://frc-fr.github.io/forti-bug-tracker/
---

# Critères communs

Section identique dans forti-, juni-, palo-, cisco- et f5-bug-tracker. Toute modification se reporte dans les cinq.

## Architecture

- Site statique : pas de serveur, pas de base de données.
- Python côté collecte, JavaScript sans framework côté navigateur.
- Paquet Python `<fournisseur>bugs`, une commande par étape :
  - `collect` : met à jour l'état des sources et télécharge ce qui a changé.
  - `extract` : lit les documents en cache ; échoue au moindre avertissement.
  - `build` : croise les données et génère `dist/`.
- Modules : `collect`, `parser`, `extract`, `normalize` (matériel), `lifecycle` (dates de support), `build`, `feed`, `cli`.

### Répertoires

- `sources/` : état des sources (adresses, ETag, lastmod, dates de support). Commité.
- `.cache/` : documents bruts. Non versionné, gardé par le cache de la CI.
- `data/extracted/` : un JSON par document, une ligne par bug pour des diffs lisibles. Commité.
- `data/changes.json` : journal des nouveautés. Absent au départ : la première extraction sert de référence.
- `site/` : `index.html`, `app.js` (affichage), `logic.js` (règles de statut, testables), `i18n.js`, `theme.js`, `style.css`, mentions légales FR/EN.
- `dist/` : site généré, avec `data/*.json` compacts et `feed.xml`. Non versionné.

### Modèle de données

- Un bug = identifiant, description, contournement, matériel cité, événements.
- Un événement = version, statut (`r` corrigé, `k` connu, `l` limitation…), page officielle.
- Les statuts par version sont calculés dans le navigateur, à partir des notes de la branche.

### Tests

- `pytest` : tests unitaires, plus tests sur les vrais documents en cache.
- `node --test tests/site/logic.test.js` : règles de statut et de comparaison.
- Test des clés de traduction et de la CSP.

## Sources et collecte

- Sources officielles et publiques du fournisseur en priorité.
- Source communautaire (ex. endoflife.date) seulement à défaut d'équivalent officiel, citée comme telle dans les mentions légales.
- robots.txt respecté : un chemin interdit n'est jamais interrogé.
- 2 secondes minimum entre deux requêtes, User-Agent du projet.
- Ne recharger que ce qui a changé (ETag, Last-Modified, lastmod du sitemap).
- Résultats d'extraction commités dans `data/` : vider le cache CI ne relance pas tout.
- Un avertissement d'extraction arrête la mise à jour : le site garde ses dernières données valides.
- Une source annexe (dates de support…) en échec garde ses dernières valeurs.
- Le navigateur ne contacte jamais de service tiers.

## Contenu

- Objet : bugs connus et bugs corrigés. Jamais la sécurité.
- Entrées de sécurité écartées, références CVE retirées des descriptions.
- Chaque fait renvoie à la page officielle exacte qui le porte.
- Textes des bugs laissés en anglais, tels que publiés.
- Statuts déduits des notes, jamais inventés ; « Inconnu » expliqué et masqué par défaut.
- Un modèle cité ne veut pas dire « seul ce modèle est touché ». Filtre matériel inclusif.
- Un bug à la fois correction et changement de comportement n'est compté qu'une fois.
- Une version annoncée mais pas encore publiée est marquée « non publiée ».
- Toutes les branches restent consultables ; les branches supportées sont mises en avant.
- Pas d'affirmation générale ou trop assurée dans les textes.

## Interface

- Français et anglais, sans page /en/ séparée.
- Bandeau visible : « vos sélections ne sont ni enregistrées ni transmises ».
- Onglets : Rechercher, Comparer, Matériel, puis Quoi de neuf à droite de Matériel.
- Comparaison : pastilles triées par ordre alphabétique, « Tous » en premier.
- Libellé court « Correction » ; risques (nouveaux, toujours présents) mis en valeur.
- Panneau « À lire » replié par défaut, il ne s'ouvre que si l'utilisateur le déplie.
- Listes déroulantes filtrables à la frappe ; bouton Réinitialiser.
- Tableau sélectionnable en entier et bouton « Copier le tableau ».
- Bouton de retour en haut de page.
- Logos RSS puis GitHub, minimalistes et presque transparents, à gauche de « EN ».
- Thème clair et sombre ; pas de noir trop profond.
- Textes longs justifiés, sur toute la largeur.
- Cron et date de dernière mise à jour affichés.
- Placeholders neutres : ne jamais révéler le matériel de l'utilisateur.
- Même forme dans tous les sites, quelle que soit la façon de présenter du fournisseur : on cherche au même endroit.
- Données uniformes entre fournisseurs : pas d'information propre à un seul fournisseur si elle n'aide pas l'exploitation (ex. date de mise en vente).
- Plusieurs systèmes : sélecteur de logiciel, libellé visible « Logiciel », jamais un choix de matériel.

## Matériel et nouveautés

- Onglet Matériel : pastilles de statut (« Tous » en premier, puis « Plus dans la dernière branche » ou son équivalent).
- Colonnes : Modèle, Première version, Dernière version, Statut <logiciel>, Version recommandée, Fin de support.
- Statut tiré d'une source officielle du fournisseur : il dit, sans le deviner, si le matériel est encore maintenu.
- Fin de vie annoncée par référence : variantes affichées séparément, pièces détachées et modules écartés.
- Pas de source : « Aucune fin annoncée », jamais « supporté ».
- Version recommandée seulement si le fournisseur la publie sans compte ; sinon la colonne est absente, et la note dit pourquoi.
- Rechercher : un modèle choisi affiche ce que le fournisseur dit de lui (statut, version recommandée, fin de support).
- Quoi de neuf : cartes « Dernière version publiée », « Dernier document mis à jour », puis « Recommandée par <fournisseur> » si elle existe.

## Design

- Même structure et mêmes jetons de couleur dans les trois sites.
- Couleur du fournisseur en touche seulement : bordure haute et nom du produit.
- Contraste professionnel, rien qui « pique les yeux ».
- Cohérence entre pages : mêmes pastilles partout, pas de tuiles géantes.

## Publication

- Cron du lundi au vendredi : 9 h 15, 14 h 15, 19 h 00, Europe/Paris.
- Horaire décrit dans `sources/schedule.yml` et affiché sur le site, qui le lit au build.
- Workflow GitHub sans déclencheur `schedule` (retardé ou oublié par GitHub) : lancé par `workflow_dispatch`.
- Ordre : tests, collecte, extraction, tests sur le corpus réel, commit des données, build, GitHub Pages.
- Flux RSS/Atom des nouveautés.
- CSP stricte : aucun script, style ou service tiers.

## Mentions et licence

- Outil créé et maintenu par FR Consulting ; contact@fr-consulting.fr ; lien vers fr-consulting.fr.
- Site indépendant, non affilié au fournisseur. Jamais « approuvé par ».
- Mentions légales FR et EN, avec la liste des services et composants tiers.
- Code sous AGPL 3.0 ou ultérieure ; contenus du fournisseur exclus.
- README générique : rien de sensible ni de personnel.

# Particularités FortiOS

## Versions

- Format `7.6.8`, avec un numéro de build (`build 3744`).
- Pas de hotfix ni de train : une correction vaut pour les versions suivantes de la branche.
- Statut « nouveau » (`n`) dans les Known Issues : avant cette version, statut « Inconnu ».

## Sources

- Un PDF de Release Notes par version, trouvé depuis la page de la version sur docs.fortinet.com.
- docs.fortinet.com : une page par version, sans query string, avec le Crawl-delay du robots.txt.
- PDF suivis par HEAD sur l'objet S3 : l'ETag indique une régénération.
- PDF absent : lecture des chapitres web (Known Issues, Resolved Issues), comme pour 7.4.7.
- Branche active : un document révisé dans les 90 derniers jours ; vérifiée à chaque passage.
- Branche dormante : vérifiée le lundi, ou en lancement manuel avec l'option `all` (`collect --all`).
- Nouvelles versions détectées à chaque passage, sur toutes les branches.
- Dates de support : API endoflife.date, source communautaire, citée dans les mentions légales.
- Version recommandée par modèle : article « Recommended release for FortiOS » de la communauté.
- Annotations manuelles (`sources/annotations.json`) : special build, article communautaire, toujours avec lien.

## Extraction

- PDF avec couche texte : pas d'OCR.
- Sections lues dans les signets, lignes lues par position sous les en-têtes « Bug ID / Description ».
- Premières notes 5.x : bugs en puces terminées par « (id) ».
- Catégories issues des tables, harmonisées.
- Contrôle croisé des identifiants trouvés sans géométrie.

## Matériel

- Noms ramenés au format FG (`FG-60F`), variantes regroupées par cœur (`60F`).
- Familles 6000, 7000, VM, et ASIC cités.
- Bug sans matériel cité : générique, toujours affiché.

## Mise à niveau

- Panneau « A lire : Upgrade information / Special notices », en deux colonnes.
- Changements CLI, de l'interface et « Changes in table size » : pastilles, car ils ont un Bug ID.
- Liens vers la page exacte du PDF.
- Lien vers l'Upgrade Path Tool, source d'inspiration du projet.

# Citations

[1] [Upgrade Path Tool](https://docs.fortinet.com/upgrade-tool/)
[2] [Recommended release for FortiOS](https://community.fortinet.com/fortigate-3/recommended-release-for-fortios-116639)
[3] [endoflife.date FortiOS](https://endoflife.date/fortios)
