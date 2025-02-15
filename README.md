# Compagnon Mythic GME

Un petit outil codé en un après midi pour m'assister dans l'utilisation du Mythic Game Master Emulator

On peut poser ses questions et gérer son facteur de chaos
![Screenshot 2025-02-15 at 20-41-08 Compagnon Mythic GME](https://github.com/user-attachments/assets/2fa2c950-9fa5-45f8-9720-0850698f4e89)

On peut gérer notre liste d'objectifs, de PNJ importants (avec tirage aléatoire pour en recroiser certains), de scènes...
![Screenshot 2025-02-15 at 20-42-19 Compagnon Mythic GME](https://github.com/user-attachments/assets/deee6689-1e19-4135-99dc-c77afe4c46a8)![Screenshot 2025-02-15 at 20-42-30 Compagnon Mythic GME](https://github.com/user-attachments/assets/fa122779-0f68-4fcd-bf98-5051bfb231a5)![Screenshot 2025-02-15 at 20-42-47 Compagnon Mythic GME](https://github.com/user-attachments/assets/0170eac5-aaa7-41c2-9fab-57a4d5b4cf96)

Un petit lanceur de d100 basique, toutes les tables aléatoires inclues dans Mythic, et une page de journal, exportable en Markdown
![Screenshot 2025-02-15 at 20-44-38 Compagnon Mythic GME](https://github.com/user-attachments/assets/3e640bdb-4cf1-4985-a61e-cb3f229a5f0d)![Screenshot 2025-02-15 at 20-44-49 Compagnon Mythic GME](https://github.com/user-attachments/assets/513e7102-9a46-4e12-ad70-a13cc5b8ce84)![Screenshot 2025-02-15 at 20-45-30 Compagnon Mythic GME](https://github.com/user-attachments/assets/5527e657-eb8a-4cf9-94e0-131de754910a)

Et ca mériterais un peu de fignolage, de corrections visuelles, orthographiques, des trad plus exactes, etc.

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
