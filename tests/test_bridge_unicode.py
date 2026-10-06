import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
QUERIES = [
    'Why is CPU load high?',
    'Почему компьютер тормозит? Ёжик — CPU',
    '¿Por qué está lenta la memoria? ¡Compruébalo!',
    'Por que o computador está lento? Ação e memória.',
    '为什么电脑很慢？检查内存。',
    'Pourquoi le PC est-il lent ? Mémoire et charge élevée.',
    'Perché il computer è lento? Memoria e attività.',
    'Warum ist der PC langsam? Arbeitsspeicher prüfen: Größe.',
    'パソコンが遅いのはなぜ？メモリを確認。',
    '컴퓨터가 왜 느린가요? 메모리를 확인해 주세요.',
    'لماذا الجهاز بطيء؟ افحص الذاكرة وCPU.',
    'कंप्यूटर धीमा क्यों है? मेमोरी की जाँच करें। 🔍',
]


def bridge(tmp_path, encoding, payload, *, stdin=False):
    database = tmp_path / 'Данные_数据_بيانات_हिन्दी' / 'sherlock.db'
    env = {**os.environ, 'SHERLOCK_DB_PATH': str(database),
           'PYTHONIOENCODING': encoding + ':strict', 'PYTHONUTF8': '0'}
    command = [sys.executable, '-m', 'sherlock.desktop_bridge']
    request = json.dumps(payload, ensure_ascii=False)
    if not stdin:
        command += ['--request-json', request]
    output = subprocess.run(command, cwd=ROOT, env=env,
                            input=request.encode('utf-8') if stdin else None,
                            capture_output=True, timeout=30)
    assert output.stdout, output.stderr
    assert output.stdout.isascii(), 'Wire JSON must not depend on a console codepage'
    response = json.loads(output.stdout.decode('utf-8', errors='strict'))
    assert '\ufffd' not in output.stdout.decode('utf-8')
    return output, response, database


@pytest.mark.parametrize('encoding', ['cp1251', 'cp1252', 'ascii'])
@pytest.mark.parametrize('question', QUERIES)
def test_question_round_trip_through_real_bridge(tmp_path, encoding, question):
    output, response, _ = bridge(tmp_path, encoding, {'action': 'investigate', 'question': question})
    assert output.returncode == 0, output.stderr
    assert response['ok'] is True
    assert response['result']['question'] == question
    assert response['result']['report']['status'] == 'INSUFFICIENT_EVIDENCE'


@pytest.mark.parametrize('encoding', ['cp1251', 'cp1252', 'ascii'])
def test_unicode_database_path_round_trip(tmp_path, encoding):
    output, response, database = bridge(tmp_path, encoding, {'action': 'history_info'})
    assert output.returncode == 0
    assert response['result']['database_path'] == str(database.resolve())


@pytest.mark.parametrize('encoding', ['cp1251', 'cp1252', 'ascii'])
def test_unicode_error_is_valid_json(tmp_path, encoding):
    output, response, _ = bridge(tmp_path, encoding, {'action': '不存在_غير موجود_нет'})
    assert output.returncode == 2
    assert response['ok'] is False
    assert '不存在_غير موجود_нет' in response['error']


def test_stdin_is_utf8_even_with_a_legacy_console(tmp_path):
    question = '¿Por qué? Почему? 为什么？ لماذا؟ क्यों? 🔍'
    output, response, _ = bridge(tmp_path, 'cp1251', {'action': 'investigate', 'question': question}, stdin=True)
    assert output.returncode == 0
    assert response['result']['question'] == question
