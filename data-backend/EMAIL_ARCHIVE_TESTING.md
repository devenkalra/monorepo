# Email Archive - Testing Guide

## Prerequisites

Before testing, ensure:
1. Docker containers are running
2. Database migrations are applied
3. You have a Gmail account with App Password ready

## Step-by-Step Testing

### Step 1: Apply Migrations

```bash
# Run migrations to create database tables
docker-compose exec backend python manage.py migrate mail_archive

# Verify tables were created
docker-compose exec db psql -U postgres -d postgres -c "\dt mail_archive*"
```

Expected output: Should show 3 tables (emailaccount, importconfig, email)

### Step 2: Start/Restart Services

```bash
# If services are already running, restart to pick up new code
docker-compose restart backend celery-worker

# Or start fresh
docker-compose up -d

# Check logs
docker-compose logs -f backend celery-worker
```

### Step 3: Setup Gmail App Password

1. **Enable 2-Factor Authentication**:
   - Go to https://myaccount.google.com/security
   - Enable 2-Step Verification if not already enabled

2. **Create App Password**:
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Click "Generate"
   - Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)
   - **Important**: Remove spaces when entering (e.g., `abcdefghijklmnop`)

### Step 4: Access Email Archive

1. Open your browser to `http://localhost:5174` (or your frontend URL)
2. Login if needed
3. Click "Email" in the top navigation
4. You should see two tabs: "📧 Email Viewer" and "⚙️ Import Manager"

### Step 5: Add Email Account

1. Go to **Import Manager** tab
2. Click **"+ Add Account"**
3. Fill in the form:
   ```
   Account Name: My Gmail
   Email Address: your-email@gmail.com
   IMAP Host: imap.gmail.com
   IMAP Port: 993
   Username: your-email@gmail.com
   Password: [paste your 16-char app password without spaces]
   Use SSL: ✓ (checked)
   Active: ✓ (checked)
   ```
4. Click **"Save Account"**

### Step 6: Test Connection

1. Find your account in the list
2. Click **"Test"** button
3. Expected result: 
   - Success message: "Connection successful! Found X mailboxes."
   - If it fails, check:
     - App password is correct (no spaces)
     - 2FA is enabled
     - IMAP is enabled in Gmail settings

### Step 7: Create Import Configuration

1. Click **"+ Add Configuration"**
2. Fill in the form:
   ```
   Configuration Name: Test Import
   Email Account: Select "My Gmail"
   Mailbox: INBOX
   Max Emails per Import: 10 (start small!)
   ```
3. **Optional filters** (leave blank for first test):
   - From Filter: (leave blank to import from anyone)
   - To Filter: (leave blank)
   - Subject Filter: (leave blank)
   - Since Date: (leave blank or set to recent date)
4. Click **"Save Configuration"**

### Step 8: Import Emails

1. Find your configuration in the list
2. Click **"Import Now"**
3. Watch the progress modal:
   - Should show "Importing Emails"
   - Progress bar should update
   - Message should show "Imported X of Y emails..."
4. Wait for completion (should take 10-30 seconds for 10 emails)
5. Click **"OK"** when done

### Step 9: View Imported Emails

1. Go to **Email Viewer** tab
2. You should see your imported emails
3. Verify:
   - Email count is shown (e.g., "10 emails")
   - Emails are listed with subject, from, date
   - Attachments show 📎 icon

### Step 10: Test Search and Filters

1. **Search**: Type keywords in search box
2. **Account Filter**: Select your account from dropdown
3. **From Filter**: Enter sender email
4. **Subject Filter**: Enter keywords
5. **Date Range**: Set from/to dates
6. **Attachments**: Check "Has Attachments" box
7. **Sorting**: Try different sort options:
   - Newest First (default)
   - Oldest First
   - Subject A-Z
   - From A-Z

### Step 11: View Email Details

1. Click on any email in the list
2. Modal should open showing:
   - Full subject
   - From, To, Cc addresses
   - Date sent
   - Attachment count (if any)
   - Full email body (HTML or text)
3. Click X to close

### Step 12: Test Pagination (if you have >20 emails)

1. Import more emails (increase max_emails to 50)
2. Go to Email Viewer
3. Should see pagination controls at bottom:
   - ««, ‹ Prev, Page X of Y, Next ›, »»
4. Click through pages
5. Verify emails change

### Step 13: Test Cancellation

1. Create a config with max_emails = 100
2. Click "Import Now"
3. Immediately click **"Cancel"** button
4. Confirm cancellation
5. Verify:
   - Progress modal shows "Task cancelled by user"
   - Import stops
   - Click OK to close

### Step 14: Verify .eml Files

```bash
# Check that .eml files were created
docker-compose exec backend ls -lh media/emails/

# Should see directory structure: media/emails/{user_id}/{account_id}/*.eml

# View a sample .eml file
docker-compose exec backend head -n 20 media/emails/1/1/*.eml
```

### Step 15: Test Duplicate Detection

1. Run the same import configuration again
2. Should complete quickly
3. Check logs:
   ```bash
   docker-compose logs backend | grep "Skipping duplicate"
   ```
4. Verify no duplicate emails in viewer

## Common Test Scenarios

