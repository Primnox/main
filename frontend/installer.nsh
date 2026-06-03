!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"

Var Dialog
Var ApiKeyLabel
Var ApiKeyHint
Var ApiKeyInput
Var ApiKeyValue

Page custom ApiKeyPage ApiKeyPageLeave

Function ApiKeyPage
  nsDialogs::Create 1018
  Pop $Dialog
  ${If} $Dialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 24u "Groq API Key"
  Pop $ApiKeyLabel

  ${NSD_CreateLabel} 0 26u 100% 20u "Get your free key at console.groq.com"
  Pop $ApiKeyHint

  ${NSD_CreatePassword} 0 50u 100% 14u ""
  Pop $ApiKeyInput

  nsDialogs::Show
FunctionEnd

Function ApiKeyPageLeave
  ${NSD_GetText} $ApiKeyInput $ApiKeyValue

  ${If} $ApiKeyValue == ""
    MessageBox MB_OK "Please enter your Groq API key to continue."
    Abort
  ${EndIf}

  StrCpy $0 $ApiKeyValue 4
  ${If} $0 != "gsk_"
    MessageBox MB_YESNO "This key doesn't look valid (should start with gsk_). Continue anyway?" IDYES +2
    Abort
  ${EndIf}
FunctionEnd

Section "WriteEnv"
  CreateDirectory "$APPDATA\Primnox"
  FileOpen $0 "$APPDATA\Primnox\.env" w
  FileWrite $0 "GROQ_API_KEY=$ApiKeyValue$\r$\n"
  FileWrite $0 "APP_VERSION=0.0.2-alpha$\r$\n"
  FileClose $0
SectionEnd
