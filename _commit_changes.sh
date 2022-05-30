#!/bin/bash

echo Please enter the message for the commit: 

read msg

git add .
git commit -m $msg
git push origin development