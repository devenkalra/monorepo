import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from gallery.compiler import compile_show
from gallery.planner import (
    build_plan,
    extract_plan_json,
    feature_card,
    plan_from_item_ids,
    validate_plan,
)


def _item(item_id, **analysis):
    return SimpleNamespace(
        id=item_id,
        filename=f'{item_id}.jpg',
        title=item_id,
        caption='',
        analysis=analysis,
    )


class PlannerTests(SimpleTestCase):
    def test_feature_card_includes_faces(self):
        faces = [{'x': 0.1, 'y': 0.2, 'w': 0.2, 'h': 0.25}]
        card = feature_card(
            _item('a', faces=faces, subject={'x': 0.2, 'y': 0.325}, blur=0.1, orientation='portrait'),
            item_id='a',
        )
        self.assertEqual(card['id'], 'a')
        self.assertEqual(card['faces'], 1)
        self.assertEqual(card['face_kind'], 'portrait')
        self.assertEqual(card['face_boxes'][0]['x'], 0.1)
        self.assertEqual(card['subject']['x'], 0.2)

        group = feature_card(
            _item('g', faces=[{}, {}, {}], blur=0.2),
            item_id='g',
        )
        self.assertEqual(group['faces'], 3)
        self.assertEqual(group['face_kind'], 'group')

        empty = feature_card(_item('z'), item_id='z')
        self.assertEqual(empty['faces'], 0)
        self.assertEqual(empty['face_kind'], 'none')

    def test_heuristic_focus_face_when_detected(self):
        items = {
            'a': _item('a', faces=[{'x': 0.2, 'y': 0.2, 'w': 0.2, 'h': 0.2}]),
            'b': _item('b', faces=[]),
        }
        plan = plan_from_item_ids(['a', 'b'], items_by_id=items)
        self.assertEqual(plan['shots'][0]['focus'], 'face')
        self.assertEqual(plan['shots'][1]['focus'], 'subject')

    def test_validate_drops_unknown_and_skipped(self):
        raw = {
            'title': 'Trip',
            'style': 'kenburns',
            'shots': [
                {'item_id': 'a', 'role': 'opener', 'focus': 'face'},
                {'item_id': 'ghost', 'role': 'hero'},
                {'item_id': 'b', 'skip': True},
                {'item_id': 'c', 'role': 'detail', 'seconds': 99, 'focus': 'center'},
            ],
        }
        plan, warnings = validate_plan(raw, ['a', 'b', 'c'])
        self.assertEqual([s['item_id'] for s in plan['shots']], ['a', 'c'])
        self.assertEqual(plan['shots'][0]['role'], 'opener')
        self.assertEqual(plan['shots'][-1]['role'], 'closer')
        self.assertEqual(plan['shots'][1]['seconds'], 20.0)
        self.assertTrue(any('ghost' in w for w in warnings))

    def test_extract_json_strips_think_and_fence(self):
        raw = '<think>nope</think>\n```json\n{"shots": [{"item_id": "a"}]}\n```'
        data = extract_plan_json(raw)
        self.assertEqual(data['shots'][0]['item_id'], 'a')

    def test_build_plan_falls_back_on_prose(self):
        items = {'a': _item('a', faces=[{}]), 'b': _item('b')}
        with patch('gallery.planner.llm_available', return_value=True), patch(
            'gallery.planner._chat_completion', return_value='sure, open on the group'
        ):
            plan = build_plan(['a', 'b'], items_by_id=items, prompt='open on the group')
        self.assertEqual(plan['planner'], 'heuristic')
        self.assertTrue(plan.get('planner_error'))
        self.assertEqual([s['item_id'] for s in plan['shots']], ['a', 'b'])

    def test_build_plan_uses_valid_llm_json(self):
        items = {
            'a': _item('a', faces=[]),
            'b': _item(
                'b',
                faces=[{'x': 0.4, 'y': 0.3, 'w': 0.2, 'h': 0.2}, {'x': 0.6, 'y': 0.3, 'w': 0.2, 'h': 0.2}, {}],
            ),
            'c': _item('c', faces=[{'x': 0.5, 'y': 0.4, 'w': 0.2, 'h': 0.2}]),
        }
        payload = json.dumps({
            'title': 'Family',
            'style': 'documentary',
            'shots': [
                {'item_id': 'b', 'role': 'opener', 'focus': 'face', 'seconds': 8},
                {'item_id': 'c', 'role': 'hero', 'focus': 'face'},
                {'item_id': 'a', 'skip': True},
            ],
        })
        with patch('gallery.planner.llm_available', return_value=True), patch(
            'gallery.planner._chat_completion', return_value=payload
        ) as chat:
            plan = build_plan(
                ['a', 'b', 'c'],
                items_by_id=items,
                prompt='open on the group, skip shots without faces',
                title='Show',
            )
        self.assertEqual(plan['planner'], 'llm')
        self.assertEqual([s['item_id'] for s in plan['shots']], ['b', 'c'])
        self.assertEqual(plan['shots'][0]['focus'], 'face')
        user_msg = chat.call_args.kwargs['prompt']
        self.assertIn('face_kind', user_msg)
        self.assertIn('"faces": 3', user_msg)
        self.assertIn('open on the group', user_msg)

    def test_build_plan_on_log_records_cards_and_fallback(self):
        items = {'a': _item('a', faces=[{'x': 0.2, 'y': 0.2, 'w': 0.2, 'h': 0.2}])}
        lines = []

        def on_log(step, message, **kwargs):
            lines.append((step, message, kwargs))

        with patch('gallery.planner.llm_available', return_value=True), patch(
            'gallery.planner._chat_completion', return_value='not json'
        ):
            plan = build_plan(['a'], items_by_id=items, prompt='open on faces', on_log=on_log)
        self.assertEqual(plan['planner'], 'heuristic')
        self.assertTrue(any('feature card' in msg for _, msg, _ in lines))
        self.assertTrue(any('faces' in (kw.get('data') or {}) or 'cards' in (kw.get('data') or {}) for _, _, kw in lines))
        self.assertTrue(any('unused' in msg.lower() or 'your order' in msg.lower() for _, msg, _ in lines))

    def test_compiler_honors_center_focus(self):
        item = _item('a', subject={'x': 0.2, 'y': 0.8}, faces=[{}])
        plan = {
            'shots': [{'item_id': 'a', 'focus': 'center'}],
        }
        config, _ = compile_show(plan, {'a': item})
        views = config['slides'][0]['views']
        self.assertEqual(views[0]['x'], 0.5)
        self.assertEqual(views[0]['y'], 0.5)
