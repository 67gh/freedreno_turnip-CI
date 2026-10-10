# Procédure de modification imposée par l’utilisateur

Pour chaque fichier, à chaque modification :

1. Lire son analyse dans `JOURNAL_ANALYSE_TURNIP.txt` avant de le modifier.
   Pour un nouveau fichier, écrire et lire son rôle et les risques dans le journal
   des verdicts avant de le créer.
2. Après modification, relire intégralement le fichier trois fois :
   logique et fonctionnement ; erreurs et cas limites ; cohérence avec le projet.
3. Consigner les trois relectures, les corrections, les tests, les limites et le
   verdict dans `JOURNAL_VERDICTS_TURNIP.txt`, avec l’empreinte de la version relue.
4. Si le fichier change encore, recommencer le cycle. Les tests ne remplacent
   pas les relectures. Ne jamais annoncer une compilation ou un essai matériel
   sans résultat effectivement observé.

Les journaux sont à la racine du projet livré. Le journal initial reste une
référence historique ; documenter les nouveaux constats dans le second journal.
Les ajouts au journal des verdicts sont le compte rendu de la procédure et
n’entraînent pas une récursion infinie de comptes rendus sur eux-mêmes.
Conserver les points de contrôle hors des seuls fichiers temporaires.
