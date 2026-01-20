#!/usr/bin/env python3
import csv
import json
import time
import re
from typing import Optional, Dict, Any, Tuple, List

import requests

# -------------------------------------------------------------------
# 1. Your book titles
# -------------------------------------------------------------------
TITLES = [
    "ANGEL DOWN",
    "AUGUST LANE",
    "BAT EATER AND OTHER NAMES FOR CORA ZENG",
    "BUCKEYE",
    "THE BUFFALO HUNTER HUNTER",
    "BURY OUR BONES IN THE MIDNIGHT SOIL",
    "THE COLONY",
    "DEATH TAKES ME",
    "THE DIRECTOR",
    "THE DOORMAN",
    "THE FEELING OF IRON",
    "FLESH",
    "A GENTLEMAN’S GENTLEMAN",
    "THE GOOD LIAR",
    "A GUARDIAN AND A THIEF",
    "HEART THE LOVER",
    "HEARTWOOD",
    "HOLLOW SPACES",
    "THE HOUNDING",
    "HOW TO DODGE A CANNONBALL",
    "ISOLA",
    "KATABASIS",
    "KILLING STELLA",
    "KING SORROW",
    "THE LONELINESS OF SONIA AND SUNNY",
    "LONELY CROWDS",
    "MAGGIE; OR, A MAN AND A WOMAN WALK INTO A BAR",
    "NIGHT WATCH",
    "ON THE CALCULATION OF VOLUME: Book III",
    "PERFECTION",
    "PLAYWORLD",
    "THE RAREST FRUIT",
    "THE REMEMBERED SOLDIER",
    "SHADOW TICKET",
    "SILVER ELITE",
    "THE SISTERS",
    "THE SLIP",
    "THE SOUTH",
    "STARTLEMENT",
    "STONE YARD DEVOTIONAL",
    "SUNRISE ON THE REAPING",
    "THESE SUMMER STORMS",
    "TO SMITHEREENS",
    "THE TOKYO SUITE",
    "TRIP",
    "VENETIAN VESPERS",
    "VICTORIAN PSYCHO",
    "WE DO NOT PART",
    "WHAT WE CAN KNOW",
    "A WITCH’S GUIDE TO MAGICAL INNKEEPING",
    "ABUNDANCE",
    "THE AGE OF CHOICE",
    "ALL CONSUMING",
    "APPLE IN CHINA",
    "THE ARROGANT APE",
    "AWAKE",
    "BALDWIN",
    "BEING JEWISH AFTER THE DESTRUCTION OF GAZA",
    "BLACK MOSES",
    "BOOK OF LIVES: A Memoir of Sorts",
    "BORN IN FLAMES",
    "THE BROKEN KING",
    "BUCKLEY",
    "THE CALL OF THE HONEYGUIDE",
    "CAPITALISM",
    "CARELESS PEOPLE",
    "CLAIRE McCARDELL",
    "THE CONTAINMENT",
    "CRUMB",
    "DARK RENAISSANCE",
    "DAUGHTERS OF THE BAMBOO GROVE",
    "EMPIRE OF AI",
    "EVERY DAY IS SUNDAY",
    "THE FATE OF THE DAY",
    "A FLOWER TRAVELED IN MY BLOOD",
    "GIRL ON GIRL",
    "THE GODS OF NEW YORK",
    "I SEEK A KIND PERSON",
    "JOHN & PAUL",
    "KING OF KINGS",
    "THE LAST MANAGER",
    "MARK TWAIN",
    "A MARRIAGE AT SEA",
    "MEMORIAL DAYS",
    "MOTHER EMANUEL",
    "MOTHERLAND",
    "MOTHER MARY COMES TO ME",
    "1929",
    "ONE DAY, EVERYONE WILL HAVE ALWAYS BEEN AGAINST THIS",
    "THE PEEPSHOW",
    "RAISING HARE",
    "SHATTERED DREAMS, INFINITE HOPE",
    "THE SPINACH KING",
    "THERE IS NO PLACE FOR US",
    "THINGS IN NATURE MERELY GROW",
    "THE TRAGEDY OF TRUE CRIME",
    "WE THE PEOPLE",
    "WHAT IS QUEER FOOD?",
    "WILD THING",
    "THE ZORG",
]

# -------------------------------------------------------------------
# 2. Helper functions
# -------------------------------------------------------------------


def extract_year_from_date(date_str: str) -> Optional[int]:
    """
    Google Books / Open Library published dates can be '2025', '2025-11-24', etc.
    Extract just the year if possible.
    """
    if not date_str:
        return None
    m = re.match(r"(\d{4})", date_str)
    if m:
        return int(m.group(1))
    return None


