"""Private engine entry point; the IFsCompanion desktop host owns its lifetime."""
import json
import pathlib
import sys
import threading
import traceback


def main():
    import companion_server
    if len(sys.argv) > 1 and sys.argv[1] == '--pick-folder':
        from folder_picker import select_folder
        select_folder(sys.argv[2], sys.argv[3])
        return
    import app
    app.initialize_storage()
    ready_stream = sys.stdout
    log = (app.DATA_ROOT / 'application.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = log
    sys.stderr = log
    server = companion_server.create_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == '--self-test':
            import urllib.request
            result = {'http_ok': urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}').status == 200}
            app.JOBS['packaged-test'] = {'status': 'running'}
            app.compare('packaged-test', {'a': sys.argv[2], 'b': sys.argv[2], 'variables': ['GDP', 'POP', 'AGDEM'], 'atol': 0, 'rtol': 0})
            result['comparison'] = app.JOBS['packaged-test']
            result['ok'] = result['http_ok'] and result['comparison']['status'] == 'complete' and all('error' not in s and s['changed'] == 0 for s in result['comparison']['report']['summaries'])
            pathlib.Path(sys.argv[3]).write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
        else:
            ready_stream.write(json.dumps({'url': f'http://127.0.0.1:{server.server_port}'}) + '\n')
            ready_stream.flush()
            sys.stdin.read()  # EOF on normal desktop shutdown or host failure.
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
