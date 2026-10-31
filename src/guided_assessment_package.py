"""In-memory synthetic assessment deliverable using existing bound source bytes."""
from hashlib import sha256
from html import escape
from io import BytesIO
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROLE_DIRECTORIES = {
    'Simulated vendor evidence': 'vendor-evidence',
    'Simulated vendor context only': 'vendor-context',
    'Customer requirement / policy context': 'customer-policy',
}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def original_sources(sources):
    """Deduplicate IDs conservatively; never replace conflicting originals."""
    unique = {}
    for bound, role in sources:
        source = bound.source
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', source.document_id):
            raise ValueError('Unsafe artifact document ID.')
        if role not in ROLE_DIRECTORIES:
            raise ValueError('Unknown artifact source role.')
        if sha256(source.content).hexdigest() != bound.content_sha256:
            raise ValueError('Original artifact content does not match its bound digest.')
        previous = unique.get(source.document_id)
        if previous is not None and previous != (bound, role):
            raise ValueError('Conflicting artifact document ID.')
        unique[source.document_id] = (bound, role)
    return dict(sorted(unique.items()))


def artifact_manifest(sources, requirement_links):
    artifacts = []
    for document_id, (bound, role) in original_sources(sources).items():
        source = bound.source
        filename = re.sub(r'[^A-Za-z0-9._-]', '_', source.filename).strip('.') or 'artifact.bin'
        artifacts.append({
            'document_id': document_id, 'filename': source.filename, 'source_role': role,
            'archive_path': f'{ROLE_DIRECTORIES[role]}/{document_id}/{filename}',
            'sha256': bound.content_sha256, 'source_fingerprint': bound.fingerprint,
            'byte_count': len(source.content), 'provenance': source.origin,
            'service': source.service, 'environment': source.environment, 'scope': source.account_scope,
            'observed_on': source.observed_on.isoformat() if source.observed_on else None,
            'captured_on': source.captured_on.isoformat() if source.captured_on else None,
            'version': source.version, 'evidence_kind': source.evidence_kind,
            'use': ('Customer acceptance criteria; not vendor operating proof' if role == 'Customer requirement / policy context'
                    else 'Context only; not used to satisfy selected requirements' if role == 'Simulated vendor context only'
                    else 'Requirement evidence for analyst review; not confirmed assurance'),
            'requirement_links': requirement_links.get(document_id, []),
        })
    return {'synthetic': True, 'artifacts': artifacts}


