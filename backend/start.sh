#!/bin/bash

# Install pip if not available
python3.11 -m ensurepip --upgrade
python3.11 -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Start FastAPI app using gunicorn + uvicorn worker
gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT






