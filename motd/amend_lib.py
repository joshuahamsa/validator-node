#!/usr/bin/env python3
"""Shared data layer for the amend CLI and metrics_server."""
import html.parser
import json
import re
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

RIPPLED = "/usr/local/bin/rippled"
RIPPLED_ADMIN_RPC = "127.0.0.1:5006"
RIPPLED_CFG = "/etc/opt/ripple/rippled.cfg"
WALLET_DB = "/var/lib/rippled/db/wallet.db"
SESSION_FILE = "/tmp/amend-session.json"
XRPL_AMENDMENTS_URL = "https://xrpl.org/known-amendments.html"


def get_live_features() -> dict:
    """Call `sudo rippled --rpc_ip feature` and return features dict keyed by hash.

    Using the admin RPC port returns the complete vetoed field (true/false/Obsolete)
    which is the authoritative synthesized view of wallet.db + rippled.cfg votes.
    """
    raw = subprocess.check_output(
        ["sudo", RIPPLED, f"--rpc_ip={RIPPLED_ADMIN_RPC}", "feature"],
        timeout=10, text=True, stderr=subprocess.DEVNULL,
    )
    return json.loads(raw)["result"]["features"]


def get_wallet_votes(wallet_db: str = WALLET_DB) -> dict:
    """Read amendment vote preferences from wallet.db → {hash_upper: 'yes'|'no'}.

    rippled's `feature` RPC omits the `vetoed` field for non-vetoed amendments
    instead of returning false, so wallet.db is the authoritative source for
    explicit yes votes. Later rows win on hash collision (highest rowid).
    """
    try:
        con = sqlite3.connect(f"file:{wallet_db}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT AmendmentHash, Veto FROM FeatureVotes ORDER BY rowid"
        ).fetchall()
        return {h.upper(): ("no" if v else "yes") for h, v in rows}
    except Exception:
        return {}


def compute_working_set(features: dict) -> list:
    """Return all pending (not yet enabled, not obsolete) amendments.

    Uses the `vetoed` field from the admin RPC as the authoritative vote:
    - vetoed: true  → node votes NO
    - vetoed: false → node votes YES
    - vetoed: "Obsolete" → skip

    Sorted: majority amendments first, then alphabetical by name.
    """
    result = []
    for hash_, data in features.items():
        if data.get("enabled"):
            continue
        if data.get("vetoed") == "Obsolete":
            continue
        name = data.get("name", "")
        your_vote = "no" if data.get("vetoed") is True else "yes"
        result.append({
            "hash": hash_,
            "name": name,
            "your_vote": your_vote,
            "majority": "majority" in data,
            "supported": data.get("supported", False),
            "description": "",
        })
    result.sort(key=lambda x: (not x["majority"], x["name"]))
    return result


def _remove_hash_from_sections(cfg_text: str, hash_: str) -> str:
    """Remove hash from [amendments] and [veto_amendments] sections."""
    current_section = None
    result = []
    for line in cfg_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            current_section = stripped.strip("[]")
        if current_section in ("amendments", "veto_amendments") and stripped == hash_:
            continue
        result.append(line)
    return "".join(result)


def _add_hash_to_section(cfg_text: str, hash_: str, section: str) -> str:
    """Add hash as first entry under [section], creating section if absent."""
    header = f"[{section}]"
    lines = cfg_text.splitlines(keepends=True)
    result = []
    added = False
    for line in lines:
        result.append(line)
        if line.strip() == header and not added:
            result.append(hash_ + "\n")
            added = True
    if not added:
        if result and not result[-1].endswith("\n"):
            result.append("\n")
        result.append(f"\n{header}\n{hash_}\n")
    return "".join(result)


def update_cfg_text(cfg_text: str, hash_: str, vote: str) -> str:
    """Return updated cfg text with hash voted explicitly. Pure — no side effects."""
    cleaned = _remove_hash_from_sections(cfg_text, hash_)
    target = "amendments" if vote == "yes" else "veto_amendments"
    return _add_hash_to_section(cleaned, hash_, target)


def write_cfg_vote(hash_: str, vote: str) -> None:
    """Backup cfg, then write a single amendment vote. Requires sudo."""
    cfg_text = subprocess.check_output(
        ["sudo", "cat", RIPPLED_CFG], text=True, stderr=subprocess.DEVNULL,
    )
    new_cfg = update_cfg_text(cfg_text, hash_, vote)
    subprocess.run(
        ["sudo", "cp", RIPPLED_CFG, RIPPLED_CFG + ".bak"], check=True,
    )
    proc = subprocess.run(
        ["sudo", "tee", RIPPLED_CFG],
        input=new_cfg, text=True, capture_output=True,
    )
    proc.check_returncode()


def save_session(amendments: list, path: str = SESSION_FILE) -> None:
    """Save current in-memory votes to a JSON temp file for later resumption."""
    data = [{"hash": a["hash"], "name": a["name"], "vote": a["your_vote"]}
            for a in amendments]
    Path(path).write_text(json.dumps(data, indent=2))


def load_session(path: str = SESSION_FILE) -> list:
    """Load saved session votes. Returns [] if file absent or invalid."""
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return []


class _AmendmentDescriptionParser(html.parser.HTMLParser):
    """Scrape amendment name → first paragraph description from xrpl.org."""

    def __init__(self):
        super().__init__()
        self._descriptions: dict = {}
        self._current_name: str | None = None
        self._in_h2 = False
        self._in_p = False
        self._h2_buf = ""
        self._p_buf = ""

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self._in_h2 = True
            self._h2_buf = ""
            self._current_name = None
        elif tag == "p" and self._current_name and self._current_name not in self._descriptions:
            self._in_p = True
            self._p_buf = ""

    def handle_endtag(self, tag):
        if tag == "h2":
            self._in_h2 = False
            name = self._h2_buf.strip()
            if name:
                self._current_name = name
        elif tag == "p" and self._in_p:
            self._in_p = False
            text = self._p_buf.strip()
            if self._current_name and text:
                self._descriptions[self._current_name] = text

    def handle_data(self, data):
        if self._in_h2:
            self._h2_buf += data
        elif self._in_p:
            self._p_buf += data

    def get_descriptions(self) -> dict:
        return self._descriptions


def fetch_amendment_descriptions() -> dict:
    """Fetch xrpl.org Known Amendments page and return {name: description}. Returns {} on error."""
    try:
        req = urllib.request.Request(
            XRPL_AMENDMENTS_URL,
            headers={"User-Agent": "amend-cli/1.0 (XRPL validator tool)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html_text = resp.read().decode("utf-8")
        parser = _AmendmentDescriptionParser()
        parser.feed(html_text)
        return parser.get_descriptions()
    except Exception:
        return {}
