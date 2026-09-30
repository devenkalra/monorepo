from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from productions.timing import (
    TimecodeError,
    apply_duration_edit,
    apply_end_edit,
    format_timecode,
    parse_timecode,
    recompute_scene_times,
    teleprompter_text,
    flat_output_text,
)


class TimecodeTests(TestCase):
    def test_parse_flexible_forms(self):
        self.assertEqual(parse_timecode('3.5'), Decimal('3.500'))
        self.assertEqual(parse_timecode('1:03.5'), Decimal('63.500'))
        self.assertEqual(parse_timecode('02:01:3.5'), Decimal('7263.500'))
        self.assertEqual(parse_timecode('1:30'), Decimal('90.000'))
        self.assertEqual(parse_timecode(90), Decimal('90.000'))

    def test_format_omits_unused_units(self):
        self.assertEqual(format_timecode(0), '0:00')
        self.assertEqual(format_timecode(Decimal('3.5')), '3.5')
        self.assertEqual(format_timecode(Decimal('63.5')), '1:03.5')
        self.assertEqual(format_timecode(Decimal('7263.5')), '2:01:03.5')

    def test_reject_negative(self):
        with self.assertRaises(TimecodeError):
            parse_timecode('-1')


class CascadeTests(TestCase):
    def _scenes(self, durations):
        start = Decimal('0')
        rows = []
        for duration in durations:
            rows.append(SimpleNamespace(start_seconds=start, duration_seconds=Decimal(duration)))
            start += Decimal(duration)
        return rows

    def test_duration_edit_cascades(self):
        scenes = self._scenes(['10', '10', '10'])
        apply_duration_edit(scenes, 0, '15')
        self.assertEqual([row.start_seconds for row in scenes], [Decimal('0.000'), Decimal('15.000'), Decimal('25.000')])
        self.assertEqual([row.duration_seconds for row in scenes], [Decimal('15.000'), Decimal('10.000'), Decimal('10.000')])

    def test_end_edit_cascades(self):
        scenes = self._scenes(['10', '10', '10'])
        apply_end_edit(scenes, 1, '25')
        self.assertEqual(scenes[1].duration_seconds, Decimal('15.000'))
        self.assertEqual(scenes[2].start_seconds, Decimal('25.000'))

    def test_end_before_start_rejected(self):
        scenes = self._scenes(['10', '10'])
        with self.assertRaises(TimecodeError):
            apply_end_edit(scenes, 1, '5')
        self.assertEqual(scenes[1].duration_seconds, Decimal('10'))

    def test_reorder_keeps_durations(self):
        scenes = self._scenes(['5', '20', '8'])
        scenes[0], scenes[1] = scenes[1], scenes[0]
        recompute_scene_times(scenes)
        self.assertEqual([row.duration_seconds for row in scenes], [Decimal('20.000'), Decimal('5.000'), Decimal('8.000')])
        self.assertEqual(scenes[0].start_seconds, Decimal('0.000'))
        self.assertEqual(scenes[1].start_seconds, Decimal('20.000'))


class TeleprompterTests(TestCase):
    def test_uses_scene_title(self):
        scenes = [
            SimpleNamespace(title='Open on the trail', scene_type='Hook', voiceover='Open on the trail'),
            SimpleNamespace(title='Intro', scene_type='Intro', voiceover='  '),
            SimpleNamespace(title='Keep walking', scene_type='Body', voiceover='We keep walking'),
        ]
        self.assertEqual(
            teleprompter_text(scenes),
            '[Open on the trail]\nOpen on the trail\n\n[Keep walking]\nWe keep walking',
        )

    def test_falls_back_to_type_when_title_empty(self):
        scenes = [
            SimpleNamespace(title='', scene_type='Hook', voiceover='Open on the trail'),
        ]
        self.assertEqual(teleprompter_text(scenes), '[Hook]\nOpen on the trail')


class FlatOutputTests(TestCase):
    def test_lists_populated_fields_only(self):
        scenes = [
            SimpleNamespace(
                title='Open',
                scene_type='Hook',
                start_seconds=Decimal('0'),
                duration_seconds=Decimal('8'),
                end_seconds=Decimal('8'),
                visuals='Face on the ridge',
                voiceover='I did not pack enough water.',
                music='thin drone',
                fx_cues='',
                notes='  ',
                assets=['Drone shot', 'Map'],
            ),
            SimpleNamespace(
                title='',
                scene_type='Segment',
                start_seconds=Decimal('8'),
                duration_seconds=Decimal('6'),
                end_seconds=Decimal('14'),
                visuals='',
                voiceover='',
                music='',
                fx_cues='',
                notes='',
                assets=[],
            ),
        ]
        self.assertEqual(
            flat_output_text(scenes),
            (
                'Scene 1\n'
                'Title: Open\n'
                'Type: Hook\n'
                'Start: 0:00\n'
                'Duration: 8\n'
                'End: 8\n'
                'Visuals & B-Roll: Face on the ridge\n'
                'Voiceover & Dialogue: I did not pack enough water.\n'
                'Music / Sound: thin drone\n'
                'Assets: Drone shot, Map\n'
                '\n'
                'Scene 2\n'
                'Type: Segment\n'
                'Start: 8\n'
                'Duration: 6\n'
                'End: 14'
            ),
        )
