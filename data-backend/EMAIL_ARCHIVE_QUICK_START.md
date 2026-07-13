# Email Archive - Quick Start

## 1. Run Migrations

```bash
docker-compose exec backend python manage.py migrate mail_archive
```

## 2. Setup Gmail Account (Example)

### Get Gmail App Password
1. Enable 2FA: https://myaccount.google.com/security
2. Create App Password: https://myaccount.google.com/apppasswords
3. Copy the 16-character password

### Add Account in UI
1. Navigate to `/email` → Import Manager
2. Click "+ Add Account"
3. Fill in:
   - Name: "My Gmail"
   - Email: your-email@gmail.com
   - IMAP Host: imap.gmail.com
   - IMAP Port: 993
   - Username: your-email@gmail.com
   - Password: [paste app password]
   - Use SSL: ✓
4. Click "Test" to verify
5. Save

## 3. Create Import Configuration

1. Click "+ Add Configuration"
2. Fill in:
   - Name: "All Emails"
   - Account: Select your account
   - Mailbox: INBOX (or [Gmail]/All Mail for everything)
   - Max Emails: 100 (start small for testing)
3. Optional filters:
   - From: specific-sender@example.com
   - Subject: "invoice" (keywords)
   - Since Date: 2024-01-01
4. Save

## 4. Import Emails

1. Find your configuration
2. Click "Import Now"
3. Watch progress bar
4. Cancel if needed

## 5. View Emails

1. Go to Email Viewer tab
2. Browse imported emails
3. Use filters to search
4. Click email to view full content

## Common Mailbox Names

### Gmail
- `INBOX` - Inbox only
- `[Gmail]/All Mail` - All emails (recommended)
- `[Gmail]/Sent Mail` - Sent emails
- `[Gmail]/Drafts` - Drafts
- `[Gmail]/Spam` - Spam folder
- `[Gmail]/Trash` - Trash

### Outlook/Office365
- `INBOX` - Inbox
- `Sent Items` - Sent emails
- `Drafts` - Drafts
- `Deleted Items` - Trash

### Yahoo
- `INBOX` - Inbox
- `Sent` - Sent emails
- `Draft` - Drafts
- `Trash` - Trash

## API Examples

### List Emails with Filters
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/mail/emails/?from=boss@company.com&page=1&page_size=20&sort_by=date"
```

### Start Import
```bash
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/mail/configs/1/import_now/"
```

### Check Import Progress
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/mail/emails/task_progress/?task_id=abc-123"
```

## Troubleshooting

### "Authentication failed"
- Gmail: Use App Password, not regular password
- Verify username is correct (usually email address)
- Check 2FA is enabled for Gmail

### "Connection refused"
- Check IMAP host and port
- Verify firewall allows outbound on port 993
- Try port 143 without SSL (less secure)

### "No emails found"
- Check your filters aren't too restrictive
- Try importing from INBOX first
- Verify mailbox name is correct (case-sensitive)

### Import is slow
- Large attachments take time to download
- Reduce `max_emails` to import in smaller batches
- Check your internet connection speed
