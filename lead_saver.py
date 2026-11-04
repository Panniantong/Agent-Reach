#!/usr/bin/env python3
"""
Lead Saver & Extraction Engine for Agent Reach.
Builds on top of Agent Reach to automate saving, contact extraction, and persistence.
Includes seamless zero-config fallback when upstream free APIs hit rate limits.
"""

import csv
import json
import os
import re
import sqlite3
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape
from typing import Any, Dict, List

DB_PATH = "/Agent-Reach/data/leads.db"
SAVED_DIR = "/Agent-Reach/saved_searches"

# Regex patterns for contact discovery
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(
    r'(?:(?:\+91|91|0)?[ -]?[6-9]\d{9})|'  # India mobile numbers
    r'(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})|'  # US/Canada numbers
    r'(?:\+\d{1,3}[- ]?)?\d{4,5}[- ]?\d{4,6}'  # International general
)

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(SAVED_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                location TEXT,
                platform TEXT,
                lead_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                csv_path TEXT,
                json_path TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id INTEGER,
                name TEXT,
                business TEXT,
                role TEXT,
                phone TEXT,
                email TEXT,
                location TEXT,
                url TEXT,
                snippet TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (search_id) REFERENCES searches(id)
            )
        """)
        conn.commit()

def extract_contacts(text: str) -> Dict[str, List[str]]:
    emails = list(set(EMAIL_REGEX.findall(text)))
    emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.webp', '.svg'))]
    
    raw_phones = PHONE_REGEX.findall(text)
    phones = []
    for match in raw_phones:
        if isinstance(match, tuple):
            p = ''.join(match).strip()
        else:
            p = str(match).strip()
        # Filter out obvious false positives like activity IDs or long digit strings
        digits = re.sub(r'\D', '', p)
        if 10 <= len(digits) <= 14 and f"activity-{p}" not in text:
            phones.append(p)
    return {
        "emails": emails,
        "phones": list(set(phones))
    }

def clean_lead_name_and_role(title: str) -> tuple[str, str, str]:
    """Parse name, role, and business from search result title."""
    # Strip common site titles
    clean = re.sub(r'\s*[-|]\s*(?:LinkedIn|Twitter|X|Facebook|Instagram).*$', '', title, flags=re.I).strip()
    
    parts = re.split(r'\s*[-|–]\s*', clean, maxsplit=2)
    name = parts[0].strip()
    role = parts[1].strip() if len(parts) > 1 else ""
    business = parts[2].strip() if len(parts) > 2 else ""

    if not business and " at " in role:
        r_parts = role.split(" at ", 1)
        role = r_parts[0].strip()
        business = r_parts[1].strip()
    elif not business and " of " in role:
        r_parts = role.split(" of ", 1)
        role = r_parts[0].strip()
        business = r_parts[1].strip()
        
    return name, role, business

def parse_lead_from_item(item: Dict[str, Any], default_location: str = "") -> Dict[str, Any]:
    raw_title = item.get("title", "")
    url = item.get("url", "")
    raw_text = item.get("text", "")
    
    name, role, business = clean_lead_name_and_role(raw_title)
    location = default_location
    
    # Try reading snippet lines for location or extra role info
    lines = [ln.strip() for ln in raw_text.split("\n") if ln.strip() and not ln.startswith("#")]
    for line in lines[:3]:
        if any(term in line.lower() for term in ["india", "kolkata", "mumbai", "delhi", "bangalore", "miami", "new york", "london", "ca", "fl", "tx"]):
            location = line
            break
            
    contacts = extract_contacts(raw_text)
    phone_str = " / ".join(contacts["phones"]) if contacts["phones"] else ""
    email_str = " / ".join(contacts["emails"]) if contacts["emails"] else ""
    
    return {
        "name": name,
        "business": business,
        "role": role,
        "phone": phone_str,
        "email": email_str,
        "location": location,
        "url": url,
        "snippet": raw_text[:400].replace("\n", " ")
    }

def search_fallback_engine(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Resilient direct search fallback when upstream Exa API hits free rate limits."""
    items = []
    offset = 1
    page = 1
    
    while len(items) < limit and page <= 3:
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}&b={offset}&pz=7"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        })
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
        except Exception:
            break
            
        pattern = re.compile(
            r'/RU=(https%3a%2f%2f[^\"]+?)/RK=[^>]*>.*?<h3[^>]*class=\"[^\"]*title[^\"]*\"[^>]*>(?:<span[^>]*>)?(.*?)(?:</span>)?</h3>(?:.*?<div class=\"compText[^\"]*\">(?:<p[^>]*>)?(.*?)(?:</p>)?</div>)?',
            re.DOTALL
        )
        matches = pattern.findall(html)
        if not matches:
            break
            
        for ru, raw_title, raw_snippet in matches:
            u = urllib.parse.unquote(ru)
            if any(bad in u for bad in ['yahoo.com', 'bing.com', 'aclick', 'doubleclick', 'ad_type']):
                continue
                
            title = unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()
            snippet = unescape(re.sub(r'<[^>]+>', '', raw_snippet)).strip() if raw_snippet else ''
            
            if not any(it['url'] == u for it in items):
                items.append({'title': title, 'url': u, 'text': snippet})
            if len(items) >= limit:
                break
                
        offset += 7
        page += 1
        
    return items

