# forti-bug-tracker

Site statique de suivi des bugs FortiOS et de leurs corrections, construit à partir de la
documentation publique de Fortinet.

Site : https://frc-fr.github.io/forti-bug-tracker/

Ce projet est indépendant. Il n'est ni affilié à Fortinet, ni approuvé par Fortinet. Les
informations sont fournies à titre indicatif : vérifiez toujours la documentation officielle.

## Fonctionnalités

- Recherche par numéro de bug ou mots-clés, par version et par matériel
- Comparaison de deux versions
- Informations par modèle, dont la version recommandée
- Suivi des nouveautés, avec un flux RSS/Atom
- Interface en français et en anglais

Vos recherches et vos filtres restent dans votre navigateur : ils ne sont ni enregistrés ni
transmis. Ce projet s'inspire de l'[Upgrade Path Tool](https://docs.fortinet.com/upgrade-tool/) de Fortinet.

## Mise à jour automatique

Un traitement GitHub Actions s'exécute plusieurs fois par jour en semaine. Il récupère la documentation publique,
en extrait les données, les contrôle, puis publie le site sur GitHub Pages. Si un contrôle
échoue, le site conserve ses dernières données valides.

Le traitement tourne du lundi au vendredi à 9 h 15, 14 h 15 et 19 h 00, heure de Paris. Pour
limiter les requêtes, tous les documents ne sont pas vérifiés à chaque passage :

- Une branche FortiOS est active si l'un de ses documents a été révisé dans les 90 derniers
  jours. Tous ses documents sont alors vérifiés à chaque passage, quel que soit leur âge.
- Les branches dormantes ne sont vérifiées que le lundi et lors d'un lancement manuel.
- Les nouvelles versions sont détectées à chaque passage, sur toutes les branches.
- Une branche dormante révisée redevient active d'elle-même.

## Liens utiles chez Fortinet

- [Communauté FortiGate](https://community.fortinet.com/fortigate-3) : articles techniques et discussions
- [Versions recommandées de FortiOS](https://community.fortinet.com/fortigate-3/recommended-release-for-fortios-116639)
- [Documentation FortiGate / FortiOS](https://docs.fortinet.com/product/fortigate), dont les Release Notes
- [Upgrade Path Tool](https://docs.fortinet.com/upgrade-tool/) : chemin de mise à niveau, très utile pour préparer une mise à jour
- [Portail de support](https://support.fortinet.com/) : compte requis

Fortinet propose aussi son propre
[Bug Tracker](https://docs.fortinet.com/document/forticloud/latest/partner-administration-guide/919257/bug-tracker),
réservé aux partenaires et accessible depuis le portail FortiCare.

## Développement

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
node --test tests/site/logic.test.js
```

Pour prévisualiser le site :

```sh
.venv/bin/fortibugs --base-url http://localhost:8000/ build
python3 -m http.server 8000 --directory dist
```

## Licence

Le code est distribué sous licence [GNU AGPL 3.0 ou ultérieure](LICENSE).

Cette licence ne couvre pas les contenus de tiers, notamment les textes issus de la
documentation Fortinet. Fortinet, FortiGate et FortiOS sont des marques de Fortinet, Inc.

## Contact

Outil créé et maintenu par [FR Consulting](https://fr-consulting.fr).
Pour toute demande : contact@fr-consulting.fr
