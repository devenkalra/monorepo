from django.db import models
import uuid

class Page(models.Model):
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True, default="", help_text="Optional category to group pages")
    slug = models.SlugField(max_length=200, unique=True, help_text="Unique slug for the page URL (e.g. professional-life)")
    content = models.TextField(help_text="Markdown content of the page")
    roles_with_access = models.CharField(max_length=255, blank=True, default="", help_text="Comma-separated roles allowed to view this page (e.g. 'user, superuser'). Leave blank for public access.")
    render_as_html = models.BooleanField(default=False, help_text="If checked, render page content as raw HTML instead of Markdown")
    allowed_emails = models.TextField(blank=True, default="", help_text="Optional comma-separated list of emails allowed to view this page (if protected)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class MenuItem(models.Model):
    title = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='children',
        help_text="Parent menu item. Leave blank for root-level items."
    )
    page = models.ForeignKey(
        Page, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='menu_items',
        help_text="The page this menu item links to. Leave blank if it's just a category folder."
    )
    order = models.PositiveIntegerField(default=0, help_text="Order in which items appear in the submenu")
    roles_with_access = models.CharField(max_length=255, blank=True, default="", help_text="Comma-separated roles allowed to view this menu item (e.g. 'user, superuser'). Leave blank for public access.")
    external_url = models.CharField(max_length=300, null=True, blank=True, help_text="Optional external link (e.g. github URL)")
    show_in_menu = models.BooleanField(default=True, help_text="If unchecked, this item won't be rendered in the header dropdown menu but can still be navigated to via links and generate breadcrumbs")
    full_path = models.CharField(max_length=500, blank=True, default="", help_text="Computed full hierarchical path of the menu item")

    class Meta:
        ordering = ['order', 'title']

    def save(self, *args, **kwargs):
        # Compute full path
        parts = [self.title]
        p = self.parent
        while p:
            parts.append(p.title)
            p = p.parent
        self.full_path = " -> ".join(reversed(parts))
        
        super().save(*args, **kwargs)
        
        # Recursively update children paths if this item has children
        # Using a list copy to prevent infinite loops or query evaluation issues
        children_list = list(self.children.all())
        for child in children_list:
            child.save()

    def __str__(self):
        return self.full_path or self.title

class Project(models.Model):
    STATUS_CHOICES = [
        ('idea', 'Idea'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('paused', 'Paused'),
    ]
    title = models.CharField(max_length=200)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='subprojects',
        help_text="Parent project. Leave blank for root-level projects."
    )
    category = models.CharField(max_length=100, help_text="e.g. Photography, Video AI Internships")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='idea')
    description = models.TextField(blank=True, default="")
    render_as_html = models.BooleanField(default=False, help_text="If checked, render description content as raw HTML instead of Markdown")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    rank = models.IntegerField(default=9000, help_text="Ranking order (ascending)")
    image_url = models.URLField(null=True, blank=True, help_text="Optional project cover image link")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.category})"

class WorkflowIdea(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    STATUS_CHOICES = [
        ('backlog', 'Backlog'),
        ('active', 'Active'),
        ('done', 'Done'),
    ]
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    render_as_html = models.BooleanField(default=False, help_text="If checked, render description content as raw HTML instead of Markdown")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='backlog')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class BookReview(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    rating = models.PositiveIntegerField(default=5, help_text="Rating out of 5 stars")
    review_content = models.TextField(help_text="Detailed review (Markdown supported)")
    summary = models.TextField(help_text="Brief summary/highlights of the book")
    read_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} by {self.author}"

class MusicTrack(models.Model):
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=200, help_text="Composer, singer, or group")
    genre = models.CharField(max_length=100, help_text="e.g. Classical, Ghazal, Folk")
    description = models.TextField(blank=True, help_text="Notes on the track/rag/composition")
    youtube_url = models.URLField(null=True, blank=True, help_text="Link to YouTube or audio source")

    def __str__(self):
        return f"{self.title} ({self.artist})"

