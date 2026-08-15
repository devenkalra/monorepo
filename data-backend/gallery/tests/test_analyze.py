import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase
from PIL import Image

from gallery.analyze import (
    ANALYZER_VERSION,
    BLUR_SKIP_THRESHOLD,
    analysis_is_fresh,
    analyze_image_file,
    current_detector,
    detect_faces,
    item_blur,
    item_subject,
    subject_from_faces,
)
from gallery.compiler import compile_show
from gallery.planner import plan_from_item_ids


def _write_image(path, pixels, size=64):
    img = Image.new('L', (size, size))
    img.putdata(pixels)
    img.save(path)


class AnalyzeTests(SimpleTestCase):
    def test_solid_is_blurry_checker_is_sharp(self):
        with tempfile.TemporaryDirectory() as tmp:
            solid = Path(tmp) / 'solid.png'
            check = Path(tmp) / 'check.png'
            _write_image(solid, [180] * (64 * 64))
            _write_image(
                check,
                [0 if (x + y) % 2 == 0 else 255 for y in range(64) for x in range(64)],
            )
            solid_a = analyze_image_file(solid)
            check_a = analyze_image_file(check)
            self.assertGreater(solid_a['blur'], BLUR_SKIP_THRESHOLD)
            self.assertLess(check_a['blur'], 0.4)
            self.assertEqual(solid_a['width'], 64)
            self.assertEqual(solid_a['subject'], {'x': 0.5, 'y': 0.5})
            self.assertEqual(solid_a['faces'], [])

    def test_cache_freshness(self):
        blob = {
            'v': ANALYZER_VERSION,
            'source_url': '/media/a.jpg',
            'blur': 0.1,
            'subject': {'x': 0.5, 'y': 0.5},
            'faces': [],
            'detector': current_detector(),
        }
        self.assertTrue(analysis_is_fresh(blob, '/media/a.jpg'))
        self.assertFalse(analysis_is_fresh(blob, '/media/b.jpg'))
        self.assertFalse(analysis_is_fresh({**blob, 'v': 0}, '/media/a.jpg'))
        self.assertFalse(analysis_is_fresh({k: v for k, v in blob.items() if k != 'faces'}, '/media/a.jpg'))
        if current_detector() != 'none':
            self.assertFalse(analysis_is_fresh({**blob, 'detector': 'none'}, '/media/a.jpg'))
            stale = {k: v for k, v in blob.items() if k != 'detector'}
            self.assertFalse(analysis_is_fresh(stale, '/media/a.jpg'))

    def test_subject_from_faces(self):
        self.assertEqual(subject_from_faces([]), {'x': 0.5, 'y': 0.5})
        self.assertEqual(
            subject_from_faces([{'x': 0.1, 'y': 0.2, 'w': 0.2, 'h': 0.2}]),
            {'x': 0.2, 'y': 0.3},
        )
        small = {'x': 0.0, 'y': 0.4, 'w': 0.1, 'h': 0.1}
        large = {'x': 0.6, 'y': 0.3, 'w': 0.3, 'h': 0.3}
        sub = subject_from_faces([small, large])
        self.assertAlmostEqual(sub['x'], 0.68, places=3)
        self.assertAlmostEqual(sub['y'], 0.45, places=3)

    def test_detect_faces_normalizes_boxes(self):
        from unittest.mock import MagicMock, patch

        gray = Image.new('L', (200, 100), 128)
        fake = MagicMock()
        fake.detectMultiScale.return_value = [(40, 20, 40, 40)]
        with patch('gallery.analyze._haar_cascades', return_value=[fake]):
            faces = detect_faces(gray)
        self.assertEqual(len(faces), 1)
        self.assertAlmostEqual(faces[0]['x'], 0.2)
        self.assertAlmostEqual(faces[0]['y'], 0.2)
        self.assertAlmostEqual(faces[0]['w'], 0.2)
        self.assertAlmostEqual(faces[0]['h'], 0.4)

    def test_compiler_aims_ken_burns_at_face_subject(self):
        faces = [{'x': 0.1, 'y': 0.2, 'w': 0.2, 'h': 0.2}]
        item = SimpleNamespace(analysis={'faces': faces, 'subject': subject_from_faces(faces)})
        plan = plan_from_item_ids(['a'], items_by_id={'a': item})
        config, _ = compile_show(plan, {'a': item})
        views = config['slides'][0]['views']
        self.assertAlmostEqual(views[0]['x'], 0.2)
        self.assertAlmostEqual(views[0]['y'], 0.3)
        self.assertAlmostEqual(views[1]['x'], 0.2)
        self.assertAlmostEqual(views[1]['y'], 0.3)

    def test_planner_skips_blurry(self):
        sharp = SimpleNamespace(analysis={'blur': 0.1})
        blurry = SimpleNamespace(analysis={'blur': 0.9})
        plan = plan_from_item_ids(
            ['a', 'b', 'c'],
            items_by_id={'a': sharp, 'b': blurry, 'c': sharp},
        )
        self.assertEqual([s['item_id'] for s in plan['shots']], ['a', 'c'])
        self.assertEqual(plan['skipped_blurry'], ['b'])

    def test_compiler_uses_subject(self):
        item = SimpleNamespace(analysis={'subject': {'x': 0.2, 'y': 0.8}})
        plan = plan_from_item_ids(['a'], items_by_id={'a': item})
        config, _ = compile_show(plan, {'a': item})
        views = config['slides'][0]['views']
        self.assertAlmostEqual(views[0]['x'], 0.2)
        self.assertAlmostEqual(views[0]['y'], 0.8)

    def test_item_helpers(self):
        item = SimpleNamespace(analysis={'blur': 0.75, 'subject': {'x': 0.1, 'y': 0.9}})
        self.assertEqual(item_blur(item), 0.75)
        self.assertEqual(item_subject(item), (0.1, 0.9))
        self.assertEqual(item_subject(object()), (0.5, 0.5))
