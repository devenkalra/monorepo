"""Shared helpers for prefs / active account / ZK writes."""

from __future__ import annotations

from django.utils import timezone

from .models import EmailSummary, GmailAccount, LlmJob, UserPreference


def get_or_create_prefs(user) -> UserPreference:
    prefs, _ = UserPreference.objects.get_or_create(user=user)
    return prefs


def get_active_account(user, account_id=None) -> GmailAccount | None:
    qs = GmailAccount.objects.filter(user=user)
    if account_id:
        return qs.filter(id=account_id).first()
    active = qs.filter(is_active=True).first()
    if active:
        return active
    return qs.first()


def set_active_account(user, account: GmailAccount) -> None:
    GmailAccount.objects.filter(user=user, is_active=True).update(is_active=False)
    account.is_active = True
    account.save(update_fields=['is_active', 'updated_at'])


def scrub_zero_knowledge_data(user) -> dict[str, int]:
    """Delete persisted email/LLM content for a user when enabling ZK.

    Removes EmailSummary rows (subjects, snippets, summaries, categories) and
    clears stored process/summarize job result payloads that may contain email text.
    Does not touch Gmail, OAuth accounts, saved prompts, or schedules.
    """
    summaries_deleted, _ = EmailSummary.objects.filter(user=user).delete()
    jobs_scrubbed = LlmJob.objects.filter(user=user).update(
        result='', progress={}, errors=[]
    )
    return {
        'summaries_deleted': int(summaries_deleted),
        'jobs_scrubbed': int(jobs_scrubbed),
    }


def upsert_summary(
    *,
    user,
    account: GmailAccount,
    message: dict,
    summary: dict,
    zero_knowledge: bool,
) -> EmailSummary:
    defaults = {
        'user': user,
        'thread_id': message.get('thread_id') or '',
        'category': summary.get('category') or '',
        'category_confidence': float(summary.get('category_confidence') or 0),
        'model': summary.get('model') or '',
        'processed_at': timezone.now(),
        'status': 'active',
    }
    if zero_knowledge:
        defaults.update(
            {
                'subject': '',
                'from_addr': '',
                'snippet': '',
                'date_iso': '',
                'internal_date_ms': 0,
                'brief_summary': '',
                'key_points': [],
                'details': '',
                'labels': [],
            }
        )
    else:
        defaults.update(
            {
                'subject': message.get('subject') or '',
                'from_addr': message.get('from_addr') or '',
                'snippet': message.get('snippet') or '',
                'date_iso': message.get('date_iso') or '',
                'internal_date_ms': int(message.get('internal_date_ms') or 0),
                'brief_summary': summary.get('brief_summary') or '',
                'key_points': summary.get('key_points') or [],
                'details': summary.get('details') or '',
                'labels': [],
            }
        )
    obj, _ = EmailSummary.objects.update_or_create(
        account=account,
        gmail_id=message['gmail_id'],
        defaults=defaults,
    )
    return obj
