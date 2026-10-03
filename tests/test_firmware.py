from pathlib import Path

import pytest

from amsrfid import firmware, pm3, web
from amsrfid.config import Config
from amsrfid.pm3 import Pm3Error, Pm3Result, FirmwareMismatch


def inspection(size):
    return Pm3Result(0, 'Available memory on this board: %s\nAll done\nHave a nice day!' % (str(size) + 'K bytes' if size else 'UNKNOWN'), '')


def written():
    return Pm3Result(0, 'Flashing...\nWriting segments for file: image.elf\nAll done\nHave a nice day!', '')


@pytest.fixture
def harness(tmp_path, monkeypatch):
    calls, stages = [], []
    cfg = Config(root=tmp_path, wait=1)
    monkeypatch.setattr(firmware.runtime, 'install', lambda *a: str(tmp_path / 'proxmark3.exe'))
    monkeypatch.setattr(firmware, 'verified_images', lambda *a: {'bootrom': tmp_path / 'bootrom.elf', 'fullimage': tmp_path / 'fullimage.elf'})
    ports = iter(['COM6', 'COM7', 'COM8', 'COM9', 'COM10'])
    monkeypatch.setattr(firmware, 'wait_port', lambda *a, **k: {'device': next(ports), 'serial': 'ICEMAN'})
    def run(responses, version='OS.......... Iceman/master/v4-gda509461b'):
        replies = iter(responses)
        def execute(self, args, timeout):
            calls.append((self.port, args))
            if '-c' in args:
                return Pm3Result(0, version, '')
            return next(replies)
        monkeypatch.setattr(pm3.Pm3, '_run_subprocess', execute)
        return firmware.repair(cfg, lambda *a: None, stages.append, confirmed=True)
    return cfg, calls, stages, run


def test_repair_bypasses_ng_handshake_and_redetects_com(harness):
    cfg, calls, stages, run = harness
    result = run([inspection(512), written(), inspection(512), written()])
    assert result['firmware_verified'] and result['port'] == 'COM10'
    assert [port for port, args in calls] == ['COM6', 'COM7', 'COM8', 'COM9', 'COM10']
    assert all('-c' not in args for port, args in calls[:-1])
    writes = [args for _, args in calls if '--image' in args]
    assert len(writes) == 2
    assert '--unlock-bootloader' in writes[0] and '--unlock-bootloader' not in writes[1]
    assert all('--force' not in args for _, args in calls)
    assert stages[-1] == 'firmware_verify'
    assert (cfg.out_path / 'firmware-repair.log').is_file()


def test_256k_is_rejected_before_any_image_write(harness):
    cfg, calls, _, run = harness
    with pytest.raises(Pm3Error, match='256KB'):
        run([inspection(256)])
    assert len(calls) == 1 and '--image' not in calls[0][1]


def test_unknown_then_256k_only_updates_bootloader(harness):
    cfg, calls, _, run = harness
    with pytest.raises(Pm3Error, match='본 펌웨어는 쓰지 않았습니다'):
        run([inspection(None), written(), inspection(256)])
    assert len(calls) == 3
    assert not any('fullimage.elf' in str(args) for _, args in calls)


def test_old_bootloader_can_report_capacity_after_update(harness):
    _, _, _, run = harness
    assert run([inspection(None), written(), inspection(512), written()])['firmware_verified']


@pytest.mark.parametrize('text', [
    'Error writing block 0 of 10\nThe flashing procedure failed\nAll done\nHave a nice day!',
    'Error: PHDR is not contained in Flash\nAll done',
    'Aborted by user\nAll done',
    'Have a nice day!',
])
def test_native_zero_exit_does_not_hide_failure(harness, text):
    cfg, calls, _, run = harness
    with pytest.raises(Pm3Error):
        run([inspection(512), Pm3Result(0, text, '')])
    assert len(calls) == 2  # No retry, no fullimage.
    assert text in (cfg.out_path / 'firmware-repair.log').read_text(encoding='utf-8')


def test_success_requires_matching_os_version(harness):
    _, calls, _, run = harness
    with pytest.raises(Pm3Error, match='OS 버전 일치'):
        run([inspection(512), written(), inspection(512), written()], version='OS.......... old-build')
    assert len(calls) == 5


def test_no_confirmation_no_runtime_or_device_access(tmp_path, monkeypatch):
    monkeypatch.setattr(firmware.runtime, 'install', lambda *a: pytest.fail('must not install'))
    with pytest.raises(Pm3Error, match='확인'):
        firmware.repair(Config(root=tmp_path))
    assert web.App(Config(root=tmp_path)).start_firmware()['ok'] is False


def test_bad_image_checksum_stops(tmp_path):
    (tmp_path / 'bootrom.elf').write_bytes(b'changed')
    with pytest.raises(Pm3Error, match='검증'):
        firmware.verified_images(str(tmp_path / 'proxmark3.exe'))


def test_multiple_boards_stop_before_opening(monkeypatch):
    monkeypatch.setattr(firmware, '_pyserial_ports', lambda: [{'device': 'COM6', 'vid': 0x9ac4, 'pid': 0x4b8f}, {'device': 'COM7', 'vid': 0x9ac4, 'pid': 0x4b8f}])
    with pytest.raises(Pm3Error, match='여러 대'):
        firmware.wait_port(1, print)


def test_capabilities_mismatch_is_specific_error(monkeypatch):
    p = pm3.Pm3(client='proxmark3.exe', port='COM6')
    output = 'Capabilities structure version sent by Proxmark3 is not the same as the one used by the client!\nERROR: cannot communicate with the Proxmark3'
    monkeypatch.setattr(p, '_run_subprocess', lambda *a: Pm3Result(1, output, ''))
    with pytest.raises(FirmwareMismatch, match='통신 규격') as e:
        p.run('hw version')
    assert 'USB를 뽑았다가' not in str(e.value)
