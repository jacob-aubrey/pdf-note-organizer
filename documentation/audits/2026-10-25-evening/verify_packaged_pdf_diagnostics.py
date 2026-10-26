"""Exercise exact-helper PDF diagnostics against a disposable Zotero fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

workspace = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(workspace))
import pymupdf
from note_organizer.remarkable_cloud import TokenVault
from note_organizer.zotero_pilot import Ledger, LocalZotero, Paper, publish
from note_organizer.zotero_worker import Worker


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--helper-sha256', required=True)
    parser.add_argument('--port', type=int, default=23168)
    args = parser.parse_args()
    fixture = args.fixture.resolve(strict=True)
    helper = args.helper.resolve(strict=True)
    assert digest(helper.read_bytes()) == args.helper_sha256
    ready = json.loads((fixture / 'ready.json').read_text(encoding='utf-8'))
    assert not (fixture / 'done').exists(), 'The synthetic fixture must still be open.'
    client = None
    record = {'scope': 'Synthetic disposable Zotero profile only; no cloud calls',
              'helper': str(helper), 'helper_sha256': args.helper_sha256,
              'fixture': str(fixture), 'port': args.port, 'zotero_version': ready['version']}
    target = Path(__file__).with_name('packaged-pdf-diagnostics-results.json')
    try:
        grant = TokenVault(fixture / 'profile/notable/zotero-grant.dpapi')
        client = LocalZotero(args.port, grant_store=grant, interactive=False)
        assert client.server_id == ready['server']
        original = fixture / 'Synthetic malformed-content.pdf'
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 72), 'Synthetic searchable text survives the malformed operator.')
            xref = page.get_contents()[0]
            doc.update_stream(xref, doc.xref_stream(xref) + b'\nq garbage Q\n')
            original.write_bytes(doc.tobytes())
        before = original.read_bytes()
        published = publish(client, Ledger(fixture / 'diagnostic-publication'), 'synthetic-diagnostic',
                    [Paper('synthetic-diagnostic', original, digest(before),
                           {'title': 'Synthetic malformed-content diagnostic'})], apply=True)['papers'][0]
        key = published['attachment_key']
        client.native_annotation_text(key)
        record.update(native_attachment_key=key, managed_annotation_read_passed=True)
        state = fixture / 'malformed-helper-state'
        worker = Worker(state)
        worker.config = {'server_id': client.server_id, 'ocr': False, 'sync_paused': True}
        worker.save()
        worker.state.write('documents', {'synthetic-diagnostic': {'source_key': key,
                            'view_key': key, 'origin': 'zotero', 'uploaded': True}})
        TokenVault(state / 'zotero-grant.dpapi').save(grant.load())
        environment = os.environ.copy()
        # Test the direct-worker fallback, independently of launch-time routing.
        environment.pop('PYMUPDF_MESSAGE', None)
        temporary = fixture / 'helper-temp'
        temporary.mkdir()
        environment['TEMP'] = environment['TMP'] = str(temporary)
        packets = [{'id': 1, 'method': 'reindex', 'params': {'key': key}},
                   {'id': 2, 'method': 'status', 'params': {}}, {'id': 3, 'method': 'shutdown'}]
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        completed = subprocess.run([str(helper), '--state', str(state), '--port', str(args.port), '--debug-stacks'],
                    input=''.join(json.dumps(row) + '\n' for row in packets).encode('utf-8'),
                    capture_output=True, timeout=120, env=environment, cwd=workspace, startupinfo=startup)
        stdout = completed.stdout.decode('utf-8')
        stderr = completed.stderr.decode('utf-8', errors='replace')
        responses = [json.loads(line) for line in stdout.splitlines()]
        by_id = {row['id']: row for row in responses if 'id' in row}
        record.update(returncode=completed.returncode, stdout_packets=responses, stderr=stderr,
                      reindex_response_received=1 in by_id, following_status_received=2 in by_id,
                      actual_native_diagnostic_on_stderr='MuPDF error:' in stderr,
                      source_sha256=digest(before),
                      source_unchanged=original.read_bytes() == before,
                      stored_pdf_unchanged=client.file_path(key).read_bytes() == before,
                      diagnostics_enabled=True, launch_message_environment_unset=True)
        assert completed.returncode == 0
        assert not by_id[1].get('error'), by_id[1]
        assert not by_id[2].get('error'), by_id[2]
        assert 'MuPDF error:' in stderr, 'The fixture must actually emit the native diagnostic.'
        assert record['source_unchanged'] and record['stored_pdf_unchanged']
        record['result'] = 'PASS'
    except Exception as error:
        record['result'] = 'FAIL'
        record['error_type'] = type(error).__name__
        record['error'] = str(error)
        raise
    finally:
        if client:
            client.close()
        (fixture / 'close-test').touch()
        target.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: value for key, value in record.items()
                          if key not in {'stdout_packets', 'stderr'}}, indent=2))


if __name__ == '__main__':
    main()
