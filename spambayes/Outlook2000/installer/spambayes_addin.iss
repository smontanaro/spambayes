;
; Inno Setup 4.x setup file for the Spambayes Outlook Addin
;

[Setup]
AppName=Spambayes Outlook Addin
AppVerName=Spambayes Outlook Addin 0.6
AppVersion=0.6
DefaultDirName={pf}\Spambayes Outlook Addin
DefaultGroupName=Spambayes Outlook Addin
OutputDir=.
OutputBaseFilename=SpamBayes-Outlook-Setup
; Note the check for Outlook running has already been done, so no point
; having this file tell them to shutdown outlook!
; Edit file using Windows 'wordpad'
InfoBeforeFile=installation_notes.rtf
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
    if not RegKeyExists( HKCU, 'Software\Microsoft\Office\Outlook') then begin
        Result := MsgBox(
              'Outlook appears to not be installed.' + #13 + #13 +
              'This addin only works with Microsoft Outlook 2000 and later - it' + #13 +
              'does not work with Outlook express.' + #13 + #13 +
              'If you know that Outlook is installed, you may with to continue.' + #13 + #13 +
              'Continue with installation?',
              mbConfirmation, MB_YESNO) = idYes;
    end;
    while Result do begin
        if not CheckForMutexes('_outlook_mutex_') then
            break;

          Result := MsgBox(
              'You must close Outlook before SpamBayes can be installed.' + #13 + #13 +
              'Please close all Outlook Windows (using "File->Exit and Log off"' + #13 +
              'if available) and click Retry, or click Cancel to exit the installation.'+ #13 + #13 +
              'If this message persists after closing all Outlook windows, you may' + #13 +
              'need to log off from Windows, and try again.',
              mbConfirmation, MB_RETRYCANCEL) = idRetry;
    end;
end;

