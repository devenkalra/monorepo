# Email Archive System

A comprehensive email archiving system that connects to IMAP servers (like Gmail), downloads emails as `.eml` files, and provides a searchable interface for viewing archived emails.

## Features

### Backend (Django)
- **Email Account Management**: Store multiple IMAP account credentials
- **Import Configurations**: Define reusable import filters (from, to, subject, date range, labels)
- **Async Email Import**: Background task processing with progress tracking and cancellation
- **Email Storage**: Saves emails as `.eml` files with metadata in database
- **Search & Filter**: Full-text search with filters for sender, recipient, subject, date, attachments
- **Pagination & Sorting**: Server-side pagination and sorting for large email archives

### Frontend (React)
- **Email Viewer**: Browse and search archived emails with advanced filters
- **Email Importer**: Manage accounts and import configurations
- **Progress Tracking**: Real-time progress for email imports with cancel capability
- **Dark Mode**: Full dark mode support
- **Responsive Design**: Works on desktop and mobile

## Architecture

### Models

#### EmailAccount
Stores IMAP server credentials and connection settings:
- `name`: Friendly account name
- `email_address`: Email address
- `imap_host`, `imap_port`, `imap_use_ssl`: IMAP connection details
- `username`, `password`: Authentication credentials
- `last_sync`: Timestamp of last successful import

#### ImportConfig
Defines reusable import filter configurations:
- `account`: Associated EmailAccount
- `mailbox`: IMAP folder (e.g., "INBOX", "[Gmail]/All Mail")
- `from_filter`, `to_filter`, `subject_filter`: Email filters
- `labels`: Gmail labels (JSON array)
- `since_date`: Only import emails after this date
- `max_emails`: Limit per import run

#### Email
Stores email metadata and references to `.eml` files:
- `message_id`: Unique email identifier
- `subject`, `from_address`, `to_addresses`, `cc_addresses`, `bcc_addresses`
- `date`: Email sent date
- `body_text`, `body_html`: Email content
- `has_attachments`, `attachment_count`: Attachment info
- `eml_file_path`: Path to stored `.eml` file
- `labels`, `thread_id`: Gmail-specific fields

## Setup

### 1. Install Dependencies

The system uses Python's built-in `imaplib` and `email` libraries, so no additional dependencies are needed beyond what's already in `requirements.txt`.

### 2. Run Migrations

```bash
docker-compose exec backend python manage.py migrate mail_archive
```

### 3. Configure Gmail App Password (for Gmail accounts)

1. Enable 2-Factor Authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate a new App Password for "Mail"
4. Use this password (not your regular password) in the EmailAccount configuration

### 4. Access the Email Archive

Navigate to `/email` in the frontend application.

## Usage

### Adding an Email Account

1. Go to Email → Import Manager tab
2. Click "+ Add Account"
3. Fill in:
   - Account Name (e.g., "My Gmail")
   - Email Address
   - IMAP Host (e.g., `imap.gmail.com`)
   - IMAP Port (usually `993` for SSL)
   - Username (usually your email address)
   - Password (use App Password for Gmail)
4. Click "Test" to verify connection
5. Save the account

### Creating an Import Configuration

1. Go to Email → Import Manager tab
2. Click "+ Add Configuration"
3. Select an email account
4. Configure filters:
   - **Mailbox**: Which folder to import from (e.g., "INBOX", "[Gmail]/All Mail")
   - **From Filter**: Only import emails from specific sender
   - **To Filter**: Only import emails to specific recipient
   - **Subject Filter**: Only import emails with keywords in subject
   - **Since Date**: Only import emails after this date
   - **Max Emails**: Limit per import run (1-1000)
5. Save the configuration

### Importing Emails

1. Go to Email → Import Manager tab
2. Find your import configuration
3. Click "Import Now"
4. Monitor progress in the progress modal
5. Cancel if needed using the Cancel button

### Viewing Emails

1. Go to Email → Email Viewer tab
2. Use filters to search:
   - **Search**: Full-text search across subject, from, and body
   - **Account**: Filter by email account
   - **From/To/Subject**: Specific field filters
   - **Date Range**: Filter by date range
   - **Has Attachments**: Only show emails with attachments
3. Sort by: Date (newest/oldest), Subject, From
4. Click an email to view full content
5. Navigate pages using pagination controls

## API Endpoints

### Email Accounts
- `GET /api/mail/accounts/` - List accounts
- `POST /api/mail/accounts/` - Create account
- `GET /api/mail/accounts/{id}/` - Get account details
- `PUT /api/mail/accounts/{id}/` - Update account
- `DELETE /api/mail/accounts/{id}/` - Delete account
- `POST /api/mail/accounts/{id}/test_connection/` - Test IMAP connection

### Import Configurations
- `GET /api/mail/configs/` - List configurations
- `POST /api/mail/configs/` - Create configuration
- `GET /api/mail/configs/{id}/` - Get configuration details
- `PUT /api/mail/configs/{id}/` - Update configuration
- `DELETE /api/mail/configs/{id}/` - Delete configuration
- `POST /api/mail/configs/{id}/import_now/` - Start async import

### Emails
- `GET /api/mail/emails/` - List emails (with filters, sorting, pagination)
  - Query params: `page`, `page_size`, `sort_by`, `account`, `from`, `to`, `subject`, `q`, `has_attachments`, `date_from`, `date_to`
- `GET /api/mail/emails/{id}/` - Get email details
- `GET /api/mail/emails/task_progress/?task_id={id}` - Get import task progress
- `POST /api/mail/emails/cancel_task/` - Cancel import task

## Storage

Emails are stored as `.eml` files in:
```
media/emails/{user_id}/{account_id}/{uid}_{timestamp}.eml
```

These files can be opened with any email client that supports `.eml` format.

## Security Considerations

### Current Implementation
- Passwords are stored in plain text in the database
- Suitable for development and personal use

### Production Recommendations
1. **Encrypt passwords**: Use Django's `cryptography` library to encrypt IMAP passwords
2. **Use environment variables**: Store sensitive credentials outside the database
3. **OAuth2**: Implement OAuth2 for Gmail instead of App Passwords
4. **Access controls**: Ensure users can only access their own accounts/emails
5. **Rate limiting**: Add rate limiting to prevent abuse
6. **Audit logging**: Log all account access and import operations

## Troubleshooting

### Connection Errors
- **Gmail**: Ensure 2FA is enabled and you're using an App Password, not your regular password
- **Port blocked**: Check firewall rules allow outbound connections on port 993
- **SSL errors**: Try disabling SSL and using port 143 (less secure)

### Import Issues
- **No emails found**: Check your filter criteria - they may be too restrictive
- **Duplicate emails**: The system automatically skips emails already imported (by message_id)
- **Slow imports**: Large attachments slow down imports; consider using `max_emails` to import in batches

### Performance
- **Large archives**: Use pagination and filters to browse large email collections
- **Search speed**: Database indexes are created on `user`, `date`, `from_address`, and `subject` fields

## Future Enhancements

Potential improvements:
- OAuth2 authentication for Gmail
- Email threading/conversation view
- Attachment extraction and preview
- Full-text search with Elasticsearch or MeiliSearch integration
- Export to various formats (PDF, HTML, CSV)
- Email rules and auto-tagging
- Scheduled imports (cron jobs)
- Email forwarding/sending capabilities
