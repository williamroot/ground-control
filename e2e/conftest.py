"""Fixtures Playwright. Um browser por sessão; um context/page por teste.

Usa o Chromium do host via executable_path (config.CHROMIUM_PATH) porque o
Playwright não publica build para ubuntu26.04. Em CI com browser baixado,
exporte GC_CHROMIUM_PATH="" para usar o bundled.
"""
import pytest
from playwright.sync_api import sync_playwright

from config import CHROMIUM_PATH


@pytest.fixture(scope="session")
def _pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(_pw):
    kwargs = {"args": ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]}
    if CHROMIUM_PATH:
        kwargs["executable_path"] = CHROMIUM_PATH
    b = _pw.chromium.launch(**kwargs)
    yield b
    b.close()


@pytest.fixture
def context(browser):
    ctx = browser.new_context(viewport={"width": 1366, "height": 900})
    yield ctx
    ctx.close()


@pytest.fixture
def page(context):
    pg = context.new_page()
    pg.set_default_timeout(30000)
    return pg
