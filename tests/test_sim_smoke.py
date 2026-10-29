"""Launch the shipped CLI in software-only mode, process frames, then stop."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import yaml


def test_cli_simulation_starts_and_exits_cleanly(tmp_path):
    root = Path(__file__).parents[1]
    cfg = yaml.safe_load((root/'config.yaml').read_text())
    cfg['camera'].update(source='test', width=320, height=240)
    cfg['command']['port'] = 0
    cfg['ground_station']['enabled'] = False
    cfg['video']['enabled'] = False
    cfg['log']['csv_enabled'] = False
    path = tmp_path/'sim.yaml'
    path.write_text(yaml.safe_dump(cfg))
    log = tmp_path/'sim.log'
    with log.open('w') as output:
        process = subprocess.Popen([sys.executable, '-u', 'main.py', '--sim',
                                    '--no-display', '--config', str(path)],
                                   cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                   env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if 'Başlatma tamam' in log.read_text():
                    break
                assert process.poll() is None, log.read_text()
                time.sleep(0.05)
            else:
                raise AssertionError(log.read_text())
            time.sleep(0.15)
            process.send_signal(signal.SIGINT)
            assert process.wait(timeout=10) == 0, log.read_text()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
    assert 'Traceback' not in log.read_text()
