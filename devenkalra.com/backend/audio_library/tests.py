import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from audio_library.indexer import index_roots, read_tags
from audio_library.models import AudioTrack
from audio_library.roots import parse_audio_library_roots, stream_signature

try:
    import mutagen  # noqa: F401
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


def _write_mp3(path: Path, body=b'not-a-real-frame'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'ID3\x04\x00\x00\x00\x00\x00\x00' + body)


def _tiny_jpeg():
    from io import BytesIO
    from PIL import Image
    image = Image.new('RGB', (24, 24), (160, 50, 40))
    buf = BytesIO()
    image.save(buf, format='JPEG')
    return buf.getvalue()


def _write_tagged_mp3(path: Path, **fields):
    from mutagen.id3 import APIC, ID3, TALB, TBPM, TCOM, TCON, TDRC, TIT2, TPE1

    _write_mp3(path)
    tags = ID3()
    if fields.get('title'):
        tags.add(TIT2(encoding=3, text=fields['title']))
    if fields.get('artist'):
        tags.add(TPE1(encoding=3, text=fields['artist']))
    if fields.get('composer'):
        tags.add(TCOM(encoding=3, text=fields['composer']))
    if fields.get('genre'):
        tags.add(TCON(encoding=3, text=fields['genre']))
    if fields.get('album'):
        tags.add(TALB(encoding=3, text=fields['album']))
    if fields.get('year'):
        tags.add(TDRC(encoding=3, text=str(fields['year'])))
    if fields.get('bpm') is not None:
        tags.add(TBPM(encoding=3, text=str(fields['bpm'])))
    if fields.get('cover'):
        tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=fields['cover']))
    tags.save(path)


class ParseRootsTests(TestCase):
    def test_slug_equals_path(self):
        rows = parse_audio_library_roots('concerts=/mnt/audio/concerts,talks=/mnt/audio/talks|Talks')
        self.assertEqual(rows[0]['slug'], 'concerts')
        self.assertEqual(rows[0]['path'], '/mnt/audio/concerts')
        self.assertEqual(rows[1]['label'], 'Talks')

    def test_json_roots(self):
        rows = parse_audio_library_roots(
            '[{"slug":"a","path":"/data/a","label":"A"}]'
        )
        self.assertEqual(rows, [{'slug': 'a', 'path': '/data/a', 'label': 'A'}])


