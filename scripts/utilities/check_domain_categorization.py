#!/usr/bin/env python3
"""
Domain Categorization Checker via TrustedSource.org
Checks domains against Skyhigh SWG (formerly McAfee Web Gateway) categorization.
For authorized red team use only.

Usage:
    source /tmp/domain_check_venv/bin/activate
    python3 scripts/utilities/check_domain_categorization.py
"""

import requests
import time
import random
import csv
import sys
import argparse
from datetime import datetime
from bs4 import BeautifulSoup

# --- Configuration ---
TRUSTEDSOURCE_URL = "https://trustedsource.org/en/feedback/url"
OUTPUT_FILE = "domain_categorization_results.csv"

MIN_DELAY = 5
MAX_DELAY = 15

# Product: Skyhigh SWG On-Prem (formerly McAfee Web Gateway)
SELECTED_PRODUCT = "03-xl"

# Target category to highlight
TARGET_CATEGORY = "finance"

DOMAINS = [
    "utrefinance.com",
    "ndrefinance.com",
    "jrefinance.com",
    "dhabifinance.com",
    "frefinance.com",
    "desotorefinance.com",
    "argylerefinance.com",
    "lancasterrefinance.com",
    "smplfinance.com",
    "wrefinance.com",
    "indianfinancer.com",
    "mynetfinance.com",
    "fleecefinance.com",
    "skfinancehk.com",
    "financi-all.com",
    "cedarhillrefinance.com",
    "rockwallrefinance.com",
    "ecafinancesolutions.com",
    "optimize-finance.com",
    "southlakerefinance.com",
    "oaklawnrefinance.com",
    "waxahachierefinance.com",
    "tedfinances.com",
    "oz-finance.com",
    "financeyourcaravan.com",
    "colleyvillerefinance.com",
    "expatriatesfinance.com",
    "financialradius.com",
    "yourfinancingportal.com",
    "mygfinancial.com",
    "financialspanish.com",
    "littleelmrefinance.com",
    "financial-synergy.com",
    "eurodrivefinance.com",
    "grandprairierefinance.com",
    "financesaude.com",
    "pasitosfinancial.com",
    "thecolonyrefinance.com",
    "fh-financial.com",
    "noble-finance.com",
    "highlandvillagerefinance.com",
    "opencoastfinancial.com",
    "justfinancehub.com",
    "mjseguridadfinanciera.com",
    "btgfinancials.com",
    "midamfinancial.com",
    "flowermoundrefinance.com",
    "financialliteracyhelp.com",
    "perdiemfinancial.com",
    "financemaximizer.com",
    "eastwakefinance.com",
    "shbfinancialservices.com",
    "thefinancialsimpleton.com",
    "financialplannerwestdesmoines.com",
    "dailyfinancedigest.com",
    "battenfeldfinancial.com",
    "jsmfinancialsvcs.com",
    "trustedfinancialbrokers.com",
    "domestic-financial.com",
    "housatonicfinancial.com",
    "financialbusinesscenter.com",
    "financeiraoficial.com",
    "degenerationfinance.com",
    "richlandhillsrefinance.com",
    "targetfinancegroup.com",
    "farmersbranchrefinance.com",
    "lwrfinancialplanner.com",
    "universityparkrefinance.com",
    "financialstudent.com",
    "northrichlandhillsrefinance.com",
    "efinancialloan.com",
    "lwrfinancialplanners.com",
    "defibusinessfinance.com",
    "equipmentfinanceagreement.com",
    "bfffinancialadvisors.com",
    "manmohanfinances.com",
    "defibusinessfinancing.com",
    "financialfinetune.com",
    "puritanfinancialcommunity.com",
    "haxofinances.com",
    "financeforhippies.com",
    "financialachievements.com",
    "apexpersonalfinance.com",
    "optionsfinancialgroup.com",
    "modfinancialagents.com",
    "financialventures.org",
    "mundofinancierocr.com",
    "mailifefinancial.com",
    "libertyfinancecoaching.com",
    "simpletruckfinance.com",
    "socialfinancebank.com",
    "financeclubs.org",
    "summumfinances.com",
    "funk-financial.com",
    "jdmcapitalfinance.com",
    "unmatchedfinancialsolutions.com",
    "financesectorinfo.com",
    "lkfinancialcoaching.com",
    "modernfinancialmanagement.com",
    "itfinancialcareers.com",
    "builderfinanceteam.com",
    "scorefactorfinancial.com",
    "sellerfinancepros.com",
    "financial-of.com",
    "alternativefinancellc.com",
    "amturstfinancial.com",
    "ownerfinanceconsultants.com",
    "credithelpfinancial.com",
    "financialbeginningslms.com",
    "ahlakerfinancial.com",
    "lolcdevelopmentfinance.com",
    "medfinance.io",
    "financieraalemana.net",
    "rafinancialplanning.com",
    "fleegelfinancial.com",
    "chicagoautofinancial.com",
    "insightfinancialnetwork.com",
    "embracingfinancialindependence.com",
    "financialfreedomcoaches.com",
    "marijuanabusinessfinancing.com",
    "financialadviseronline.com",
    "ssgincfinancial.com",
    "duvisonfinancieros.com",
    "betterhalfdivorcefinancial.com",
    "financeyourequipment.net",
    "goldtouchfinancial.com",
    "paragonmedicalfinances.com",
    "moneybuilderfinancial.com",
    "placementfinancier.net",
    "marketgardenfinancial.com",
    "owneruserfinancing.com",
    "jvfinancial.net",
    "magnoliafinancial.net",
    "financialmedianetworks.com",
    "financetrades.net",
    "klimbfinancial.net",
    "dentalfinance.io",
    "strategicfinancialanalysis.net",
    "actualidadfinanciera.info",
    "jdmcapitalfinance.net",
    "financialnetworkmedia.com",
    "lovelifefinancials.com",
    "financialcontentsecrets.com",
    "bfffinancial.info",
    "klimbfinancial.info",
    "upfinancial.net",
    "emeraldfinancial.biz",
    "bfffinancial.tv",
    "klimbfinancial.co",
    "thefinancials.co",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": TRUSTEDSOURCE_URL,
}


