# Compagnon Mythic GME

Un petit outil codé en quelques heures pour m'assister dans l'utilisation du Mythic Game Master Emulator

Déjà les fonctions de bases, on peut gérer le facteur de Chaos, et poser des questions à l'oracle Mythic
![image](https://github.com/user-attachments/assets/174bebc9-c756-4d25-86f7-8caf7dac6558)

On peut lister ses objectifs, PNJ rencontrés, scènes (avec jet de Chaos)
![image](https://github.com/user-attachments/assets/4ead574b-cd36-40fd-96fa-7578f6498c31)
![image](https://github.com/user-attachments/assets/68017041-e729-4cf0-94f4-7c212a632728)
![image](https://github.com/user-attachments/assets/b21629d1-30b3-4ea4-a02c-54935ce7aaf9)

Il y a une gestion basique des PJ et de leur description/inventaire
![image](https://github.com/user-attachments/assets/1db1e5b0-3102-4e9f-a61e-08a6e5ff2bf2)

Il y a quelques tables aléatoires, je n'ai pas mises celles du Mythic GME pour des raisons de droit d'auteur. Et on peut ajouter ses propres tables.
![image](https://github.com/user-attachments/assets/912fcfa6-66e4-4052-ab45-a6cc9a59a4ce)
![image](https://github.com/user-attachments/assets/b8be543b-dfed-44e3-b034-d4af044beef2)

Un petit lanceur de dés simple
![image](https://github.com/user-attachments/assets/9a8f1c4d-bf04-407d-afd9-85205e2a91cd)

Une gestion d'inventaire basique
![image](https://github.com/user-attachments/assets/86c702da-665b-44b7-bc9d-bc42e90007d2)

Et un journal très basique
![image](https://github.com/user-attachments/assets/f023a9a3-7676-4b9b-bf32-a029d169bdfc)

Et ca mériterais un peu de fignolage, de corrections visuelles, orthographiques, des trad plus exactes, etc.
Surtout que je ne suis pas programmeur professionel, alors beaucoup de code notamment du backend pourrait être mieux foutu.

Pour l'utiliser :

Installer python 3, puis les packages suivants :
```bash
python3 -m pip install flask flask-sqlalchemy flask-wtf
```
puis simplement lancer le script :
```bash
python app.py
```
Puis on ouvre http://127.0.0.1:5000/ dans notre navigateur.
