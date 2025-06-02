#!/bin/bash

echo "📦 Activating Python virtual environment..."
source unified_env/Scripts/activate || { echo "❌ Failed to activate virtual environment"; exit 1; }

echo "📂 Moving to Rasa directory..."
cd rasa || { echo "❌ Failed to change to Rasa directory"; exit 1; }

echo "🚀 Starting Rasa Action Server..."
rasa run actions &

echo "⏳ Waiting 5 seconds for action server to boot..."
sleep 5

echo "🤖 Starting Rasa Core/NLU Server..."
rasa run --enable-api --cors "*" --port 5005 &

echo "📂 Returning to root directory..."
cd ..

echo "📂 Moving to backend directory..."
cd backend || { echo "❌ Failed to change to backend directory"; exit 1; }

echo "🌐 Starting FastAPI backend..."
uvicorn main:app --host 0.0.0.0 --port 8000




