"""Windows CI smoke test of the real downloaded client, always offline."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amsrfid import runtime
from amsrfid.pm3 import Pm3

if __name__ == "__main__":
    if not runtime.supported_platform():
        raise SystemExit("Windows x64 required")
    with tempfile.TemporaryDirectory(prefix="ams-runtime-") as temp:
        root = Path(temp)
        client = runtime.install(root)
        pm3 = Pm3(client=client, workdir=root / "out")
        help_result = pm3._run_subprocess([client, "-h"], 30)
        assert help_result.returncode == 0, help_result.text
        result = pm3._run_subprocess([client, "-c", "hf mf sen -h"], 30)
        # CLIExecWithReturn returns PM3_ESOFT (-10) for help as well as parse errors.
        # Windows exposes negative C exit codes as unsigned 32-bit values.
        assert result.returncode in (0, -10, 0xFFFFFFF6), (result.returncode, result.text)
        assert "--no-oob" in result.text, result.text
        print("OK: pinned Windows client starts with packaged DLLs; native SEN available (offline)")