class Recipe(models.Model):
    title = models.CharField(max_length=200)
    ingredients = models.TextField(help_text="List of ingredients (one per line or markdown format)")
    instructions = models.TextField(help_text="Steps to prepare")
    prep_time_minutes = models.PositiveIntegerField(default=15)
    image_url = models.URLField(null=True, blank=True, help_text="Link to recipe photo")

    def __str__(self):
        return self.title

class StaticFile(models.Model):
    title = models.CharField(max_length=200, blank=True, default="", help_text="Descriptive title for the file")
    filename = models.CharField(max_length=200, blank=True, default="", help_text="Optional custom filename (e.g. animation.gif). If blank, defaults to the uploaded file name.")
    file = models.FileField(upload_to='uploads/', blank=True, null=True, help_text="Upload PDFs, images, or documents here")
    file_url = models.URLField(max_length=500, blank=True, null=True, help_text="Or paste/drop a URL here to upload from the internet")
    make_local_copy = models.BooleanField(default=True, help_text="If checked and a URL is provided, download it and save a local copy.")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        # If filename is empty but file_url is provided, generate a short 8-character filename with original extension
        if not self.filename and self.file_url:
            from urllib.parse import urlparse
            import os
            import uuid
            path = urlparse(self.file_url).path
            _, ext = os.path.splitext(path)
            short_token = uuid.uuid4().hex[:8]
            self.filename = f"{short_token}{ext}"

        if self.filename:
            import os
            from urllib.parse import urlparse
            import uuid
            fn = self.filename.strip()
            # If the filename looks like a URL or a full path, convert it to a short random name
            if fn.startswith('http://') or fn.startswith('https://') or '/' in fn or '\\' in fn:
                path = urlparse(fn).path
                _, ext = os.path.splitext(path)
                short_token = uuid.uuid4().hex[:8]
                self.filename = f"{short_token}{ext}"
            else:
                self.filename = os.path.basename(fn)

        if self.file_url and self.make_local_copy and not self.file:
            from django.core.exceptions import ValidationError
            try:
                self._download_file()
            except Exception as e:
                raise ValidationError(f"Failed to download file from URL: {e}")

    def _download_file(self):
        import os
        import urllib.request
        from django.core.files import File
        from urllib.parse import urlparse
        import ssl
        import tempfile

        custom_filename = self.filename.strip() if getattr(self, 'filename', None) else ""
        
        # Un-proxy WordPress/Jetpack CDN URL
        parsed_url = urlparse(self.file_url)
        netloc = parsed_url.netloc.lower()
        if any(netloc.endswith(suffix) for suffix in ['.wp.com', 'jetpack.wordpress.com']):
            path_part = parsed_url.path.lstrip('/')
            if path_part:
                if path_part.startswith('http://') or path_part.startswith('https://'):
                    self.file_url = path_part
                else:
                    self.file_url = f"https://{path_part}"
                # Keep query params if any
                if parsed_url.query:
                    self.file_url += f"?{parsed_url.query}"
                parsed_url = urlparse(self.file_url)

        # Determine initial filename
        if custom_filename:
            filename = custom_filename
        else:
            filename = os.path.basename(parsed_url.path)
            if not filename:
                filename = "downloaded_file"

        # Fetch URL content using Request with standard headers
        req = urllib.request.Request(
            self.file_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        )

        response = None
        # Try with default SSL context first, fall back to unverified context if needed
        try:
            context = ssl.create_default_context()
            response = urllib.request.urlopen(req, context=context)
        except ssl.SSLError:
            unverified_context = ssl._create_unverified_context()
            response = urllib.request.urlopen(req, context=unverified_context)
        except Exception:
            try:
                unverified_context = ssl._create_unverified_context()
                response = urllib.request.urlopen(req, context=unverified_context)
            except Exception:
                raise

        try:
            # Detect extension from Content-Type if parsed filename has no extension
            _, ext = os.path.splitext(filename)
            if not ext:
                content_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
                mime_map = {
                    'image/gif': '.gif',
                    'image/jpeg': '.jpg',
                    'image/pjpeg': '.jpg',
                    'image/png': '.png',
                    'image/webp': '.webp',
                    'image/svg+xml': '.svg',
                    'image/x-icon': '.ico',
                    'application/pdf': '.pdf',
                    'text/plain': '.txt',
                    'text/html': '.html',
                }
                guessed_ext = mime_map.get(content_type, '')
                filename += guessed_ext

            temp_fd, temp_path = tempfile.mkstemp()
            try:
                with open(temp_path, 'wb') as temp_file:
                    temp_file.write(response.read())
                
                with open(temp_path, 'rb') as f:
                    self.file.save(filename, File(f), save=False)
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        finally:
            if response:
                response.close()

        self.file_url = None

    def save(self, *args, **kwargs):
        import os
        from django.core.files.base import ContentFile
        from urllib.parse import urlparse
        import uuid

        if self.filename:
            fn = self.filename.strip()
            if fn.startswith('http://') or fn.startswith('https://') or '/' in fn or '\\' in fn:
                path = urlparse(fn).path
                _, ext = os.path.splitext(path)
                short_token = uuid.uuid4().hex[:8]
                self.filename = f"{short_token}{ext}"
            else:
                self.filename = os.path.basename(fn)

        custom_filename = self.filename.strip() if getattr(self, 'filename', None) else ""

        # If clean() wasn't called (e.g. programmatic save), download here
        if self.file_url and self.make_local_copy and not self.file:
            try:
                self._download_file()
            except Exception as e:
                print("Error downloading static file from URL:", e)

        # Rename local file if custom filename is specified and different
        if self.file and custom_filename:
            current_name = os.path.basename(self.file.name)
            if current_name != custom_filename:
                try:
                    self.file.open('rb')
                    content = self.file.read()
                    self.file.close()
                    self.file.save(custom_filename, ContentFile(content), save=False)
                except Exception as e:
                    print("Error renaming uploaded file:", e)

        # Set default title if blank
        if not self.title:
            if self.file:
                self.title = os.path.basename(self.file.name)
            elif self.file_url:
                if custom_filename:
                    self.title = custom_filename
                else:
                    parsed_url = urlparse(self.file_url)
                    self.title = os.path.basename(parsed_url.path) or "downloaded_file"
            else:
                self.title = "untitled"

        # Update filename field to match actual file name if it was blank
        if not self.filename and self.file:
            self.filename = os.path.basename(self.file.name)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class PageData(models.Model):
    page_slug = models.CharField(max_length=100, unique=True, help_text="Slug of the page this data belongs to")
    data = models.JSONField(default=dict, help_text="JSON payload containing state data")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Data for {self.page_slug}"


class BlogCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Blog Categories"

    def __str__(self):
        return self.name


class BlogTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField(help_text="Markdown or HTML content of the blog post")
    summary = models.TextField(max_length=500, blank=True, help_text="Brief excerpt for index/cards preview")
    cover_image = models.CharField(max_length=500, blank=True, null=True, help_text="Optional cover image URL or relative path (e.g. /api/media/uploads/filename.png)")
    render_as_html = models.BooleanField(default=False, help_text="If checked, render post content as raw HTML instead of Markdown")
    
    # Relationships
    category = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, related_name='posts')
    tags = models.ManyToManyField(BlogTag, blank=True, related_name='posts')
    
    # Publishing Controls
    is_published = models.BooleanField(default=False)
    preview_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    publish_date = models.DateTimeField(blank=True, null=True, help_text="Date when post becomes visible")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-publish_date', '-created_at']

    def __str__(self):
        return self.title


class Comment(models.Model):
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments')
    author_name = models.CharField(max_length=100)
    author_email = models.EmailField()
    content = models.TextField()
    is_approved = models.BooleanField(default=False, help_text="If checked, this comment will be shown on the blog post")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author_name} on {self.post.title}"


class Subscription(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200, blank=True, default="")
    provider = models.CharField(max_length=50, blank=True, default="google", help_text="Social auth provider (e.g. google, github)")
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, help_text="If unchecked, user is unsubscribed from updates")

    def __str__(self):
        return f"{self.email} ({'Active' if self.is_active else 'Inactive'})"



