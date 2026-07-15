import urllib.request
import ssl
from bs4 import BeautifulSoup
import os
from urllib.parse import urlparse, urljoin
import uuid
from django.core.files.base import ContentFile
from core.models import StaticFile

def scrape_substack_post_content(url):
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    )

    try:
        context = ssl.create_default_context()
        response = urllib.request.urlopen(req, context=context)
    except ssl.SSLError:
        unverified_context = ssl._create_unverified_context()
        response = urllib.request.urlopen(req, context=unverified_context)
    except Exception:
        unverified_context = ssl._create_unverified_context()
        response = urllib.request.urlopen(req, context=unverified_context)
        
    html = response.read().decode('utf-8')
    response.close()

    soup = BeautifulSoup(html, 'html.parser')

    # 1. Title
    title_meta = soup.find('meta', property='og:title')
    title = title_meta['content'] if title_meta else ""
    if not title:
        title_tag = soup.find('h1')
        title = title_tag.get_text().strip() if title_tag else "Imported Substack Post"

    # 2. Summary
    desc_meta = soup.find('meta', property='og:description')
    summary = desc_meta['content'] if desc_meta else ""

    # 3. Content Body
    body_container = (
        soup.find('div', class_='available-content') or
        soup.find('div', class_='post-content') or
        soup.find('div', class_='body markup') or
        soup.find('article')
    )

    if not body_container:
        body_container = soup.find('body')

    body_html = str(body_container) if body_container else ""
    body_soup = BeautifulSoup(body_html, 'html.parser')

    # Helper to download image
    def download_image_as_static_file(img_url, prefix="image"):
        try:
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif not img_url.startswith('http'):
                img_url = urljoin(url, img_url)

            # Un-proxy wordpress/jetpack cdns if applicable
            parsed_img = urlparse(img_url)
            netloc = parsed_img.netloc.lower()
            if any(netloc.endswith(suffix) for suffix in ['.wp.com', 'jetpack.wordpress.com']):
                path_part = parsed_img.path.lstrip('/')
                if path_part:
                    if path_part.startswith('http://') or path_part.startswith('https://'):
                        img_url = path_part
                    else:
                        img_url = f"https://{path_part}"
                    if parsed_img.query:
                        img_url += f"?{parsed_img.query}"
                    parsed_img = urlparse(img_url)

            path = parsed_img.path
            _, ext = os.path.splitext(path)
            if not ext:
                ext = ".png"

            short_token = uuid.uuid4().hex[:8]
            filename = f"{prefix}_{short_token}{ext}"

            img_req = urllib.request.Request(
                img_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            )

            try:
                img_response = urllib.request.urlopen(img_req, context=ssl.create_default_context())
            except Exception:
                img_response = urllib.request.urlopen(img_req, context=ssl._create_unverified_context())

            img_data = img_response.read()
            img_response.close()

            # Create StaticFile record
            sf = StaticFile(
                title=filename,
                filename=filename,
                make_local_copy=True
            )
            sf.file.save(filename, ContentFile(img_data), save=False)
            sf.save()
            return sf.file.url
        except Exception as e:
            print(f"Error downloading image {img_url}: {e}")
            return img_url

    # 4. Cover image
    cover_image_local_url = ""
    cover_meta = soup.find('meta', property='og:image')
    if cover_meta and cover_meta.get('content'):
        cover_image_local_url = download_image_as_static_file(cover_meta['content'], prefix="cover")

    # 5. Embedded images in content
    for img in body_soup.find_all('img'):
        src = img.get('src')
        if src:
            if src.startswith('data:') or 'doubleclick' in src or 'google-analytics' in src:
                continue

            # Prefer high-resolution image URL from data-src or data-attrs if present
            img_url = img.get('data-src') or src

            local_url = download_image_as_static_file(img_url, prefix="substack")

            img['src'] = local_url
            
            # Clean up other attributes (especially srcset)
            for attr in list(img.attrs.keys()):
                if attr not in ['src', 'alt', 'title', 'class', 'style', 'width', 'height']:
                    del img[attr]

            # Enforce height removal and width="100%"
            if 'height' in img.attrs:
                del img['height']
            img['width'] = '100%'
            img['style'] = 'max-width: 100%; height: auto;'

    # 6. Remove zoom, expand, or maximize buttons/icons, and generic buttons
    # First, unwrap any containers with zoom/expand/maximize classes that wrap an image
    for el in list(body_soup.find_all(class_=lambda x: x and any(word in x.lower() for word in ['maximize', 'zoom', 'expand']))):
        if el.find('img'):
            el.unwrap()

    # Next, decompose any remaining zoom/expand/maximize elements that don't contain images
    for el in list(body_soup.find_all(class_=lambda x: x and any(word in x.lower() for word in ['maximize', 'zoom', 'expand']))):
        if el.name != 'img':
            el.decompose()

    for btn in list(body_soup.find_all('button')):
        btn.decompose()

    content_html = body_soup.prettify()

    return {
        'title': title,
        'summary': summary,
        'content': content_html,
        'cover_image': cover_image_local_url,
        'render_as_html': True
    }