### Scenario 1: Import Specific Sender's Emails

1. Create config with:
   - From Filter: `boss@company.com`
   - Max Emails: 20
2. Import
3. Verify only emails from that sender appear

### Scenario 2: Import Recent Emails Only

1. Create config with:
   - Since Date: 2026-01-01
   - Max Emails: 50
2. Import
3. Verify all emails are from 2026 or later

### Scenario 3: Import from Specific Mailbox

1. Create config with:
   - Mailbox: `[Gmail]/Sent Mail`
   - Max Emails: 10
2. Import
3. Verify emails are from your sent folder

### Scenario 4: Search Across All Emails

1. Import emails from multiple senders
2. In Email Viewer, use search:
   - Search: "invoice"
   - From: "accounting@"
   - Date From: 2025-01-01
3. Verify filtered results

## Verification Checklist

- [ ] Migrations applied successfully
- [ ] Email account added and connection tested
- [ ] Import configuration created
- [ ] Emails imported successfully (progress shown)
- [ ] Emails visible in Email Viewer
- [ ] Search and filters work
- [ ] Sorting changes results (server-side)
- [ ] Pagination works (if >20 emails)
- [ ] Email detail modal displays correctly
- [ ] .eml files created in media/emails/
- [ ] Duplicate detection works (re-import same emails)
- [ ] Cancellation works
- [ ] Dark mode displays correctly

## Troubleshooting

### No emails imported (0 imported, X skipped)
**Cause**: All emails already exist in database
**Solution**: Either:
- Delete existing emails from database
- Change filters to import different emails
- Check different mailbox

### "Authentication failed"
**Cause**: Invalid credentials
**Solutions**:
- Verify App Password is correct (no spaces)
- Check username is your full email address
- Ensure 2FA is enabled for Gmail
- Verify IMAP is enabled in Gmail settings

### "Connection refused"
**Cause**: Cannot reach IMAP server
**Solutions**:
- Check IMAP host is correct (imap.gmail.com for Gmail)
- Verify port 993 is not blocked by firewall
- Check internet connection

### Progress shows 0/0
**Cause**: Progress updates not reaching frontend
**Solutions**:
- Check Redis is running: `docker-compose ps redis`
- Check Celery worker is running: `docker-compose ps celery-worker`
- Check backend logs: `docker-compose logs backend`

### Emails not showing in viewer
**Cause**: Import may have failed silently
**Solutions**:
- Check backend logs: `docker-compose logs backend | grep "email import"`
- Check Celery logs: `docker-compose logs celery-worker`
- Verify database: `docker-compose exec backend python manage.py shell`
  ```python
  from mail_archive.models import Email
  print(Email.objects.count())
  ```

### Modal doesn't close after import
**Cause**: Progress endpoint not returning completed status
**Solutions**:
- Check Redis is running
- Refresh page
- Check browser console for errors

## Advanced Testing

### Test with Different IMAP Providers

#### Outlook/Office365
```
IMAP Host: outlook.office365.com
IMAP Port: 993
Use SSL: ✓
```

#### Yahoo Mail
```
IMAP Host: imap.mail.yahoo.com
IMAP Port: 993
Use SSL: ✓
```

### Test Large Import
1. Create config with max_emails = 500
2. Monitor progress updates
3. Test cancellation mid-import
4. Verify pagination with many pages

### Test Complex Filters
1. Create config with multiple filters:
   - From: specific-domain.com
   - Subject: "report"
   - Since Date: 2025-06-01
   - Max Emails: 100
2. Verify only matching emails imported

## Database Inspection

```bash
# Connect to database
docker-compose exec db psql -U postgres -d postgres

# Check email accounts
SELECT id, name, email_address, last_sync FROM mail_archive_emailaccount;

# Check import configs
SELECT id, name, mailbox, max_emails FROM mail_archive_importconfig;

# Check imported emails
SELECT id, subject, from_address, date FROM mail_archive_email ORDER BY date DESC LIMIT 10;

# Count emails by account
SELECT account_id, COUNT(*) FROM mail_archive_email GROUP BY account_id;
```

## Performance Testing

### Test Pagination Performance
```bash
# Import 200 emails
# Then test pagination speed in frontend
# Should load each page quickly (<1 second)
```

### Test Search Performance
```bash
# Import 500+ emails
# Test full-text search
# Should return results in <2 seconds
```

## Cleanup After Testing

```bash
# Delete all test emails
docker-compose exec backend python manage.py shell
>>> from mail_archive.models import Email, EmailAccount, ImportConfig
>>> Email.objects.all().delete()
>>> ImportConfig.objects.all().delete()
>>> EmailAccount.objects.all().delete()

# Or delete .eml files
docker-compose exec backend rm -rf media/emails/
```

## Success Criteria

✅ System is working correctly if:
1. Can add email account and test connection successfully
2. Can create import configuration with filters
3. Import shows progress and completes
4. Emails appear in viewer with correct metadata
5. Search and filters return expected results
6. Sorting changes the order (verified by checking different pages)
7. Pagination allows browsing all emails
8. Email detail shows full content
9. .eml files are created in media directory
10. Duplicate imports are skipped
11. Cancellation stops the import
12. Dark mode displays correctly
