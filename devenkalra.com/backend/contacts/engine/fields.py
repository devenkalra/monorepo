"""ClickUp custom fields the sync reads and writes, and the vocabulary shared across the engine."""
import re

# Internal key -> custom field name in the ClickUp Contacts list (matched case-insensitively).
FIELDS = {
    "google_id":     "Google ID",      # Short text  - people/c123...   (idempotency key)
    "google_link":   "Google Link",    # URL         - contacts.google.com link
    "google_hash":   "Google hash",    # Short text  - change detection
    "linkedin_url":  "LinkedIn URL",   # URL         - normalized profile URL (idempotency key)
    "linkedin_hash": "LinkedIn hash",  # Short text  - change detection
    "email":         "Email",          # Email       - primary email (optional)
    "emails":        "Emails",         # Short text  - all emails, comma separated
    "phones":        "Phones",         # Short text  - all phones, comma separated (E.164 when valid)
    "company":       "Company",        # Short text
    "title":         "Title",          # Short text
    "birthday":      "Birthday",       # Text ("03-14 (1985)") or Date - from Google
    "address":       "Address",        # Text        - from Google
    "website":       "Website",        # URL         - from Google
    "groups":        "Groups",         # Labels      - Google contact labels are ADDED, never removed
    "connected_on":  "Connected on",   # Date        - from LinkedIn
    "sources":       "Sources",        # Labels      - Google / LinkedIn / WhatsApp, never removed
    "last_li_msg":   "Last LinkedIn message",  # Date - latest message, from messages.csv
    "whatsapp":      "WhatsApp",       # Text        - WhatsApp number, E.164 (idempotency key)
    "whatsapp_hash": "WhatsApp hash",  # Text        - change detection
    "last_wa_msg":   "Last WhatsApp message",  # Date - latest WhatsApp message
    "status":        "Match status",   # Dropdown: active / possible duplicate / deleted in google / merged
    "dup_of":        "Duplicate of",   # URL or short text - suspected duplicate task link
    "last_synced":   "Last synced",    # Date (optional)
}
EXTRA = ("birthday", "address", "website", "connected_on")  # single-valued, source-owned
SOURCE_LABEL = {"google": "Google", "linkedin": "LinkedIn", "whatsapp": "WhatsApp"}
REQUIRED = ["google_id", "google_hash", "linkedin_url", "linkedin_hash", "emails", "status", "dup_of"]

ACTIVE, REVIEW, DELETED, MERGED = "active", "possible duplicate", "deleted in google", "merged"
STATUS_OPTIONS = [ACTIVE, REVIEW, DELETED, MERGED]

KEY = {"google": "google_id", "linkedin": "linkedin_url", "whatsapp": "whatsapp"}
HASH = {"google": "google_hash", "linkedin": "linkedin_hash", "whatsapp": "whatsapp_hash"}
KEY_FIELDS = tuple(KEY.values())
LIST_FIELDS = ("emails", "phones")
LABEL_FIELDS = ("groups", "sources")
MONOTONIC_DATE_FIELDS = ("last_li_msg", "last_wa_msg")

NAME_STRONG = 0.95        # name similarity that alone flags a possible duplicate
NAME_WITH_COMPANY = 0.85  # name similarity that flags a duplicate when the company also matches


def task_url(tid):
    return f"https://app.clickup.com/t/{tid}"


def task_id_from_url(url):
    m = re.search(r"/t/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None
