import argparse
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def build_program(name, prefix, work):
    source = ROOT / "programs" / f"{name}.S"
    obj = work / f"{name}.o"
    elf = work / f"{name}.elf"
    binary = work / f"{name}.bin"
    subprocess.run([
        f"{prefix}as", "-march=rv32i", "-mabi=ilp32", "-mno-relax",
        "-o", str(obj), str(source),
    ], check=True)
    subprocess.run([
        f"{prefix}ld", "-m", "elf32lriscv", "--no-relax",
        "-Ttext=0", "-e", "_start", "-o", str(elf), str(obj),
    ], check=True)
    subprocess.run([
        f"{prefix}objcopy", "-O", "binary", "-j", ".text", str(elf), str(binary),
    ], check=True)
    image = binary.read_bytes()
    if not image or len(image) % 4:
        raise ValueError(f"{name}: 指令映像必须为非空的完整 32 位字")
    if len(image) > 4096:
        raise ValueError(f"{name}: 指令映像超过 4 KiB ROM")
    words = [int.from_bytes(image[offset:offset + 4], "little")
             for offset in range(0, len(image), 4)]
    destination = ROOT / "programs" / f"{name}.coe"
    destination.write_text(
        "memory_initialization_radix=16;\n"
        "memory_initialization_vector=\n"
        + ",\n".join(f"{word:08x}" for word in words) + ";\n",
        encoding="utf-8",
    )
    print(f"{source.relative_to(ROOT)}: {len(words)} words -> {destination.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description="使用 GNU RISC-V 工具链生成真实程序 COE")
    parser.add_argument("--riscv-prefix", default=os.environ.get("RISCV_PREFIX", "riscv64-unknown-elf-"))
    args = parser.parse_args()
    work = ROOT / ".work" / "programs"
    work.mkdir(parents=True, exist_ok=True)
    for name in ("fastpow", "fib"):
        build_program(name, args.riscv_prefix, work)


if __name__ == "__main__":
    main()
