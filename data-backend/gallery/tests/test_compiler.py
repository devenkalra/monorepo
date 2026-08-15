from django.test import SimpleTestCase

from gallery.compiler import compile_show
from gallery.planner import plan_from_item_ids
from gallery.presets import PRESETS


class CompilerTests(SimpleTestCase):
    def test_empty_shots_raise(self):
        with self.assertRaises(ValueError):
            compile_show({'shots': []}, {})

    def test_unknown_item_dropped(self):
        plan = plan_from_item_ids(['keep', 'missing'])
        config, warnings = compile_show(plan, {'keep': object()})
        self.assertEqual(len(config['slides']), 1)
        self.assertEqual(config['slides'][0]['item_id'], 'keep')
        self.assertTrue(any('missing' in w for w in warnings))

    def test_order_preserved_on_channel_a(self):
        ids = ['a', 'b', 'c']
        plan = plan_from_item_ids(ids)
        config, _ = compile_show(plan, {i: object() for i in ids})
        self.assertEqual([s['item_id'] for s in config['slides']], ids)
        self.assertTrue(all(s['channel'] == 0 for s in config['slides']))
        starts = [s['start'] for s in config['slides']]
        self.assertEqual(starts, sorted(starts))

    def test_scale_to_target(self):
        ids = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']
        plan = plan_from_item_ids(ids)
        config, _ = compile_show(
            plan,
            {i: object() for i in ids},
            style='kenburns',
            target_seconds=30,
        )
        total = sum(s['duration'] for s in config['slides'])
        self.assertAlmostEqual(total, 30, delta=0.6)

    def test_no_blend_effects(self):
        ids = ['a', 'b', 'c']
        plan = plan_from_item_ids(ids)
        config, _ = compile_show(plan, {i: object() for i in ids})
        kinds = {fx['type'] for fx in config['effects']}
        self.assertNotIn('blend', kinds)
        self.assertNotIn('blend-reverse', kinds)

    def test_ken_burns_focus_center(self):
        plan = plan_from_item_ids(['a'])
        config, _ = compile_show(plan, {'a': object()})
        views = config['slides'][0]['views']
        self.assertEqual(views[0]['x'], 0.5)
        self.assertEqual(views[0]['y'], 0.5)
        self.assertEqual(views[0]['zoom'], 1.0)
        self.assertGreater(views[-1]['zoom'], 1.0)

    def test_focus_center_overrides_subject(self):
        from types import SimpleNamespace

        item = SimpleNamespace(analysis={'subject': {'x': 0.2, 'y': 0.8}})
        config, _ = compile_show(
            {'shots': [{'item_id': 'a', 'focus': 'center'}]},
            {'a': item},
        )
        views = config['slides'][0]['views']
        self.assertEqual(views[0]['x'], 0.5)
        self.assertEqual(views[0]['y'], 0.5)

    def test_punchy_has_no_fades(self):
        plan = plan_from_item_ids(['a', 'b'])
        config, _ = compile_show(plan, {'a': object(), 'b': object()}, style='punchy')
        self.assertEqual(config['effects'], [])
        self.assertAlmostEqual(
            config['slides'][0]['duration'],
            PRESETS['punchy']['seconds'],
            delta=0.05,
        )
