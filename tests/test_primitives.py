import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("simulator", ["iverilog", "verilator"])
def test_lut_truth_tables_and_flip_flop_transitions(simulator, tmp_path):
    executable = shutil.which(simulator)
    if executable is None:
        pytest.skip(f"未安装 {simulator}")
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    environment = {**os.environ, "TMPDIR": str(temporary), "TMP": str(temporary), "TEMP": str(temporary)}
    sources = [str(ROOT / "sim/vendor/xilinx_cells_sim.v"), str(ROOT / "tests/tb_primitives.v")]
    if simulator == "iverilog":
        binary = tmp_path / "primitives.vvp"
        command = [executable, "-g2012", "-s", "tb_primitives", "-o", str(binary), *sources]
        runtime = [shutil.which("vvp"), str(binary)]
    else:
        build = tmp_path / "build"
        command = [executable, "--binary", "--timing", "--top-module", "tb_primitives",
                   "--Mdir", str(build), "-j", "1", "-Wno-fatal", *sources]
        runtime = [str(build / "Vtb_primitives")]
    compiled = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=180)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    simulated = subprocess.run(runtime, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    assert simulated.returncode == 0, simulated.stdout + simulated.stderr
    assert "PRIMITIVES PASS" in simulated.stdout
