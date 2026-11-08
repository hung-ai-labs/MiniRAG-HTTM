"""Scientific split invariants; standard library fixtures, no dataset labels."""
from pathlib import Path
import sys

RESEARCH = Path(__file__).resolve().parents[2] / 'reproduce/research'
sys.path.insert(0, str(RESEARCH))
import freeze_2wiki_split as split


def fixture():
    return [{'_id': str(i), 'type': 'a' if i % 2 else 'b',
             'supporting_facts': [[str(i // 2), 0]],
             'context': [[str(i // 2), ['text']], ['distractor', ['shared']]]} for i in range(100)]


def test_small_partition_is_analysis_not_test():
    dev, test, report = split.partition(fixture())
    assert len(dev) == 20 and len(test) == 80
    assert dev.isdisjoint(test) and dev | test == set(range(100))
    assert report['gold_title_overlap']['shared_unique_titles'] == 0
    assert report['all_context_title_overlap']['shared_unique_titles'] == 1


def test_connected_questions_never_cross_and_split_is_repeatable():
    rows = fixture()
    a, b, report = split.partition(rows)
    assert (a, b, report) == split.partition(rows)
    assert all((i in a) == (i + 1 in a) for i in range(0, 100, 2))
