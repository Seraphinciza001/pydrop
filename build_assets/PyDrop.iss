; Installateur de PyDrop (Inno Setup 6)
; Compilation : "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build_assets\PyDrop.iss
; Prend le dossier construit par PyInstaller (build_assets\dist3\PyDrop) et produit PyDrop-Setup.exe

#define AppName "PyDrop"
#define AppVersion "1.9.0"
#define AppPublisher "Seraphin"
#define Source "dist3\PyDrop"

[Setup]
AppId={{6F1D3C2A-9B47-4E8A-B5C1-7A2E9D40F318}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments=Partage de fichiers en réseau local — By Seraphin
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Installation de PyDrop
; Installation pour l'utilisateur, sans droits d'administrateur
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; L'antivirus bloque parfois l'écriture finale dans le dossier livré : on compile à part, puis on copie
OutputDir=setup_out
OutputBaseFilename=PyDrop-Setup
SetupIconFile=pydrop.ico
UninstallDisplayIcon={app}\PyDrop.exe
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=setup_side_100.bmp,setup_side_150.bmp,setup_side_200.bmp
WizardSmallImageFile=setup_small_100.bmp,setup_small_150.bmp,setup_small_200.bmp
Compression=lzma2/ultra64
SolidCompression=yes
; Ferme PyDrop s'il est ouvert pendant une mise à jour
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "{#Source}\PyDrop.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Source}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Une version précédente ne doit pas laisser de fichiers obsolètes
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\PyDrop.exe"; Comment: "Partage de fichiers en réseau local"; AppUserModelID: "Seraphin.PyDrop"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PyDrop.exe"; Tasks: desktopicon; Comment: "Partage de fichiers en réseau local"

[Run]
Filename: "{app}\PyDrop.exe"; Description: "Lancer PyDrop"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Retire le menu « Envoyer avec PyDrop » de l'Explorateur
Filename: "{app}\PyDrop.exe"; Parameters: "--uninstall-shell"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveShellMenu"

[Messages]
fr.WelcomeLabel2=Cet assistant va installer [name/ver] sur votre ordinateur.%n%nPyDrop partage des fichiers et des dossiers entre vos ordinateurs et vos téléphones sur le même réseau Wi-Fi.%n%nAu premier lancement, Windows vous demandera d'autoriser PyDrop sur le réseau : cochez « Réseaux privés ».
fr.FinishedLabel=PyDrop est installé.%n%nPour le téléphone : installez PyDrop.apk, ou scannez le QR code affiché par PyDrop.
