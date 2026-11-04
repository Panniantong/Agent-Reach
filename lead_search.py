#!/usr/bin/env python3
"""
CLI Lead Search & Auto-Save Tool for Agent Reach.
Usage:
  lead-search "dentist" --location "Mumbai" --limit 10
  lead-search "cake sellers" --location "Kolkata" --platform linkedin
"""

import argparse
import sys

sys.path.insert(0, "/Agent-Reach")
from lead_saver import get_leads_by_search_id, get_search_history, run_lead_search


def print_table(leads):
    if not leads:
        print("\nNo leads found.\n")
        return

    # Print formatted output
    print("\n" + "="*95)
    print(f"{'#':<3} | {'NAME':<18} | {'BUSINESS':<22} | {'PHONE / WHATSAPP':<18} | {'EMAIL'}")
    print("="*95)
    
    for i, lead in enumerate(leads, 1):
        name = (lead.get('name') or 'N/A')[:18]
        biz = (lead.get('business') or lead.get('role') or 'N/A')[:22]
        phone = (lead.get('phone') or 'Not listed')[:18]
        email = (lead.get('email') or 'Not listed')[:25]
        print(f"{i:<3} | {name:<18} | {biz:<22} | {phone:<18} | {email}")
        
    print("="*95 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Agent Reach Lead Finder with Automatic Saving & Contact Discovery")
    parser.add_argument("query", nargs="?", help="Lead search query (e.g. 'dentist', 'cake sellers', 'SaaS founders')")
    parser.add_argument("--location", "-l", default="", help="City, state, or country (e.g. 'Kolkata', 'New York')")
    parser.add_argument("--platform", "-p", default="linkedin", choices=["linkedin", "twitter", "reddit", "web"], help="Target platform (default: linkedin)")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Max results to fetch (default: 10)")
    parser.add_argument("--history", action="store_true", help="View past searches")
    parser.add_argument("--view", type=int, metavar="SEARCH_ID", help="View leads from a past search ID")

    args = parser.parse_args()

    if args.history:
        history = get_search_history()
        if not history:
            print("No saved searches found yet.")
            return
        print("\n--- Saved Searches History ---")
        for s in history:
            print(f"[{s['id']}] {s['created_at']} | Query: '{s['query']}' | Loc: '{s['location'] or 'Any'}' | Leads: {s['lead_count']} | CSV: {s['csv_path']}")
        print()
        return

    if args.view:
        leads = get_leads_by_search_id(args.view)
        print(f"\nDisplaying {len(leads)} leads for Search ID #{args.view}:")
        print_table(leads)
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    print(f"\n[*] Searching for '{args.query}' in '{args.location or 'any location'}' on {args.platform.upper()}...")
    print("[*] Contact columns (phone/email) and auto-saving enabled...")
    
    result = run_lead_search(
        query=args.query,
        location=args.location,
        platform=args.platform,
        limit=args.limit
    )

    if not result.get("ok"):
        print(f"\n[!] Error: {result.get('error')}\n")
        sys.exit(1)

    leads = result.get("leads", [])
    print_table(leads)
    
    saved = result.get("saved_files", {})
    print("[✓] Leads automatically saved:")
    print(f"    - CSV:  {saved.get('csv_path')}")
    print(f"    - JSON: {saved.get('json_path')}")
    print(f"    - Latest: {saved.get('latest_csv')}\n")

if __name__ == "__main__":
    main()
