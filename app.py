"""
FacePoke API

Author: Julian Bilcke
Date: September 30, 2024
"""

import sys
import asyncio
from aiohttp import web, WSMsgType
import json
from json import JSONEncoder
import numpy as np
import uuid
import logging
import os
import signal
from typing import Dict, Any, List, Optional
import base64
import io

from PIL import Image

# by popular demand, let's add support for avif
import pillow_avif

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set asyncio logger to DEBUG level
#logging.getLogger("asyncio").setLevel(logging.INFO)

#logger.debug(f"Python version: {sys.version}")

# SIGSEGV handler
def SIGSEGV_signal_arises(signalNum, stack):
    logger.critical(f"{signalNum} : SIGSEGV arises")
    logger.critical(f"Stack trace: {stack}")

signal.signal(signal.SIGSEGV, SIGSEGV_signal_arises)

from loader import initialize_models
from engine import Engine, base64_data_uri_to_PIL_Image

# Global constants
DATA_ROOT = os.environ.get('DATA_ROOT', '/tmp/data')
MODELS_DIR = os.path.join(DATA_ROOT, "models")

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(NumpyEncoder, self).default(obj)

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    engine = request.app['engine']
    try:
        #logger.info("New WebSocket connection established")
        while True:
            msg = await ws.receive()

            if msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                #logger.warning(f"WebSocket connection closed: {msg.type}")
                break

            try:
                if msg.type == WSMsgType.BINARY:
                    res = await engine.load_image(msg.data)
                    json_res = json.dumps(res, cls=NumpyEncoder)
                    await ws.send_str(json_res)

                elif msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    webp_bytes = await engine.transform_image(data.get('uuid'), data.get('params'))
                    await ws.send_bytes(webp_bytes)

            except Exception as e:
                logger.error(f"Error in engine: {str(e)}")
                logger.exception("Full traceback:")
                await ws.send_json({"error": str(e)})

    except Exception as e:
        logger.error(f"Error in websocket_handler: {str(e)}")
        logger.exception("Full traceback:")
    return ws

async def index(request: web.Request) -> web.Response:
    """Serve the index.html file"""
    content = open(os.path.join(os.path.dirname(__file__), "public", "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def js_index(request: web.Request) -> web.Response:
    """Serve the index.js file"""
    content = open(os.path.join(os.path.dirname(__file__), "public", "index.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)

async def hf_logo(request: web.Request) -> web.Response:
    """Serve the hf-logo.svg file"""
    content = open(os.path.join(os.path.dirname(__file__), "public", "hf-logo.svg"), "r").read()
    return web.Response(content_type="image/svg+xml", text=content)

async def initialize_app() -> web.Application:
    """Initialize and configure the web application."""
    try:
        logger.info("Initializing application...")
        live_portrait = await initialize_models()

        logger.info("🚀 Creating Engine instance...")
        engine = Engine(live_portrait=live_portrait)
        logger.info("✅ Engine instance created.")

        app = web.Application()
        app['engine'] = engine

        # Configure routes
        app.router.add_get("/", index)
        app.router.add_get("/index.js", js_index)
        app.router.add_get("/hf-logo.svg", hf_logo)
        app.router.add_get("/ws", websocket_handler)

        logger.info("Application routes configured")

        return app
    except Exception as e:
        logger.error(f"🚨 Error during application initialization: {str(e)}")
        logger.exception("Full traceback:")
        raise

if __name__ == "__main__":
    try:
        logger.info("Starting FacePoke application")
        app = asyncio.run(initialize_app())
        logger.info("Application initialized, starting web server")
        web.run_app(app, host="127.0.0.1", port=7860)
    except Exception as e:
        logger.critical(f"🚨 FATAL: Failed to start the app: {str(e)}")
        logger.exception("Full traceback:")
