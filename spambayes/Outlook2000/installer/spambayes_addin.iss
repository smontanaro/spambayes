;
; Inno Setup 4.x setup file for the Spambayes Outlook Addin
;

[Setup]
AppName=Spambayes Outlook Addin
AppVerName=Spambayes Outlook Addin 0.5
AppVersion=0.5
DefaultDirName={pf}\Spambayes Outlook Addin
DefaultGroupName=Spambayes Outlook Addin
OutputDir=.
OutputBaseFilename=SpamBayes-Outlook-Setup

[Files]
Source: "dist\spambayes_addin.dll"; DestDir: "{app}"; Flags: ignoreversion regserver
Source: "dist\*.*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "dist\about.html"; DestDir: "{app}"; Flags: isreadme

[UninstallDelete]
Type: filesandordirs; Name: "{app}\support"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := true;
  if not RegKeyExists( HKCU, 'Software\Microsoft\Office\Outlook') then
    begin
      Result := MsgBox(
            'Outlook appears to not be installed.' + #13 + #13 +
            'This addin only works with Microsoft Outlook 2000 and later - it' + #13 +
            'does not work with Outlook express.' + #13 + #13 +
            'If you know that Outlook is installed, you may with to continue.' + #13 + #13 +
            'Continue with installation?',
            mbConfirmation, MB_YESNO) = idYes;
    end;
end;