def pick_isbn(identifiers: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """
    Given Google Books industryIdentifiers list, pick ISBN-13 if available,
    otherwise ISBN-10 if available.
    Returns (isbn13, isbn10).
    """
    isbn13 = None
    isbn10 = None
    for ident in identifiers or []:
        t = ident.get("type", "")
        v = ident.get("identifier")
        if t == "ISBN_13" and v:
            isbn13 = v
        elif t == "ISBN_10" and v:
            isbn10 = v
    return isbn13, isbn10


def search_google_books(title: str, author: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Search Google Books by title (and optional author).
    Returns a dict with publisher, year, isbn_13, isbn_10, raw_source, or None.
    """
    base_url = "https://www.googleapis.com/books/v1/volumes"
    # Basic query: intitle:"Title"
    q = f'intitle:"{title}"'
    if author:
        q += f'+inauthor:"{author}"'

    params = {
        "q": q,
        "maxResults": 5,
        # You can set a key here if needed, but for small usage it's not required.
        # "key": "YOUR_API_KEY",
    }

    try:
        resp = requests.get(base_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[GoogleBooks] Error for title '{title}': {e}")
        return None

    items = data.get("items", [])
    if not items:
        return None

    # Naive best-match strategy: first item, but you can add smarter matching if needed.
    best = items[0]
    vi = best.get("volumeInfo", {}) or {}

    publisher = vi.get("publisher")
    published_date = vi.get("publishedDate")
    year = extract_year_from_date(published_date) if published_date else None
    identifiers = vi.get("industryIdentifiers", [])
    isbn13, isbn10 = pick_isbn(identifiers)

    return {
        "source": "google_books",
        "publisher": publisher,
        "year": year,
        "isbn_13": isbn13,
        "isbn_10": isbn10,
        "raw_published_date": published_date,
        "raw": vi,
    }


def search_open_library(title: str, author: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Search Open Library by title (and optional author).
    Returns a dict with publisher, year, isbn_13, isbn_10, raw_source, or None.
    """
    base_url = "https://openlibrary.org/search.json"
    params = {
        "title": title,
        "limit": 5,
    }
    if author:
        params["author"] = author

    try:
        resp = requests.get(base_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[OpenLibrary] Error for title '{title}': {e}")
        return None

    docs = data.get("docs", [])
    if not docs:
        return None

    best = docs[0]

    publishers = best.get("publisher", [])
    publisher = publishers[0] if publishers else None

    # first_publish_year is usually present
    year = best.get("first_publish_year")

    isbn13 = None
    isbn10 = None
    isbns = best.get("isbn", []) or []
    for code in isbns:
        if len(code) == 13 and not isbn13:
            isbn13 = code
        elif len(code) == 10 and not isbn10:
            isbn10 = code
        if isbn13 and isbn10:
            break

    return {
        "source": "open_library",
        "publisher": publisher,
        "year": year,
        "isbn_13": isbn13,
        "isbn_10": isbn10,
        "raw": best,
    }


def lookup_book(title: str, author: Optional[str] = None) -> Dict[str, Any]:
    """
    Try Google Books first, then Open Library.
    Returns a normalized dict suitable for CSV.
    """
    print(f"\nLooking up: {title}")
    result = search_google_books(title, author=author)
    time.sleep(0.2)  # be gentle

    if not result:
        result = search_open_library(title, author=author)
        time.sleep(0.2)

    if not result:
        return {
            "title": title,
            "author": author or "",
            "publisher": "",
            "year": "",
            "isbn_13": "",
            "isbn_10": "",
            "source": "NOT_FOUND",
        }

    return {
        "title": title,
        "author": author or "",
        "publisher": result.get("publisher") or "",
        "year": result.get("year") or "",
        "isbn_13": result.get("isbn_13") or "",
        "isbn_10": result.get("isbn_10") or "",
        "source": result.get("source", ""),
    }


# -------------------------------------------------------------------
# 3. Main script
# -------------------------------------------------------------------


def main():
    output_file = "books_metadata.csv"

    rows = []
    for title in TITLES:
        row = lookup_book(title)
        rows.append(row)

    fieldnames = [
        "title",
        "author",
        "publisher",
        "year",
        "isbn_13",
        "isbn_10",
        "source",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"\nDone. Wrote {len(rows)} rows to {output_file}")


if __name__ == "__main__":
    main()
