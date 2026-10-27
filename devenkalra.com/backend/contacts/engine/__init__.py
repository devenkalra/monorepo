"""Contact sync engine: Google / LinkedIn / WhatsApp -> ClickUp Contacts list.

Framework-free; the Django app (contacts.runner) and the CLI both drive it through `run_sync`.
"""
from .clickup import ClickUp
from .errors import ConfigError
from .guard import WriteGuard
from .index import build_index
from .sync import Reporter, SyncContext, merge

SOURCES = ("google", "linkedin", "whatsapp", "merge")


def open_list(token, list_id, guard, session=None):
    if not token or not list_id:
        raise ConfigError("Set CONTACTS_CLICKUP_LIST_ID and a ClickUp token (CLICKUP_API_TOKEN).")
    cu = ClickUp(token, list_id, guard, session=session)
    missing = cu.load_fields()
    return cu, missing


def run_sync(*, source, cu, reporter=None, options=None, decisions=None, files=None,
             google_service=None, sync_token=None, on_index=None):
    """Run one sync against an opened list. Returns (context, result)."""
    options = options or {}
    files = files or {}
    reporter = reporter or Reporter()
    reporter.progress("Reading ClickUp contacts", 0, 0)
    ix = build_index(cu, progress=lambda n: reporter.progress("Reading ClickUp contacts", n, 0))
    if on_index:
        on_index(ix)
    ctx = SyncContext(
        cu, ix, reporter=reporter, decisions=decisions,
        hold_review=source in ("google", "linkedin", "whatsapp"),
        no_create=bool(options.get("no_create")),
        trust_names=bool(options.get("trust_exact_names")),
        rename_tasks=bool(options.get("rename_tasks")),
        overwrite_values=options.get("overwrite_values", True),
    )
    for w in ix.warnings:
        ctx.log("WARN", "", w)
    result = {}
    if source == "google":
        from .sources.google import run_google
        if google_service is None:
            raise ConfigError("Connect Google first.")
        result["next_sync_token"] = run_google(
            ctx, google_service, sync_token=sync_token, full=bool(options.get("full")),
            photos=bool(options.get("photos")), do_writeback=bool(options.get("writeback")),
            ignore_patterns=options.get("ignore_labels") or (), revisit=list(ctx.decisions))
    elif source == "linkedin":
        from .sources.linkedin import run_linkedin
        if not files.get("connections"):
            raise ConfigError("Upload LinkedIn's Connections.csv first.")
        run_linkedin(ctx, files["connections"], files.get("messages"))
    elif source == "whatsapp":
        from .sources.whatsapp import run_whatsapp
        if not files.get("export"):
            raise ConfigError("Upload a WhatsApp contacts export first.")
        run_whatsapp(ctx, files["export"], only_saved=bool(options.get("only_saved")))
    elif source == "merge":
        merge(ctx, str(options.get("survivor") or ""), str(options.get("loser") or ""))
    else:
        raise ConfigError(f"Unknown source {source!r}")
    return ctx, result


__all__ = ["ClickUp", "ConfigError", "Reporter", "SOURCES", "SyncContext", "WriteGuard", "open_list", "run_sync"]
