#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("browser_service")

app = FastAPI()

class BrowseRequest(BaseModel):
    url: str

class BrowseResponse(BaseModel):
    content: str
    error: str | None = None

@app.post("/browse", response_model=BrowseResponse)
async def browse_page(payload: BrowseRequest):
    logger.info(f"Browsing URL: {payload.url}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(payload.url, timeout=15000)
            content = await page.inner_text("body")
            await browser.close()
            return BrowseResponse(content=content)
    except Exception as e:
        logger.error(f"Error browsing {payload.url}: {e}")
        return BrowseResponse(content="", error=str(e))
