# forti-bug-tracker

Site statique de suivi des bugs FortiOS et de leurs corrections, construit à partir des Release Notes
publiques de Fortinet.

Site : https://frc-fr.github.io/forti-bug-tracker/

Ce projet est indépendant. Il n'est pas affilié à Fortinet.
Les informations sont fournies à titre indicatif : vérifiez toujours la documentation officielle.

## Fonctionnalités

- Recherche par numéro de bug ou mots-clés, par version et par matériel
- Mise en avant des branches supportées, sans masquer les autres
- Comparaison de deux versions : bugs corrigés, nouveaux problèmes ouverts, problèmes toujours présents,
  changements de la CLI et de l'interface, et chapitres à lire avant la mise à niveau
- Onglet Matériel : versions dont les notes listent chaque modèle, statut, version recommandée et fin de
  support selon Fortinet
- Suivi des nouveautés, avec un flux RSS/Atom
- Page « État du traitement », en bas de page : ce que le dernier traitement n'a pas lu, et pourquoi
- Interface en français et en anglais

Vos recherches et vos filtres restent dans votre navigateur : ils ne sont ni enregistrés ni transmis.
Ce projet s'inspire de l'[Upgrade Path Tool](https://docs.fortinet.com/upgrade-tool/) de Fortinet.

## Ce que disent les notes, et ce qu'elles ne disent pas

- Fortinet publie une note par version de FortiOS (7.6.4), avec ses problèmes résolus (« Resolved
  Issues ») et ses problèmes connus (« Known Issues »). FortiOS n'a ni hotfix ni train : une correction vaut
  pour les versions suivantes de la branche.
- Un problème connu marqué « nouveau » dans une version n'est pas situé avant elle : son statut y est
  « Inconnu ».
- Chaque note liste les modèles qu'elle supporte : c'est la source des versions de l'onglet Matériel.
- Les notes ne rangent pas les bugs par modèle. Un modèle n'est connu que lorsque le texte le cite. Le
  filtre matériel est donc inclusif : avec un modèle choisi, il garde les bugs qui le citent, ceux qui ne
  citent que sa famille et ceux qui ne citent aucun matériel.
- Les avis de sécurité sont écartés et les références CVE retirées des descriptions.
- Chaque identifiant de bug listé par une note finit lu, écarté par une règle ou non compris. Les
  identifiants sont aussi relevés dans le texte brut des chapitres de bugs, sans la mise en page : un
  identifiant compté nulle part rend la note « suspecte ». Une note que le code ne sait pas lire en entier
  est publiée pour ce qu'elle a de compris, et la page « État du traitement » le montre.

## Sources

- Release Notes PDF de chaque version, trouvées depuis la page de la version sur `docs.fortinet.com`, dans
  le respect du Crawl-delay de son robots.txt. Un PDF est suivi par une requête HEAD sur son objet de
  stockage : son ETag indique qu'il a été régénéré. Si le PDF manque, les chapitres web (Known Issues,
  Resolved Issues) sont lus à la place. Deux secondes au moins séparent deux requêtes.
- Pour limiter les requêtes, une branche est active si l'un de ses documents a été révisé dans les 90
  derniers jours : tous ses documents sont alors vérifiés à chaque passage. Les branches dormantes ne sont
  vérifiées que le lundi, ou lors d'un lancement manuel qui le demande (`collect --all`). Les nouvelles
  versions sont cherchées à chaque passage, sur toutes les branches.
- Dates de support des branches : [API endoflife.date](https://endoflife.date/fortios), une source
  communautaire, car Fortinet ne publie ses dates que sur un portail avec compte. Elles sont lues pendant
  la collecte, jamais par votre navigateur ; si l'API ne répond pas, les dernières dates sont gardées.
- Version recommandée par modèle : article
  [Recommended release for FortiOS](https://community.fortinet.com/fortigate-3/recommended-release-for-fortios-116639)
  de la communauté Fortinet, revu chaque trimestre. Résultat dans `sources/recommended.json`.
- Annotations ajoutées à la main (`sources/annotations.json`) : special build, article de la communauté,
  toujours avec leur lien.
- Le résultat de l'extraction est commité dans `data/` : vider le cache de la CI ne relance pas le
  téléchargement de tous les PDF.

## Mise à jour

Un traitement GitHub Actions s'exécute du lundi au vendredi à 9 h 15, 14 h 15 et 19 h 00, heure de
Paris, et sur lancement manuel. Cet horaire est décrit dans `sources/schedule.yml`, que le site lit pour
l'afficher. Il collecte, extrait, publie le site sur GitHub Pages, puis contrôle. Ce que le code ne sait pas
lire est publié dans `data/report.json` et sur la page « État du traitement » ; le passage finit en échec
pour le signaler. La mise à jour ne s'arrête que si moins de 75 % des versions sont lues : le site garde
alors sa version précédente.

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

Pour récupérer les documents puis prévisualiser le site :

```sh
.venv/bin/fortibugs collect
.venv/bin/fortibugs extract
.venv/bin/fortibugs check
.venv/bin/fortibugs --base-url http://localhost:8050/ build
python3 -m http.server 8050 --directory dist
```

## Licence

Le code est distribué sous licence [GNU AGPL 3.0 ou ultérieure](LICENSE).

Cette licence ne couvre pas les contenus de tiers, notamment les textes issus de la documentation
Fortinet. Fortinet, FortiGate et FortiOS sont des marques de Fortinet, Inc.

## Contact

Outil créé et maintenu par [FR Consulting](https://fr-consulting.fr).
Pour toute demande : contact@fr-consulting.fr
