"""
TestPilot WebSocket — Simplified
==================================
Minimal WebSocket support. No Redis dependency.
"""

from __future__ import annotations
import json
import asyncio
import logging
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("testpilot.websocket")
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self):
        self._rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, room: str):
        await ws.accept()
        self._rooms.setdefault(room, set()).add(ws)

    async def disconnect(self, ws: WebSocket, room: str):
        if room in self._rooms:
            self._rooms[room].discard(ws)
            if not self._rooms[room]:
                del self._rooms[room]

    async def broadcast(self, room: str, event: str, data: dict):
        conns = set(self._rooms.get(room, set()))
        msg = json.dumps({"event": event, "data": data})
        for ws in conns:
            try:
                await ws.send_text(msg)
            except Exception:
                self._rooms.get(room, set()).discard(ws)


manager = ConnectionManager()


async def start_redis_listener():
    """No-op — Redis removed."""
    pass

async def stop_redis_listener():
    """No-op — Redis removed."""
    pass