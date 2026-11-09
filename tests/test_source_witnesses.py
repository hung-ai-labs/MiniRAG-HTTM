"""Provenance must survive merge ordering without fabricated alignments."""
import json
from pathlib import Path
import tempfile
import unittest

from minirag import operate
from minirag.source_witnesses import WitnessWriter, capture_source_witnesses


class SourceWitnessTest(unittest.IsolatedAsyncioTestCase):
    async def test_original_parsers_unchanged_and_pairs_remain_explicit(self):
        entity = ['"entity"', 'Alice', 'PERSON', 'Z description']
        relationship = ['"relationship"', 'Alice', 'Bob', 'A description', 'rents', '2']
        original_node = operate._handle_single_entity_extraction
        original_edge = operate._handle_single_relationship_extraction
        expected_node = await original_node(entity, 'chunk-z')
        expected_edge = await original_edge(relationship, 'chunk-a')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'witnesses.jsonl'
            with capture_source_witnesses(path):
                self.assertEqual(await operate._handle_single_entity_extraction(entity, 'chunk-z'), expected_node)
                self.assertEqual(await operate._handle_single_relationship_extraction(relationship, 'chunk-a'), expected_edge)
                await operate._handle_single_relationship_extraction(relationship, 'chunk-a')
                self.assertIsNone(await operate._handle_single_entity_extraction([], 'chunk-a'))
            rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['source_chunk'], 'chunk-z')
        self.assertEqual(rows[0]['extraction']['description'], 'Z description')
        self.assertEqual(rows[1]['source_chunk'], 'chunk-a')
        self.assertEqual(rows[1]['evidence_status'], 'unvalidated_extraction')
        self.assertIsNone(rows[1]['event_metadata'])
        self.assertIs(operate._handle_single_entity_extraction, original_node)
        self.assertIs(operate._handle_single_relationship_extraction, original_edge)

    async def test_exception_restores_hooks_and_refuses_nested_capture(self):
        original = operate._handle_single_entity_extraction
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'intentional'):
                with capture_source_witnesses(Path(directory) / 'outer.jsonl'):
                    with self.assertRaisesRegex(RuntimeError, 'already active'):
                        with capture_source_witnesses(Path(directory) / 'inner.jsonl'):
                            pass
                    raise RuntimeError('intentional')
            self.assertFalse((Path(directory) / 'inner.jsonl').exists())
        self.assertIs(operate._handle_single_entity_extraction, original)

    async def test_existing_sidecar_not_overwritten_and_mismatched_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'witnesses.jsonl'
            writer = WitnessWriter(path)
            try:
                with self.assertRaisesRegex(ValueError, 'exact unmerged'):
                    writer.record('entity', {'source_id': 'a<SEP>b'}, 'a')
            finally:
                writer.close()
            with self.assertRaises(FileExistsError):
                WitnessWriter(path)
            self.assertEqual(path.read_text(), '')


if __name__ == '__main__':
    unittest.main()