def get_session_and_tokens():
    """Create session and extract hidden form fields (CSRF tokens, etc.)."""
    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(TRUSTEDSOURCE_URL, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form", {"action": "/en/feedback/url"})
    hidden_fields = {}
    if form:
        for inp in form.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            value = inp.get("value", "")
            if name:
                hidden_fields[name] = value

    return session, hidden_fields


def check_domain(session, domain, hidden_fields):
    """Submit domain to TrustedSource, parse categorization result."""
    form_data = {
        **hidden_fields,
        "product": SELECTED_PRODUCT,
        "url": f"https://{domain}",
    }

    try:
        resp = session.post(TRUSTEDSOURCE_URL, data=form_data, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"domain": domain, "status": f"ERROR: {e}", "category": "ERROR", "reputation": "ERROR"}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Result table has 5 cells: [checkbox] | URL | Status | Categorization | Reputation
    status = "Unknown"
    category = "Unknown"
    reputation = "Unknown"

    tables = soup.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            cell_texts = [c.get_text(strip=True) for c in cells]
            # TrustedSource truncates long URLs (e.g. "socialfinancebank ...")
            # Match on domain name without TLD to handle truncation
            domain_base = domain.split(".")[0]
            if len(cells) >= 4 and any(domain_base in t for t in cell_texts):
                for idx, t in enumerate(cell_texts):
                    if domain_base in t:
                        remaining = cell_texts[idx + 1:]
                        if len(remaining) >= 3:
                            status = remaining[0]
                            category = remaining[1].lstrip("- ") if remaining[1] else "Uncategorized"
                            reputation = remaining[2]
                        elif len(remaining) >= 2:
                            status = remaining[0]
                            category = remaining[1].lstrip("- ") if remaining[1] else "Uncategorized"
                        elif len(remaining) >= 1:
                            status = remaining[0]
                        break
                break

    # Update hidden fields from the response for next request (tokens may rotate)
    form = soup.find("form", {"action": "/en/feedback/url"})
    if form:
        for inp in form.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            value = inp.get("value", "")
            if name:
                hidden_fields[name] = value

    return {"domain": domain, "status": status, "category": category, "reputation": reputation}


def load_domains_from_csv(csv_path):
    """Load domain names from a GoDaddy auctions CSV export."""
    domains = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = row.get("Domain Name", "").strip()
            if domain:
                domains.append(domain)
    return domains


def main():
    parser = argparse.ArgumentParser(description="Check domain categorization on TrustedSource")
    parser.add_argument("--csv", help="Path to GoDaddy auctions CSV file to load domains from")
    parser.add_argument("--target", default=TARGET_CATEGORY,
                        help=f"Target category to highlight (default: {TARGET_CATEGORY})")
    args = parser.parse_args()

    # Load domains from CSV or use built-in list
    domains = load_domains_from_csv(args.csv) if args.csv else DOMAINS
    target = args.target.lower()

    print(f"{'='*70}")
    print(f"  TrustedSource Domain Categorization Checker")
    print(f"  Product: Skyhigh SWG On-Prem (McAfee Web Gateway)")
    print(f"  Domains: {len(domains)}")
    print(f"  Target category: {target}")
    print(f"  Delay: {MIN_DELAY}-{MAX_DELAY}s between requests")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    print("[*] Initializing session...")
    try:
        session, hidden_fields = get_session_and_tokens()
        print(f"[+] Session ready.\n")
    except Exception as e:
        print(f"[!] Failed to connect: {e}")
        sys.exit(1)

    results = []
    finance_hits = []
    other_categorized = []
    uncategorized = []
    errors = []

    for i, domain in enumerate(domains, 1):
        print(f"[{i:3d}/{len(domains)}] {domain:45s}", end="", flush=True)

        result = check_domain(session, domain, hidden_fields)
        results.append(result)

        cat = result["category"]
        rep = result["reputation"]
        status = result["status"]

        if "ERROR" in cat:
            marker = "!!"
            errors.append(result)
        elif cat in ("Uncategorized", "Unknown", "N/A", ""):
            marker = "--"
            uncategorized.append(result)
        elif target in cat.lower():
            marker = "$$"
            finance_hits.append(result)
        else:
            marker = ">>"
            other_categorized.append(result)

        print(f" [{marker}] {status:25s} | {cat:25s} | {rep}")

        if marker == "$$":
            print(f"      *** FINANCE/BANKING HIT — BUY THIS ONE ***")
        elif marker == ">>":
            print(f"      ^^^ categorized (not finance)")

        # Write results incrementally so we don't lose data on crash
        if i % 10 == 0:
            with open(OUTPUT_FILE, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["domain", "status", "category", "reputation"])
                writer.writeheader()
                writer.writerows(results)

        # Delay between requests
        if i < len(domains):
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            time.sleep(delay)

            # Refresh session every 25 requests
            if i % 25 == 0:
                print(f"\n[*] Refreshing session (after {i} requests)...")
                try:
                    session, hidden_fields = get_session_and_tokens()
                    print("[+] Session refreshed.\n")
                except Exception as e:
                    print(f"[!] Refresh failed: {e}, continuing...\n")

    # Final CSV write
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["domain", "status", "category", "reputation"])
        writer.writeheader()
        writer.writerows(results)

    # Summary
    print(f"\n{'='*70}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*70}")
    print(f"  Total checked:  {len(results)}")
    print(f"  FINANCE HITS:   {len(finance_hits)}")
    print(f"  Other category: {len(other_categorized)}")
    print(f"  Uncategorized:  {len(uncategorized)}")
    print(f"  Errors:         {len(errors)}")
    print(f"  CSV saved to:   {OUTPUT_FILE}")

    if finance_hits:
        print(f"\n  *** FINANCE/BANKING DOMAINS — TOP CANDIDATES ***")
        print(f"  {'─'*60}")
        for d in finance_hits:
            print(f"    {d['domain']:45s} {d['category']:25s} {d['reputation']}")

    if other_categorized:
        print(f"\n  OTHER CATEGORIZED DOMAINS:")
        print(f"  {'─'*60}")
        for d in other_categorized:
            print(f"    {d['domain']:45s} {d['category']:25s} {d['reputation']}")

    print(f"\n  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
