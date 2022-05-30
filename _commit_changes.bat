@echo off

cd C:\Working\Development\EODMS\eodms-cli\git\eodms-cli

set /p msg=Please enter the message for the commit:

git add .
git commit -m "%msg%"
git push origin development