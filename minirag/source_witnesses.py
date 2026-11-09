"""Capture extraction provenance before merge, without inferring source alignment.

These records establish which extraction came from which chunk. The generated
description is not a verbatim quotation and is not proof the relation is true.
Use in a dedicated indexing process, with a fresh sidecar outside old indexes.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path


class WitnessWriter:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('x', encoding='utf-8')
        self.seen = set()

    def record(self, kind, data, chunk_key):
        if kind not in ('entity', 'relationship'):
            raise ValueError('Unknown extraction kind')
        if not chunk_key or data['source_id'] != chunk_key:
            raise ValueError('Capture requires the exact unmerged extraction source')
        fields = ('entity_name', 'entity_type', 'description') if kind == 'entity' else (
            'src_id', 'tgt_id', 'description', 'keywords', 'weight')
        record = {'schema_version': 1, 'kind': kind, 'source_chunk': chunk_key,
                  'extraction': {k: data[k] for k in fields},
                  'evidence_status': 'unvalidated_extraction',
                  'event_metadata': None}
        canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
        key = hashlib.sha256(canonical.encode()).hexdigest()
        if key not in self.seen:
            self.file.write(json.dumps({'witness_id': key, **record}, ensure_ascii=False) + '\n')
            self.file.flush()
            self.seen.add(key)

    def close(self):
        self.file.close()


@contextmanager
def capture_source_witnesses(path):
    """Wrap the two original parsers during a dedicated index run only.

    Does not change extraction results, graph merge, vectors or query ranking.
    Never activate around a shared in-process index/query service. Existing
    sidecars are refused; an incomplete index run leaves a partial sidecar.
    """
    from . import operate
    names = ('_handle_single_entity_extraction', '_handle_single_relationship_extraction')
    originals = {name: getattr(operate, name) for name in names}
    if any(getattr(fn, '_witness_capture', False) for fn in originals.values()):
        raise RuntimeError('Witness capture is already active')
    writer = WitnessWriter(path)

    def wrapped(fn, kind):
        async def capture(record_attributes, chunk_key):
            result = await fn(record_attributes, chunk_key)
            if result is not None:
                writer.record(kind, result, chunk_key)
            return result
        capture._witness_capture = True
        return capture

    try:
        for name, kind in zip(names, ('entity', 'relationship')):
            setattr(operate, name, wrapped(originals[name], kind))
        yield writer
    finally:
        for name, original in originals.items():
            setattr(operate, name, original)
        writer.close()