@skipUnless(HAS_MUTAGEN, 'mutagen is not installed')
class ReadTagsTests(TestCase):
    def test_reads_id3_fields(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'song.mp3'
            _write_tagged_mp3(
                path,
                title='Night Ride',
                artist='Asha',
                composer='R. D. Burman',
                genre='Filmi',
                album='Hits',
                year=1973,
                bpm=108,
            )
            tags = read_tags(path)
        self.assertEqual(tags['title'], 'Night Ride')
        self.assertEqual(tags['artist'], 'Asha')
        self.assertEqual(tags['composer'], 'R. D. Burman')
        self.assertEqual(tags['genre'], 'Filmi')
        self.assertEqual(tags['album'], 'Hits')
        self.assertEqual(tags['year'], 1973)
        self.assertEqual(tags['bpm'], 108.0)


class AudioLibraryApiTests(APITestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'concerts'
        self.nested = self.root / 'set1'
        _write_mp3(self.nested / 'one.mp3')
        _write_mp3(self.root / 'two.mp3')
        self.media = Path(self.tmp.name) / 'media'
        self.media.mkdir()
        self.roots = [{
            'slug': 'concerts',
            'path': str(self.root),
            'label': 'Concerts',
        }]
        self.user = User.objects.create_user('listener', password='secret', email='a@example.com')
        self.staff = User.objects.create_superuser('owner', 'owner@example.com', 'secret')
        self.token = Token.objects.create(user=self.user)
        self.staff_token = Token.objects.create(user=self.staff)

    def _index(self):
        with override_settings(
            AUDIO_LIBRARY_ROOTS=self.roots,
            AUDIO_LIBRARY_EXTENSIONS='.mp3',
            MEDIA_ROOT=str(self.media),
        ):
            return index_roots(self.roots)

    def test_index_and_list(self):
        counts = self._index()
        self.assertEqual(counts['scanned'], 2)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots):
            res = self.client.get('/api/audio/tracks/')
        self.assertEqual(res.status_code, 200)
        titles = {row['title'] for row in res.data['results']}
        self.assertIn('one', titles)
        self.assertIn('two', titles)
        parents = {row['parent'] for row in res.data['results']}
        self.assertEqual(parents, {'', 'set1'})

    @skipUnless(HAS_MUTAGEN, 'mutagen is not installed')
    def test_index_stores_id3_tags(self):
        _write_tagged_mp3(
            self.nested / 'one.mp3',
            title='Night Ride',
            artist='Asha',
            composer='R. D. Burman',
            genre='Filmi',
            year=1973,
            bpm=108,
        )
        self._index()
        track = AudioTrack.objects.get(filename='one.mp3')
        self.assertEqual(track.title, 'Night Ride')
        self.assertEqual(track.artist, 'Asha')
        self.assertEqual(track.composer, 'R. D. Burman')
        self.assertEqual(track.genre, 'Filmi')
        self.assertEqual(track.year, 1973)
        self.assertEqual(track.bpm, 108.0)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots):
            res = self.client.get('/api/audio/tracks/', {'genre': 'Filmi', 'year': 1973})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['results']), 1)
        row = res.data['results'][0]
        self.assertEqual(row['composer'], 'R. D. Burman')
        self.assertEqual(row['bpm'], 108.0)

    def test_folder_jpg_becomes_cover(self):
        (self.root / 'folder.jpg').write_bytes(_tiny_jpeg())
        self._index()
        track = AudioTrack.objects.get(filename='two.mp3')
        self.assertTrue(track.has_cover)
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots, MEDIA_ROOT=str(self.media)):
            denied = self.client.get(f'/api/audio/tracks/{track.id}/cover/')
            self.assertEqual(denied.status_code, 403)
            res = self.client.get(
                f'/api/audio/tracks/{track.id}/cover/',
                {'sig': stream_signature(track.id)},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'image/jpeg')
        self.assertGreater(len(res.getvalue()), 20)

    @skipUnless(HAS_MUTAGEN, 'mutagen is not installed')
    def test_embedded_cover(self):
        _write_tagged_mp3(self.root / 'art.mp3', title='Art', cover=_tiny_jpeg())
        self._index()
        track = AudioTrack.objects.get(filename='art.mp3')
        self.assertTrue(track.has_cover)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots, MEDIA_ROOT=str(self.media)):
            res = self.client.get('/api/audio/tracks/')
        row = next(item for item in res.data['results'] if item['filename'] == 'art.mp3')
        self.assertTrue(row['has_cover'])
        self.assertIn('/cover/', row['cover_url'])

    def test_search_and_folder_filter(self):
        self._index()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots):
            res = self.client.get('/api/audio/tracks/', {'q': 'set1'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['results']), 1)
        self.assertEqual(res.data['results'][0]['filename'], 'one.mp3')

    def test_meta_lists_top_level_parents(self):
        deeper = self.nested / 'encore'
        _write_mp3(deeper / 'three.mp3')
        self._index()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots):
            meta = self.client.get('/api/audio/meta/')
            listed = self.client.get('/api/audio/tracks/', {'parent': 'set1'})
        self.assertEqual(meta.status_code, 200)
        self.assertEqual(meta.data['parents'], [{'name': 'set1', 'track_count': 2}])
        names = {row['filename'] for row in listed.data['results']}
        self.assertEqual(names, {'one.mp3', 'three.mp3'})

    def test_unauthenticated_list_rejected(self):
        res = self.client.get('/api/audio/tracks/')
        self.assertIn(res.status_code, (401, 403))

    def test_stream_requires_signature(self):
        self._index()
        track = AudioTrack.objects.get(filename='two.mp3')
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots):
            denied = self.client.get(f'/api/audio/tracks/{track.id}/stream/')
            self.assertEqual(denied.status_code, 403)
            ok = self.client.get(
                f'/api/audio/tracks/{track.id}/stream/',
                {'sig': stream_signature(track.id)},
            )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok['Accept-Ranges'], 'bytes')
        self.assertTrue(len(ok.getvalue()) > 0)

    def test_range_request(self):
        self._index()
        track = AudioTrack.objects.get(filename='two.mp3')
        path = self.root / 'two.mp3'
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots):
            res = self.client.get(
                f'/api/audio/tracks/{track.id}/stream/',
                {'sig': stream_signature(track.id)},
                HTTP_RANGE='bytes=0-3',
            )
        self.assertEqual(res.status_code, 206)
        self.assertEqual(res.getvalue(), path.read_bytes()[:4])
        self.assertTrue(res['Content-Range'].startswith('bytes 0-3/'))

    def test_rejects_path_outside_root(self):
        self._index()
        track = AudioTrack.objects.get(filename='two.mp3')
        track.relpath = '../secret.mp3'
        track.save(update_fields=['relpath'])
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots):
            res = self.client.get(
                f'/api/audio/tracks/{track.id}/stream/',
                {'sig': stream_signature(track.id)},
            )
        self.assertEqual(res.status_code, 404)

    def test_reindex_is_superuser_only(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        res = self.client.post('/api/audio/reindex/')
        self.assertEqual(res.status_code, 403)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.staff_token.key}')
        with override_settings(AUDIO_LIBRARY_ROOTS=self.roots):
            res = self.client.post('/api/audio/reindex/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['scanned'], 2)
