#!/bin/bash
echo "️ Starting FastAPI backend..."
cd backend || { echo " Failed to change to backend directory"; exit 1; }
uvicorn main:app --host 0.0.0.0 --port 10000




