\
import asyncio
import csv
import io
import math
import re
from typing import Iterable, List, Tuple

# Basic BTC address validation: Base58 (1,3), Bech32 (bc1, tb1), P2TR (bc1p...), etc.
_BASE58_RE = re.compile(r'^[123][a-km-zA-HJ-NP-Z1-9]{25,34}$')
_BECH32_RE = re.compile(r'^(bc1|tb1)[0-9ac-hj-np-z]{25,83}$')

def is_probable_btc_address(addr: str) -> bool:
    if not addr: return False
    a = addr.strip()
    if _BASE58_RE.match(a): return True
    if _BECH32_RE.match(a): return True
    return False

def chunked(seq: List, n: int) -> Iterable[List]:
    """Yield successive n-sized chunks from seq."""
    for i in range(0, len(seq), n):
        yield seq[i: i+n]

def format_btc(sats: int) -> str:
    return f"{sats / 1e8:.8f}"

def to_csv_bytes(rows: List[Tuple[int, str, int]]) -> bytes:
    # rows: (rank, address, balance_sats)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["rank", "address", "balance_btc"])
    for r, a, s in rows:
        writer.writerow([r, a, f"{s/1e8:.8f}"])
    return buf.getvalue().encode("utf-8")
