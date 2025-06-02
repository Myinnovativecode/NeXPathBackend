#!/bin/bash
echo " Starting Rasa Action Server..."
cd Rasa || { echo " Failed to change to Rasa directory"; exit 1; }
rasa run actions &
sleep 5
echo " Starting Rasa Core/NLU Server..."
rasa run --enable-api --cors "*" --port 5005
