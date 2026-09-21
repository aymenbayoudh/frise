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
- `deck` : tableau JSON de chemins hiérarchiques complets. **Chaque `::` crée exactement un niveau** : `["ICT::3::3::4"]` donne `ICT → 3 → 3 → 4`. Le site ne déduit aucune signification des noms de niveaux.
- `image` : tableau JSON d’images. Une image issue d’un paquet Anki peut être référencée par un chemin privé tel que `["ict_timeline_media/mon-image.jpg"]` (ou `ict_carto_media/...`) ; elle est alors chargée via l’accès GitHub privé. Une image ajoutée manuellement dans l’éditeur est intégrée au CSV en data URL, comme dans la frise.

Les champs contenant des virgules, guillemets ou retours à la ligne doivent être correctement échappés selon le standard CSV. Le fichier peut être UTF-8 avec BOM.

## Règles pour convertir des cartes Anki

1. **La colonne `deck` du CSV est la seule source de vérité pour l’arborescence.** La cartographie ne tente pas de reconnaître, compléter ou recréer un deck Anki à partir du contenu de la carte.
2. Un chemin est purement hiérarchique : `ICT::3::3::4` crée quatre niveaux. Un renommage ou déplacement depuis l’arbre modifie ce préfixe pour toutes les fiches concernées ; une modification depuis la fiche ne change que les chemins de cette fiche.
3. Pour une conversion Anki, utiliser le véritable chemin de deck seulement s’il est réellement présent dans les données exportées. **Ne jamais reconstruire automatiquement un deck à partir des champs `Matière`, `Thème` ou `Chapitre`.** Un export de deck filtré peut avoir perdu le deck d’origine ; dans ce cas il faut une correspondance explicite, pas une inférence.
4. Une note Anki peut produire plusieurs lignes cartographiques lorsqu'elle cite plusieurs exemples territoriaux distincts.
5. Retenir l'échelon territorial le plus précis qui porte réellement l'exemple : commune, groupement/EPCI, département ou région. Une carte sans territoire français identifiable n'est pas forcée sur la carte.
6. Le titre est déclaratif et court, pas formulé comme une question de flashcard. Le sous-titre porte le chiffre, le mécanisme ou le résultat principal.
7. Le corps conserve l'explication utile et les mises en perspective. Les styles Anki arbitraires, classes CSS, fonds et tailles de police ne sont pas importés ; conserver la mise en forme sémantique utile : gras, italique, souligné, retours à la ligne, listes et liens.
8. Les références bibliographiques, rapports, articles et jurisprudences vont dans `source`, afin d'apparaître dans l'onglet **Sources** de la fiche. Une URL est stockée comme lien HTML avec un libellé lisible.
9. Pour les médias Anki, copier les fichiers dans le dépôt privé (par défaut `ict_timeline_media/`, réutilisable par la frise et la cartographie) et mettre leurs chemins relatifs dans `image`. Les mêmes chemins sont aussi acceptés dans les balises `<img>` du HTML.
10. Les CSV peuvent être découpés physiquement comme on veut : leur nom de fichier ou leur dossier ne crée aucun niveau de deck. Seule la valeur de la colonne `deck` le fait.

## Import privé

Le bouton **Importer CSV** requiert désormais l'accès privé. Le fichier est vérifié, écrit dans `frise-data/carto/imports/`, ajouté au manifeste privé, puis immédiatement rechargé. Sans token privé, la carte affiche zéro fiche et les actions d'ajout/import sont désactivées.
