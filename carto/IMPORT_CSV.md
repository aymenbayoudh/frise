# Import CSV de la cartographie

La cartographie ne contient aucune fiche publique : les exemples sont chargés uniquement après connexion à l'accès privé GitHub. Les CSV privés actifs sont déclarés dans `frise-data/carto-files.json`.

## Schéma CSV

Ordre recommandé des colonnes :

```text
id,title,subtitle,mode,unit,unitName,unitCode,kind,lat,lng,departmentCode,regionCode,centerName,tags,color,html,source,deck,image
```

- `id` : entier unique dans le fichier source.
- `title` : titre court ; HTML inline limité à `b/strong/i/em/u/br`.
- `subtitle` : sous-titre court, même logique typographique que le titre.
- `mode` : `commune`, `interco`, `departement` ou `region`.
- `unit` : identifiant interne stable. Pour une commune, préférer `commune-CODE_INSEE`; pour un EPCI `interco-SIREN`. Un identifiant historique déjà utilisé peut être conservé.
- `unitName` : nom affiché du territoire.
- `unitCode` : code INSEE / SIREN administratif. Il peut rester vide pour un groupement libre ou un syndicat sans géométrie administrative correspondante.
- `kind` : `global` par défaut ; `point`, `street` ou `quarter` pour une localisation communale plus précise.
- `lat`, `lng` : coordonnées WGS84 du siège ou du point.
- `departmentCode`, `regionCode` : codes administratifs utiles au rattachement.
- `centerName` : ville-centre, surtout pour les groupements libres.
- `tags` : tableau JSON, par exemple `["Chiffres","Veille_territoriale"]`.
- `color` : couleur de fiche au format hexadécimal, par exemple `#4A92D6`.
- `html` : corps de la fiche. HTML autorisé : paragraphes/divisions, gras, italique, souligné, listes, liens HTTP(S) et images sûres.
- `source` : sources séparées du corps ; même HTML sûr. Les liens `<a href="https://…">texte affiché</a>` sont cliquables.
- `deck` : tableau JSON de chemins complets, par exemple `["Culture générale::IA et numérique::I.C - Usages publics et exemples territoriaux"]`.
- `image` : tableau JSON d'images, le plus souvent `[]`.

Les champs contenant des virgules, guillemets ou retours à la ligne doivent être correctement échappés selon le standard CSV. Le fichier peut être UTF-8 avec BOM.

## Règles pour convertir des cartes Anki

1. Le nom d'un deck de copie/filtre n'est jamais utilisé comme deck final. Quand les champs d'origine existent, reconstruire le chemin complet à partir de `Matière::Thème::Chapitre`.
2. Une note Anki peut produire plusieurs lignes cartographiques lorsqu'elle cite plusieurs exemples territoriaux distincts.
3. Retenir l'échelon territorial le plus précis qui porte réellement l'exemple : commune, groupement/EPCI, département ou région.
4. Une carte sans territoire français identifiable n'est pas forcée sur la carte.
5. Le titre est déclaratif et court, pas formulé comme une question de flashcard. Le sous-titre porte le chiffre, le mécanisme ou le résultat principal.
6. Le corps conserve l'explication utile et les mises en perspective. Les styles Anki arbitraires, classes CSS, fonds et tailles de police ne sont pas importés : la carte applique sa propre présentation, identique à la logique de la frise.
7. Conserver seulement la mise en forme sémantique utile : gras, italique, souligné, retours à la ligne, listes et liens.
8. Les références bibliographiques, rapports, articles et jurisprudences vont dans `source`, afin d'apparaître dans l'onglet **Sources** de la fiche.
9. Une URL de source doit être enregistrée sous forme de lien HTML avec un libellé lisible ; le modificateur permet ensuite de modifier directement le texte affiché.
10. Les vrais chemins de decks restent dans la colonne `deck`, même si les CSV sont regroupés par deck racine ou par thème.

## Import privé

Le bouton **Importer CSV** requiert désormais l'accès privé. Le fichier est vérifié, écrit dans `frise-data/carto/imports/`, ajouté au manifeste privé, puis immédiatement rechargé. Sans token privé, la carte affiche zéro fiche et les actions d'ajout/import sont désactivées.
