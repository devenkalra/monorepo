"""
Example: create a page and optionally attach it to the menu.

Usage:
  set DK_API_TOKEN=your_token_from_admin
  set DK_API_BASE=https://devenkalra.com/api   # optional
  python create_page.py

Or locally against Django:
  set DK_API_BASE=http://127.0.0.1:8001/api
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python create_page.py` from the scripts/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dkapi import ApiError, Client


def main() -> None:
    client = Client.from_env()
    if not client.token:
        raise SystemExit(
            "Set DK_API_TOKEN to a Django REST token "
            "(Admin → Authtoken → Tokens)."
        )

    page = client.pages.create(
        title="Sync by Steven Strogatz",
        slug="sync-by-steven-strogatz",
        category="Books",
        content="# Sync\n\nNotes on the book.",
        roles_with_access="",  # public
        render_as_html=False,
    )
    print("Created page:", page)

    # Optional: add a menu entry pointing at the new page
    # item = client.menu_items.create(
    #     title=page["title"],
    #     page=page["id"],
    #     order=0,
    #     show_in_menu=True,
    # )
    # print("Created menu item:", item)


if __name__ == "__main__":
    try:
        main()
    except ApiError as exc:
        raise SystemExit(f"API error: {exc}") from exc
