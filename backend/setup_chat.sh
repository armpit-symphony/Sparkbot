#!/bin/bash
# Setup script for the chat backend

set -e

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -e .

echo "Creating database tables..."
python -c "
from app.core.db import engine
from app.models.chat.models import User, Room, RoomMember, Message, RoomInvite, MeetingArtifact
from sqlmodel import text

# Create all tables
User.metadata.create_all(engine)
Room.metadata.create_all(engine)
RoomMember.metadata.create_all(engine)
Message.metadata.create_all(engine)
RoomInvite.metadata.create_all(engine)
MeetingArtifact.metadata.create_all(engine)

print('Database tables created!')
"

echo "Testing imports..."
python -c "
from app.main import app
from app.api.routes.chat import users_router, rooms_router, messages_router, ws_router
print('All imports OK!')
"

echo "Setup complete!"
