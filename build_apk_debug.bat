@echo off
gradle :app:assembleDebug :app:assembleRelease --stacktrace
mkdir dist 2>nul
copy app\build\outputs\apk\debug\*.apk dist\Lumivox-Android-debug.apk
copy app\build\outputs\apk\release\*.apk dist\Lumivox-Android-release-assinado.apk
echo APKs gerados em .\dist
