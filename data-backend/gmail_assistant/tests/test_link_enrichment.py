"""Unit tests for URL extraction / classification (no network)."""

from django.test import SimpleTestCase

from gmail_assistant.link_enrichment import (
    _extract_transcript_text,
    _instagram_looks_like_video,
    append_full_transcripts_to_details,
    apify_source_for_url,
    classify_url,
    extract_urls,
    is_instagram_url,
    youtube_video_id,
)


class ExtractUrlsTests(SimpleTestCase):
    def test_plain_and_html(self):
        text = 'See https://example.com/article?x=1 and https://youtu.be/dQw4w9WgXcQ'
        html = '<a href="https://cdn.example.com/pic.jpg">img</a> <img src="https://cdn.example.com/a.png">'
        urls = extract_urls(text, html)
        self.assertIn('https://example.com/article?x=1', urls)
        self.assertIn('https://youtu.be/dQw4w9WgXcQ', urls)
        self.assertIn('https://cdn.example.com/pic.jpg', urls)
        self.assertIn('https://cdn.example.com/a.png', urls)

    def test_unescapes_html_entities(self):
        urls = extract_urls(
            'https://www.linkedin.com/feed/update/urn:li:groupPost:1/?utm_source=x&amp;utm_medium=ios',
            '',
        )
        self.assertEqual(len(urls), 1)
        self.assertIn('utm_medium=ios', urls[0])
        self.assertNotIn('&amp;', urls[0])

    def test_skips_unsubscribe(self):
        urls = extract_urls(
            'https://list-manage.com/unsubscribe?u=1',
            '<a href="https://news.example.com/unsubscribe">u</a>',
        )
        self.assertEqual(urls, [])


class ClassifyTests(SimpleTestCase):
    def test_youtube(self):
        self.assertEqual(
            classify_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
            'youtube',
        )
        self.assertEqual(classify_url('https://youtu.be/dQw4w9WgXcQ'), 'youtube')
        self.assertEqual(
            youtube_video_id('https://www.youtube.com/shorts/dQw4w9WgXcQ'),
            'dQw4w9WgXcQ',
        )

    def test_image_and_web(self):
        self.assertEqual(classify_url('https://cdn.example.com/a.PNG?w=1'), 'image')
        self.assertEqual(classify_url('https://example.com/post'), 'web')

    def test_social_apify_sources(self):
        self.assertTrue(is_instagram_url('https://www.instagram.com/p/AbC123/'))
        cases = [
            ('https://www.instagram.com/reel/AbC123xyz/', 'instagram'),
            ('https://www.facebook.com/some.page/posts/123', 'facebook'),
            ('https://fb.watch/abc123/', 'facebook'),
            (
                'https://www.linkedin.com/feed/update/urn:li:groupPost:1-2/',
                'linkedin',
            ),
            ('https://lnkd.in/abc', 'linkedin'),
            ('https://x.com/user/status/1234567890', 'twitter'),
            ('https://twitter.com/user/status/1234567890', 'twitter'),
            ('https://www.tiktok.com/@user/video/1234567890', 'tiktok'),
        ]
        for url, kind in cases:
            self.assertEqual(classify_url(url), kind, url)
            self.assertEqual(apify_source_for_url(url), kind, url)

    def test_instagram_video_paths(self):
        self.assertTrue(
            _instagram_looks_like_video('https://www.instagram.com/reel/AbC123/')
        )
        self.assertTrue(
            _instagram_looks_like_video('https://www.instagram.com/p/AbC123/')
        )
        self.assertFalse(
            _instagram_looks_like_video('https://www.instagram.com/someuser/')
        )

    def test_extract_transcript_text(self):
        text = _extract_transcript_text(
            [{'fullText': 'Hello world from youtube'}, {'transcript': 'IG audio'}]
        )
        self.assertIn('Hello world from youtube', text)
        self.assertIn('IG audio', text)

    def test_append_full_transcripts_to_details(self):
        details = append_full_transcripts_to_details(
            'Short analysis of the email.',
            [
                {
                    'kind': 'youtube',
                    'url': 'https://youtu.be/abc',
                    'transcript': 'Line one of the video.\nLine two.',
                }
            ],
        )
        self.assertIn('Short analysis of the email.', details)
        self.assertIn('Full transcript(s)', details)
        self.assertNotIn('## ', details)
        self.assertIn('Line one of the video.', details)
        self.assertIn('https://youtu.be/abc', details)
