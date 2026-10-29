"""Bound untrusted upload parsing before source fingerprinting (Linux development host).

Reuse the existing parser with incremental output budgets. PDF extraction runs in
a disposable process with memory/CPU/wall-time bounds for decompression/internals.
This is resource containment, not malware scanning or production document custody.
"""
from pathlib import Path
import json
import subprocess
import sys

MAX_SEGMENTS = 2000
MAX_CHARACTERS = 250000
MEMORY_BYTES = 384 * 1024 * 1024
CPU_SECONDS = 3
WALL_SECONDS = 10
LIMIT_ERROR = 'Document exceeds local parser resource limits; upload a smaller, simpler document.'


def read_bounded_document(filename, content):
    from src.evidence_intelligence_mvp import EvidenceDocument, EvidenceSegment, read_evidence_document
    if Path(filename).suffix.lower() != '.pdf':
        # TXT has incremental segment retention; DOCX XML has a bounded 2 MB
        # preflight in the upload adapter. Neither can expand like PDF streams.
        return read_evidence_document(filename, content, max_segments=MAX_SEGMENTS, max_chars=MAX_CHARACTERS, max_xml_bytes=2 * 1024 * 1024)
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'src.bounded_document_parser', filename],
            input=content, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=Path(__file__).resolve().parents[1], timeout=WALL_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(LIMIT_ERROR) from exc
    if result.returncode != 0:
        raise ValueError(LIMIT_ERROR)
    payload = json.loads(result.stdout)
    if 'error' in payload:
        raise ValueError(payload['error'])
    return EvidenceDocument(payload['filename'], tuple(EvidenceSegment(**s) for s in payload['segments']))


def _worker():
    # Set bounds before importing any PDF/parser dependencies. Fail closed on hosts
    # without these OS limits rather than silently parsing uploads without bounds.
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    from dataclasses import asdict
    from src.evidence_intelligence_mvp import read_evidence_document
    try:
        content = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024:
            raise ValueError(LIMIT_ERROR)
        document = read_evidence_document(sys.argv[1], content,
            max_segments=MAX_SEGMENTS, max_chars=MAX_CHARACTERS)
        payload = asdict(document)
    except ValueError as exc:
        payload = {'error': str(exc)[:500]}
    except MemoryError:
        payload = {'error': LIMIT_ERROR}
    sys.stdout.write(json.dumps(payload))


if __name__ == '__main__':
    _worker()
