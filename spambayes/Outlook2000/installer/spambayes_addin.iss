;
; Inno Setup 3.x setup file for the Spambayes Outlook Addin
;

[Setup]
AppName=Spambayes Outlook Addin
AppVerName=Spambayes Outlook Addin 0.0.1
AppVersion=0.0.1
DefaultDirName={pf}\Spambayes Outlook Addin
DefaultGroupName=Spambayes Outlook Addin
OutputDir=.
OutputBaseFilename=SpamBayes-Outlook-Setup

[Files]
Source: "dist\spambayes_addin.dll"; DestDir: "{app}"; Flags: ignoreversion regserver
Source: "dist\*.*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[UninstallDelete]
Type: filesandordirs; Name: "{app}\support"

