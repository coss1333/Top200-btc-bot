\
import asyncio
import os
from typing import List, Tuple, Dict, Set
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils import is_probable_btc_address

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))
MAX_PER_SOURCE = int(os.getenv("MAX_PER_SOURCE", "200"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RichListBot/1.0; +https://example.local)"
}

class SourceError(Exception):
    pass

# --- Balance fetcher (blockchain.info) ---
@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=10),
       retry=retry_if_exception_type(Exception))
async def fetch_balance_sats(client: httpx.AsyncClient, address: str) -> int:
    # Using blockchain.info rawaddr endpoint; returns final_balance in satoshis
    url = f"https://blockchain.info/rawaddr/{address}?cors=true"
    r = await client.get(url, timeout=HTTP_TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    data = r.json()
    return int(data.get("final_balance", 0))

# --- Address scrapers ---
async def _parse_addresses_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    addrs: List[str] = []
    # Generic: find links that look like address pages
    for a in soup.find_all("a", href=True):
        href = a["href"]
        txt = (a.text or "").strip()
        cand = None
        # Try derive address from href or text
        # common patterns: /btc/address/<addr>, /address/<addr>, ... or text equals address
        if "/address/" in href:
            cand = href.split("/address/")[-1].split("?")[0].split("#")[0]
        elif "/btc/address/" in href:
            cand = href.split("/btc/address/")[-1].split("?")[0].split("#")[0]
        elif "/bitcoin/address/" in href:
            cand = href.split("/bitcoin/address/")[-1].split("?")[0].split("#")[0]
        elif "/wallet/" in href:
            # some explorers use /wallet/<addr>
            cand = href.split("/wallet/")[-1].split("?")[0].split("#")[0]
        elif len(txt) >= 26:
            cand = txt

        if cand and is_probable_btc_address(cand):
            addrs.append(cand)

    # Keep order, unique
    seen: Set[str] = set()
    uniq: List[str] = []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6),
       retry=retry_if_exception_type(Exception))
async def get_blockchair_top() -> List[str]:
    # Try first 4 pages to reach ~200 (if available)
    base = "https://blockchair.com/bitcoin/richest-addresses"
    addrs: List[str] = []
    async with httpx.AsyncClient(headers=HEADERS) as client:
        for page in range(1, 5):
            url = f"{base}?page={page}" if page > 1 else base
            r = await client.get(url, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            chunk = await _parse_addresses_from_html(r.text)
            addrs.extend(chunk)
            if len(addrs) >= MAX_PER_SOURCE:
                break
    # Return first MAX_PER_SOURCE
    return addrs[:MAX_PER_SOURCE]

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6),
       retry=retry_if_exception_type(Exception))
async def get_btccom_top() -> List[str]:
    # BTC.com rich list pages
    addrs: List[str] = []
    async with httpx.AsyncClient(headers=HEADERS) as client:
        for page in range(1, 6):  # try first 5 pages
            url = f"https://btc.com/stats/rich-list?p={page}"
            r = await client.get(url, timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                continue
            chunk = await _parse_addresses_from_html(r.text)
            addrs.extend(chunk)
            if len(addrs) >= MAX_PER_SOURCE:
                break
    return addrs[:MAX_PER_SOURCE]

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6),
       retry=retry_if_exception_type(Exception))
async def get_bitinfocharts_top() -> List[str]:
    url = "https://bitinfocharts.com/top-100-richest-bitcoin-addresses.html"
    async with httpx.AsyncClient(headers=HEADERS) as client:
        r = await client.get(url, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        addrs = await _parse_addresses_from_html(r.text)
    return addrs[:MAX_PER_SOURCE]

async def collect_candidate_addresses() -> List[str]:
    # Gather from multiple sources concurrently
    tasks = [get_blockchair_top(), get_btccom_top(), get_bitinfocharts_top()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    collected: List[str] = []
    seen = set()
    for res in results:
        if isinstance(res, Exception):
            # Skip failed source
            continue
        for a in res:
            if a not in seen:
                seen.add(a)
                collected.append(a)
            if len(collected) >= 5_000:  # hard cap
                break
    return collected

async def build_rich_list(limit: int = 200) -> List[Tuple[str, int]]:
    """
    Returns list of tuples (address, balance_sats) sorted desc by balance.
    """
    candidates = await collect_candidate_addresses()
    # If we didn't get enough candidates, just proceed with what we have
    if not candidates:
        raise SourceError("Не удалось собрать кандидатов адресов из публичных источников.")
    # Fetch balances with concurrency and rate limiting
    balances: Dict[str, int] = {}

    async with httpx.AsyncClient(headers=HEADERS) as client:
        sem = asyncio.Semaphore(10)  # limit concurrency to be polite

        async def worker(addr: str):
            async with sem:
                try:
                    sats = await fetch_balance_sats(client, addr)
                    balances[addr] = sats
                except Exception:
                    # Skip on failure
                    pass

        await asyncio.gather(*(worker(a) for a in candidates))

    pairs: List[Tuple[str, int]] = [(a, s) for a, s in balances.items() if s > 0]
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs[:limit]
