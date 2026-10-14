@echo off
rem Release assinado so com a chave no ambiente (LUMIVOX_KEYSTORE_PATH etc.); ela nao esta no Git.
if defined LUMIVOX_KEYSTORE_PATH (
  gradle :app:assembleDebug :app:assembleRelease --stacktrace
) else (
  echo LUMIVOX_KEYSTORE_PATH ausente: gerando apenas o APK debug.
  gradle :app:assembleDebug --stacktrace
)
mkdir dist 2>nul
copy app\build\outputs\apk\debug\*.apk dist\Lumivox-Android-debug.apk
if defined LUMIVOX_KEYSTORE_PATH copy app\build\outputs\apk\release\*.apk dist\Lumivox-Android-release-assinado.apk
echo APKs gerados em .\dist
