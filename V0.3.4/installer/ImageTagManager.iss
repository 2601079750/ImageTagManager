#ifndef AppVersion
  #define AppVersion "0.3.4"
#endif
#define VersionRoot ".."

[Setup]
AppId={{55923FBF-2267-4BC7-98C2-DA9F1543767C}
AppName=拾图 · ImageTagManager
AppVersion={#AppVersion}
AppVerName=拾图 · ImageTagManager v{#AppVersion}
AppPublisher=ImageTagManager
AppPublisherURL=https://github.com/2601079750/ImageTagManager
AppSupportURL=https://github.com/2601079750/ImageTagManager/issues
AppUpdatesURL=https://github.com/2601079750/ImageTagManager/releases
VersionInfoVersion={#AppVersion}.0
DefaultDirName={localappdata}\Programs\ImageTagManager
DefaultGroupName=拾图 · ImageTagManager
DisableProgramGroupPage=yes
DisableDirPage=no
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#VersionRoot}\release
OutputBaseFilename=ImageTagManager-{#AppVersion}-Windows-x64-Setup
SetupIconFile={#VersionRoot}\assets\app-icon.ico
UninstallDisplayIcon={app}\ImageTagManager.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=no
RestartApplications=no
AppMutex=Local\Shitu.ImageTagManager.Application
SetupMutex=Shitu.ImageTagManager.Setup
InfoBeforeFile=INSTALLATION.txt
ChangesAssociations=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#VersionRoot}\ImageTagManager.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#VersionRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#VersionRoot}\README.en.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#VersionRoot}\RELEASE_NOTES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#VersionRoot}\docs\INSTALLATION.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#VersionRoot}\docs\REMOVAL.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\拾图 · ImageTagManager"; Filename: "{app}\ImageTagManager.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\拾图 · ImageTagManager"; Filename: "{app}\ImageTagManager.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ImageTagManager.exe"; Description: "{cm:LaunchProgram,拾图 · ImageTagManager}"; Flags: nowait postinstall skipifsilent

; No InstallDelete or UninstallDelete: data, portable.json, backups and original
; images are runtime user files and are never installer payload or delete targets.
