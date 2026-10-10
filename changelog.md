# Journal des changements

## 10 octobre 2026 — fiabilisation du projet

- Appel corrigé vers `turnip_builder.sh` et arrêt effectif sur erreur.
- Dossiers de travail uniques ; suppression des faux succès liés aux anciens ZIP.
- Mesa figé au commit `9cb4a4fb42a8a067cd2250e116c6a605b527a093` ; NDK r29.
- Empreintes des archives contrôlées, extraction avec permissions et liens Unix.
- Dépendances Python isolées et versionnées ; fichiers Meson natif/croisé séparés.
- Suppression du LTO forcé, explicitement non pris en charge par Mesa.
- Strip effectif, SONAME cohérent, contrôles ELF/AArch64, alignement et ZIP.
- Métadonnées fondées sur la version Mesa réelle et provenance dans build-info.json.
- Logs conservés en échec, publications sérialisées et URL propre à chaque build.
- Documentation Magisk, horaires et anciennes promesses de performances corrigées.
- Tests de régression et procédure de trois relectures pour chaque modification.

La version Vulkan exposée, les performances et la compatibilité des jeux doivent
être mesurées sur un appareil réel. Les releases restent des préversions et
`runtimeTested` reste faux. Consulter le journal des verdicts pour les résultats
exacts des contrôles réalisés ; ne pas déduire un essai matériel de ce changelog.

Pour chaque ZIP, `build-info.json` identifie le commit Mesa, les empreintes des
archives, la version du paquet et celle du pilote. Le lien de source y est fixé
au commit compilé. Cette note décrit les changements du système de compilation,
pas une liste inventée des changements internes de Mesa.
