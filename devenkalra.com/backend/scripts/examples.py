"""
Quick smoke examples for each resource.

  set DK_API_TOKEN=...
  python examples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dkapi import ApiError, Client


def main() -> None:
    c = Client.from_env()
    if not c.token:
        raise SystemExit("Set DK_API_TOKEN first.")

    menu = c.menu.get()
    print("menu roots:", len(menu) if isinstance(menu, list) else menu)
    print("pages:", len(c.pages.list()))
    print("projects:", len(c.projects.list()))
    print("ideas:", len(c.ideas.list()))
    print("books:", len(c.books.list()))
    print("tracks:", len(c.tracks.list()))
    print("recipes:", len(c.recipes.list()))
    print("blog posts:", len(c.blog_posts.list()))


if __name__ == "__main__":
    try:
        main()
    except ApiError as exc:
        raise SystemExit(f"API error: {exc}") from exc
