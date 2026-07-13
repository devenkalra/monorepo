# Email Archive - Simple Testing Steps

## Quick Test (5 minutes)

### 1. Run the test script
```bash
cd /home/ubuntu/monorepo/data-backend
./test_email_archive.sh
```

This will:
- ✓ Check Docker services
- ✓ Run migrations
- ✓ Verify database tables
- ✓ Check Celery worker
- ✓ Check Redis
- ✓ Show access URLs

### 2. Get Gmail App Password

**Quick Link**: https://myaccount.google.com/apppasswords

1. Make sure 2FA is enabled first
2. Click "Generate" for Mail
3. Copy the 16-character password
4. **Remove spaces** (e.g., `abcd efgh ijkl mnop` → `abcdefghijklmnop`)

### 3. Open Email Archive

```
http://localhost:5174/email
```

### 4. Add Account

Click **Import Manager** → **+ Add Account**

```
Name:          My Gmail
Email:         your-email@gmail.com
IMAP Host:     imap.gmail.com
IMAP Port:     993
Username:      your-email@gmail.com
Password:      [paste app password - no spaces!]
Use SSL:       ✓
```

Click **Test** → Should say "Connection successful!"

Click **Save Account**

### 5. Create Import Config

Click **+ Add Configuration**

```
Name:          Test Import
Account:       My Gmail
Mailbox:       INBOX
Max Emails:    10
```

Leave filters blank for now.

Click **Save Configuration**

### 6. Import Emails

Click **Import Now** → Watch progress bar → Click **OK** when done

### 7. View Emails

Click **Email Viewer** tab → See your imported emails!

### 8. Test Features

- Click an email to view details
- Try searching
- Try filters (from, subject, date)
- Try sorting (newest/oldest)

## That's it!

You now have a working email archive system.

## If Something Goes Wrong

### Backend logs
```bash
docker-compose logs backend | tail -50
```

### Celery logs
```bash
docker-compose logs celery-worker | tail -50
```

### Check database
```bash
docker-compose exec backend python manage.py shell
>>> from mail_archive.models import Email
>>> Email.objects.count()
```

### Restart everything
```bash
docker-compose restart backend celery-worker
```

## Common Issues

| Problem | Solution |
|---------|----------|
| "Authentication failed" | Use App Password, not regular password |
| "Connection refused" | Check IMAP host and port |
| "No emails imported" | Check filters aren't too restrictive |
| Progress stuck at 0% | Check Redis and Celery are running |
| Emails not showing | Check backend logs for errors |

## Need Help?

See full documentation:
- `EMAIL_ARCHIVE_TESTING.md` - Detailed testing guide
- `EMAIL_ARCHIVE_QUICK_START.md` - Setup instructions
- `EMAIL_ARCHIVE_GUIDE.md` - Complete documentation
