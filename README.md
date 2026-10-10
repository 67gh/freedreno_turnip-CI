# Turnip pour Android ARM64

Ce projet compile Mesa Turnip pour un appareil Adreno avec noyau KGSL et produit
un paquet pour une application compatible **Adreno Tools**. Il ne produit pas de
module Magisk. Le nom historique du ZIP contient `a660`, mais le code ne comporte
pas de réglage exclusif à l’Adreno 660. Aucun gain de performances, niveau Vulkan
ou fonctionnement dans un jeu n’est garanti par une simple compilation.

## Configuration figée

- Hôte : Linux x86_64 ; environnement de référence Ubuntu 24.04, Python 3.12.
- Cible : ARM64, Android 14/API 34 minimum, KGSL ; application avec chargeur Adreno Tools.
- Mesa : commit `9cb4a4fb42a8a067cd2250e116c6a605b527a093` (26.3.0-devel).
- NDK : r29. Les deux archives sont vérifiées par SHA-256 avant extraction.
- Compilation release `-O3`, sans LTO ni extensions Vulkan beta forcées.
- Segments ELF vérifiés pour un alignement de 16 Kio après strip et patchelf.
  Ce contrôle ne prouve pas la compatibilité de l’application et de l’appareil.

## Compiler localement

Conserver tout le projet, y compris `scripts/`, puis, sous Ubuntu 24.04 :

```bash
sudo apt-get update
sudo apt-get install -y build-essential python3-venv curl ca-certificates \
  patchelf pkg-config flex bison glslang-tools
bash ./turnip_builder.sh --check
python3 -m unittest discover -s tests -v
JOBS=4 bash ./turnip_builder.sh
```

Prévoir plusieurs Go d’espace disque et un accès réseau pour Mesa, le NDK et PyPI.
Le script crée son environnement Python privé avec des versions de dépendances
fixées ; il ne modifie pas le Python système. `--check` vérifie les outils hôtes,
pas une compilation. `--help` affiche les options. Les chemins contenant une
apostrophe, un antislash ou un saut de ligne ne sont pas acceptés.

Chaque lancement crée `turnip_workdir/run-XXXXXXXX/` à côté du script. Ce dossier
contient les logs, les sources, les outils, les fichiers Meson et, seulement en cas
de succès, `turnip_a660_final_adrenotools.zip`, son `.sha256` et `build-info.json`.
Aucune ancienne sortie n’est réutilisée. Le chemin du ZIP réussi est affiché.
Pour économiser les téléchargements, `NDK_ARCHIVE` et `MESA_ARCHIVE` peuvent
indiquer des ZIP locaux ; les mêmes empreintes restent exigées.

Les anciens dossiers de travail peuvent être supprimés manuellement après avoir
conservé les logs utiles. Ne pas supprimer un dossier pendant sa compilation.
Le répertoire `patches/` est réservé : des fichiers autres que `.gitkeep` provoquent
un refus explicite, car aucune série de patches n’est intégrée dans cette version.

## Installer et diagnostiquer

Importer le ZIP dans le sélecteur de pilotes de l’application compatible Adreno
Tools, selon sa documentation. Ne pas l’installer comme un module Magisk.
En cas d’échec, conserver `python.log`, `*.check.log`, `compiler.log`, `meson.log`,
`ninja.log`, `elf.log` et `build/meson-logs/` lorsqu’ils existent. Certains logs
n’existent pas si l’erreur se produit avant leur étape.

Le paquet contient `meta.json`, `vulkan.freedreno.so` et `build-info.json`.
L’empaquetage vérifie ELF64/AArch64, SONAME, dépendances reconnues, alignement et
intégrité ZIP. Les bibliothèques système reconnues doivent aussi être accessibles
dans l’espace de chargement de l’application ; seul un essai sur appareil le confirme.
`runtimeTested: false` est conservé tant que ces essais n’ont pas été réalisés.
Les témoignages historiques sont séparés dans [list.md](list.md).

## GitHub Actions et versions

Lancement manuel, ou les 1er et 15 à **05:20 UTC** (06:20 à Libreville), avec
retards possibles du service. Le workflow lance le bon script, teste les régressions
et conserve les logs même en cas d’échec. Les publications sont sérialisées.
Seule la branche `main` publie ; une autre branche conserve ses artifacts.

Chaque build publié dispose d’un tag `turnip-<run_id>-<attempt>`. La release
historique `github_run` est aussi mise à jour. Son `update.json` pointe vers le ZIP
du tag propre au build, afin de conserver la correspondance manifeste/binaire.
`versionCode` reste une chaîne décimale, comme dans l’ancien contrat, et contient
l’horodatage Unix en millisecondes. Les clients doivent comparer numériquement
avec une capacité 64 bits ; aucun client de mise à jour n’est livré ici.
`packageVersion` inclut cet horodatage, le commit Mesa et l’identité du run.

Les builds programmés recompilent **la révision figée**, pas automatiquement le
nouveau `main` de Mesa. Pour changer de source, revoir ensemble `MESA_COMMIT`,
`MESA_SHA256`, les options Meson et les dépendances, puis refaire les tests et
la compilation. Une empreinte différente doit être expliquée avant de la changer.
Les versions système, horodatages et chemins peuvent varier : il s’agit de sources
identifiables, pas d’une promesse de ZIP identiques octet pour octet.

## Maintenance et provenance

Respecter [AGENTS.md](AGENTS.md), le journal d’analyse et le journal des verdicts
pour toute modification. Le projet dérive de `ilhan-athn7/freedreno_turnip-CI` ;
l’archive fournie comporte l’origine Git `67gh/freedreno_turnip-CI`. Les instructions
ci-dessus utilisent cette copie complète, pas un ancien script téléchargé ailleurs.
Voir [changelog.md](changelog.md), [Mesa](https://gitlab.freedesktop.org/mesa/mesa),
[NDK r29](https://github.com/android/ndk/releases/tag/r29) et le
[format Adreno Tools](https://github.com/bylaws/libadrenotools/blob/master/tools/ADPKG.md).
