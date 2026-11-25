# PyDrop — By Seraphin

Partage de fichiers sur le réseau local : ordinateur ↔ ordinateur et ordinateur ↔ téléphone.

## Fichiers prêts à l'emploi

Dans le dossier **`PyDrop - Prêt à installer`** :

- **`PyDrop.exe`** (Windows) : double-cliquez, aucune installation. Il doit rester à côté de son dossier **`_internal`** : pour le copier sur un autre PC, copiez tout le dossier (ou un zip de celui-ci). Au premier lancement, Windows demande d'autoriser PyDrop sur le réseau : cochez **Réseaux privés** et acceptez. Si SmartScreen affiche « Windows a protégé votre ordinateur », cliquez **Informations complémentaires → Exécuter quand même** (l'exe n'est pas signé par un éditeur reconnu).
- **`PyDrop.apk`** (Android 7 et plus) : copiez-le sur le téléphone et ouvrez-le. Autorisez « Installer des applications inconnues » si Android le demande. L'application détecte automatiquement les ordinateurs PyDrop sur le même Wi-Fi.

Sur iPhone (ou sans l'APK) : scannez le QR code affiché par PyDrop sur le PC, la page s'ouvre dans le navigateur.

## Utilisation

- Ouvrez PyDrop sur chaque appareil du même réseau : ils apparaissent sur le radar.
- Touchez / cliquez un appareil pour lui **demander la connexion** ; l'autre doit **accepter** ou **refuser**.
- Une fois connecté (pastille verte), envoyez des fichiers (ou glissez-les sur l'appareil, sur PC).
- Les fichiers reçus vont dans `Téléchargements\PyDrop` (PC, modifiable) et `Téléchargements/PyDrop` (Android).

## Envoyer depuis le système

- **Android** : touchez *Partager* sur un fichier, choisissez **PyDrop**, puis l'ordinateur. Fonctionne aussi avec plusieurs fichiers.
- **Windows** : clic droit sur un fichier ou un dossier → **Envoyer avec PyDrop** (sous Windows 11 : *Afficher plus d'options*), ou **Envoyer vers → PyDrop**. Choisissez ensuite l'appareil. PyDrop s'ouvre tout seul s'il est fermé.
- Le menu s'installe au premier lancement de `PyDrop.exe`, uniquement pour votre compte Windows, et se retire avec l'interrupteur **Menu « Envoyer avec PyDrop »** dans l'application. Il suit l'emplacement de `PyDrop.exe` : relancez l'exe une fois si vous le déplacez.

## Envoyer un dossier

Sur PC : bouton **Envoyer un dossier**, glisser-déposer ou menu Windows. Le dossier est compressé à l'envoi et décompressé automatiquement à l'arrivée dans le dossier de réception. Vers un téléphone, l'application Android le décompresse dans `Téléchargements/PyDrop` ; dans un navigateur, il reste en `.zip`.

## Vidéos par lien (YouTube, Facebook, Instagram, TikTok…)

Dans l'application Android, onglet **Vidéos** : collez un lien, choisissez Vidéo ou Audio seul et le PC. Ou bien, depuis YouTube : *Partager → PyDrop*. Le PC télécharge la vidéo avec yt-dlp puis l'envoie au téléphone.

Au premier usage, le PC installe yt-dlp (23 Mo) et, pour la HD, ffmpeg (90 Mo, sauf s'il est déjà présent) dans `%LOCALAPPDATA%\PyDrop\tools`, depuis leurs pages officielles, avec vérification de l'empreinte. yt-dlp se met ensuite à jour une fois par jour. Seules les vidéos publiques sont accessibles ; respectez les conditions des sites et les droits d'auteur.

## Voir et contrôler le téléphone depuis le PC

Avec [scrcpy](https://github.com/Genymobile/scrcpy) (Android 11 ou plus, même Wi-Fi). Sur le PC, cliquez sur le téléphone connecté → **Voir et contrôler** ; ou dans l'application, panneau d'envoi → **Afficher ce téléphone sur le PC**.

La première fois : sur le téléphone, *Options pour les développeurs* → *Débogage sans fil* → *Associer l'appareil avec un code d'association*, puis tapez le code à 6 chiffres dans PyDrop sur le PC. scrcpy (11 Mo) s'installe tout seul dans `%LOCALAPPDATA%\PyDrop\tools\scrcpy`. Raccourcis dans la fenêtre : Ctrl gauche + H (accueil), + B (retour), + S (applications récentes).

## Envoyer à plusieurs appareils
Dans le panneau d'envoi, cochez « Envoyer aussi à » : les mêmes fichiers partent vers chaque appareil coché. Le menu Windows « Envoyer avec PyDrop » et « Partager avec PyDrop » sur Android permettent aussi de choisir plusieurs appareils.

## Presse-papiers partagé
- Téléphone → PC : onglet Transfert → Presse-papiers → Envoyer. Le texte est copié sur le PC (Ctrl+V).
- PC → téléphone : bouton « Presse-papiers » du panneau d'envoi, ou onglet « Textes ». Réglage « Presse-papiers automatique » : chaque Ctrl+C part tout seul vers les appareils connectés.

## Notifications du téléphone sur le PC
Uniquement dans `PyDrop-android-complet-notifications.apk` : Play Protect bloque souvent hors Play Store les applis qui lisent les notifications, d'où l'APK normal sans cette fonction.
Onglet Transfert → « Notifications sur le PC ». Android demande d'autoriser l'accès aux notifications (si « Paramètre restreint » : Infos sur l'appli → ⋮ → Autoriser les paramètres restreints). Les notifications apparaissent dans l'onglet « Notifs » du PC et en pop-up Windows ; une appli peut être masquée.

## Caméra du téléphone et enregistrement
Dans « Voir et contrôler » (PC) ou l'onglet Écran (téléphone) : Écran, Caméra avant ou Caméra arrière (Android 12+), et « Enregistrer en vidéo » (.mp4 dans le dossier de réception). Pour une webcam Zoom/Teams : OBS Studio → capture de fenêtre → caméra virtuelle.

## Télécommande
Onglet « Télécom. » du téléphone : pavé tactile (souris, clics, défilement, glisser-déposer), présentation (diapositives, écran noir), son et musique, saisie de texte. Les boutons de volume peuvent passer les diapositives. Réglage « Télécommande » sur le PC pour l'autoriser ou non.

## Applications et programmes
Les .apk / .exe arrivent intacts. Sur le téléphone, toucher un .apk reçu l'installe ; « Envoyer une application » envoie une appli installée (en .apks si elle est en plusieurs morceaux — PyDrop sait l'installer à l'arrivée). Sur le PC, un .exe/.msi reçu propose « Installer ».

## En cas de problème

Le journal de l'application se trouve dans `%USERPROFILE%\.pydrop\pydrop.log`, sur le PC concerné. Il contient les erreurs et, en cas de plantage, l'endroit où le programme s'est arrêté.

## Structure du code

- `app/pydrop.py` : moteur (découverte UDP port 47474, serveur HTTP/WebSocket port 8765, fenêtre)
- `app/ui/desktop.html` : interface de l'ordinateur (radar)
- `app/boot_splash.py` : fenêtre d'accueil animée du PC (images générées par `build_assets/make_splash_assets.py`)
- `mob/splash.js` : écran de chargement animé (fenêtre PC et téléphone)
- `app/shell/PyDropSend.cs` : petit relais du menu Windows (recompilé avec `csc`, voir l'en-tête du fichier)
- `mob/index.html` : page du téléphone (servie par le PC et embarquée dans l'APK)
- `mob/envelope.js` : animation de l'enveloppe, partagée par le PC et le téléphone
- `android/` : projet de l'application Android (WebView + découverte native + téléchargements)

## Reconstruire

Windows (depuis les sources) :

```
pip install -r requirements.txt pyinstaller
python app/pydrop.py              # lancer sans compiler
```

L'exe se reconstruit avec la commande PyInstaller utilisée dans `build_assets/PyDrop.spec` :

```
pyinstaller build_assets/PyDrop.spec --noconfirm
```

Android (JDK 17+ et SDK Android requis) :

```
cd android
gradlew assembleRelease
```

L'APK est signé avec `android/pydrop-release.jks` (mots de passe dans `android/keystore.properties`). **Gardez ces deux fichiers** : ils sont nécessaires pour publier des mises à jour de l'application.