def summary_html(report):
    """Printable HTML with escaped reviewer text and archive-relative source links."""
    e = lambda value: escape(str(value), quote=True)
    risk = report['risk']
    completion = report['review_completion']
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8">',
             '<title>Synthetic assessment package</title><body><h1>Synthetic assessment review</h1>',
             f'<p>{e(completion["status"])} · Vendor decision: {e(completion["vendor_decision"])}</p>',
             f'<p>Completed at: {e(completion["completed_at"])} · Snapshot: {e(completion["snapshot_fingerprint"])}</p>',
             f'<p>Case: {e(report["scenario_id"])} · Scope: {e(report["scope"])}</p>',
             '<table border="1"><tr><th>Inherent risk</th><th>Residual risk</th></tr>',
             f'<tr><td>{e(risk["inherent_score"])} · {e(risk["inherent_rating"])} · {e(risk["inherent_tier"])}</td>',
             f'<td>{e(risk["residual_status"])} · Provisional {e(risk["residual_hold_rating"])} hold; no numeric score</td></tr></table>',
             f'<p>{e(risk["residual_recommendation"])}</p>',
             '<p>This package does not approve a vendor, confirm control operation or accept risk.</p>',
             '<h2>Risk drivers and open conditions</h2><ul>']
    context = report.get('assessment_context')
    if context:
        parts.insert(3, f'<p>Vendor: {e(context["vendor"])} · Service: {e(context["service"])} · Use case: {e(context["use_case"])}</p><p>{e(context["limitations"])}</p><p>{e(context["criteria_basis"])}</p>')
    for driver in risk['drivers'] + risk['residual_drivers']:
        parts.append(f'<li>{e(driver)}</li>')
    parts.append('</ul><h2>Requirement outcomes and policy thresholds</h2>')
    for row in report['requirements']:
        parts.extend([f'<h3>{e(row["requirement_id"])} · {e(row["outcome"])}</h3>',
                      f'<p>Customer policy: {e(row["customer_policy_id"])} v{e(row["policy_version"])}; {e(row["threshold_summary"])}</p>',
                      f'<p>Next action: {e(row["next_action"])}</p>'])
        for citation in row['citations'] + row['customer_policy_citations']:
            parts.append(f'<p>{e(citation["source_role"])}: <a href="{e(citation["archive_path"])}">{e(citation["filename"])}</a> · {e(citation["location"])}</p><blockquote>{e(citation["quote"])}</blockquote>')
    parts.append('<h2>Open draft findings</h2>')
    for finding in report['findings']:
        parts.append(f'<p>{e(finding["requirement_id"])} · {e(finding["context_status"])} · {e(finding["rationale"])}</p>')
    parts.append('<h2>Remaining questions</h2>')
    for request in report['targeted_requests']:
        parts.append(f'<p>{e(request["question"])}</p>')
    parts.append('<h2>Simulated annotation history (no confirmations or approvals)</h2>')
    for action in report['analyst_actions']:
        parts.append(f'<p>{e(action["requirement_id"])} · {e(action["action"])} · {e(action["status"])} · {e(action["recorded_at"])}: {e(action["rationale"])}</p>')
    if context and context.get('evaluations') is not None:
        parts.append('<h2>Unconfirmed source-cited threshold comparisons</h2>')
        for evaluation in context['evaluations']:
            parts.append(f'<h3>{e(evaluation["requirement_id"])} · {e(evaluation["status"])}</h3><p>{e(evaluation["threshold"])}</p>')
            for fact in evaluation['facts']:
                parts.append(f'<p>{e(fact["comparison"])} · {e(fact["filename"])} · {e(fact["location"])}</p><blockquote>{e(fact["quote"])}</blockquote><p>{e("; ".join(fact["uncertainties"]))}</p>')
            for source in evaluation['sources']:
                parts.append(f'<p>{e(source["filename"])}: {e("; ".join(source["uncertainties"]))}</p>')
            parts.append(f'<p>Next action: {e(evaluation["next_action"])}</p><p>{e(evaluation["limitations"])}</p>')
    parts.append('<h2>Attached evidence/artifacts</h2><ul>')
    for artifact in report['evidence_manifest']['artifacts']:
        parts.append(f'<li><a href="{e(artifact["archive_path"])}">{e(artifact["filename"])}</a> · {e(artifact["document_id"])} · {e(artifact["source_role"])} · SHA-256 {e(artifact["sha256"])} · {e(artifact["use"])}</li>')
    parts.append('</ul><p><a href="report.json">Detailed assessment report</a> · <a href="manifest.json">Source manifest</a></p></body></html>')
    return '\n'.join(parts).encode('utf-8')


def assessment_package(report, sources):
    """Verify the frozen inventory and write exact original bytes, never surrogates."""
    originals = original_sources(sources)
    manifest = {'synthetic': True, 'artifacts': report['evidence_manifest']['artifacts']}
    manifest_content = json_bytes(manifest)
    if sha256(manifest_content).hexdigest() != report['evidence_manifest']['sha256']:
        raise ValueError('Manifest digest mismatch.')
    if {a['document_id'] for a in manifest['artifacts']} != set(originals):
        raise ValueError('Artifact inventory changed; reopen the review.')
    files = {'summary.html': summary_html(report), 'report.json': json_bytes(report), 'manifest.json': manifest_content}
    for artifact in manifest['artifacts']:
        bound, role = originals[artifact['document_id']]
        expected = artifact_manifest([(bound, role)], {artifact['document_id']: artifact['requirement_links']})['artifacts'][0]
        if artifact != expected or artifact['archive_path'] in files:
            raise ValueError('Artifact manifest does not match the original source.')
        files[artifact['archive_path']] = bound.source.content
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as archive:
        for path, content in files.items():
            info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()