def run_lead_search(query: str, location: str = "", platform: str = "linkedin", limit: int = 10) -> Dict[str, Any]:
    init_db()
    
    # Construct search query
    if platform == "linkedin":
        dork_parts = ['site:linkedin.com/in/']
        if query:
            dork_parts.append(f'("{query}")')
        if location:
            dork_parts.append(f'"{location}"')
        full_query = " ".join(dork_parts)
    elif platform == "twitter":
        dork_parts = ['site:x.com']
        if query:
            dork_parts.append(f'"{query}"')
        if location:
            dork_parts.append(f'"{location}"')
        full_query = " ".join(dork_parts)
    elif platform == "reddit":
        dork_parts = ['site:reddit.com']
        if query:
            dork_parts.append(f'"{query}"')
        if location:
            dork_parts.append(f'"{location}"')
        full_query = " ".join(dork_parts)
    else:
        full_query = f"{query} {location}".strip()
        
    raw_items = []
    source = "agent-reach (exa)"
    
    # 1. Try primary backend (agent-reach web search)
    cmd = ["agent-reach", "web", "search", full_query, "--limit", str(limit)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        output = proc.stdout
        start_idx = output.find('{"schema_version"')
        if start_idx != -1:
            data = json.loads(output[start_idx:])
            if data.get("ok") and data.get("items"):
                raw_items = data.get("items", [])
    except Exception:
        raw_items = []

    # 2. Resilient fallback if agent-reach was rate-limited or failed
    if not raw_items:
        source = "web search engine fallback"
        raw_items = search_fallback_engine(full_query, limit=limit)

    if not raw_items:
        return {
            "ok": False,
            "error": "No results found. Try broadening the search terms or location.",
            "leads": []
        }

    leads = [parse_lead_from_item(item, default_location=location) for item in raw_items]

    # Save to files & SQLite
    saved_info = save_leads_to_storage(
        query=query,
        location=location,
        platform=platform,
        leads=leads
    )

    return {
        "ok": True,
        "query": query,
        "location": location,
        "platform": platform,
        "lead_count": len(leads),
        "source": source,
        "leads": leads,
        "saved_files": saved_info
    }

def save_leads_to_storage(query: str, location: str, platform: str, leads: List[Dict[str, Any]]) -> Dict[str, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_query = re.sub(r'[^a-zA-Z0-9_-]', '_', f"{query}_{location}").strip('_')[:40] or "leads"
    
    filename_csv = f"{clean_query}_{timestamp}.csv"
    filename_json = f"{clean_query}_{timestamp}.json"
    
    csv_path = os.path.join(SAVED_DIR, filename_csv)
    json_path = os.path.join(SAVED_DIR, filename_json)
    
    latest_csv = os.path.join(SAVED_DIR, "latest_leads.csv")
    latest_json = os.path.join(SAVED_DIR, "latest_leads.json")
    
    fieldnames = ['name', 'business', 'role', 'phone', 'email', 'location', 'url', 'snippet']
    
    # Write timestamped CSV & latest CSV
    for path in [csv_path, latest_csv]:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for lead in leads:
                row = {k: lead.get(k, '') for k in fieldnames}
                writer.writerow(row)
                
    # Write timestamped JSON & latest JSON
    for path in [json_path, latest_json]:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(leads, f, indent=2, ensure_ascii=False)

    # Save in SQLite DB
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO searches (query, location, platform, lead_count, csv_path, json_path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (query, location, platform, len(leads), csv_path, json_path))
        search_id = cursor.lastrowid
        
        for lead in leads:
            cursor.execute("""
                INSERT INTO leads (search_id, name, business, role, phone, email, location, url, snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                search_id,
                lead.get('name', ''),
                lead.get('business', ''),
                lead.get('role', ''),
                lead.get('phone', ''),
                lead.get('email', ''),
                lead.get('location', ''),
                lead.get('url', ''),
                lead.get('snippet', '')
            ))
        conn.commit()

    return {
        "csv_path": csv_path,
        "json_path": json_path,
        "latest_csv": latest_csv,
        "latest_json": latest_json
    }

def get_search_history() -> List[Dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM searches ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_leads_by_search_id(search_id: int) -> List[Dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE search_id = ? ORDER BY id ASC", (search_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
