import argparse
from pathlib import Path
import re


def load_coe(path):
    text = "\n".join(line for line in path.read_text().splitlines()
                     if not line.lstrip().startswith(";"))
    radix_match = re.search(r"memory_initialization_radix\s*=\s*(\d+)\s*;", text, re.I)
    vector_match = re.search(r"memory_initialization_vector\s*=\s*([^;]+);", text, re.I)
    if radix_match is None or vector_match is None:
        raise ValueError(f"Missing COE radix or vector: {path}")
    radix = int(radix_match[1])
    if radix not in (2, 10, 16):
        raise ValueError(f"Unsupported COE radix: {radix}")
    words = [int(value.strip(), radix) for value in vector_match[1].split(",")]
    if any(word < 0 or word > 0xffffffff for word in words):
        raise ValueError("COE values must fit in a 32-bit word")
    return words


def main():
    parser = argparse.ArgumentParser(description="Convert a 32-bit COE ROM image to readmemh")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    words = load_coe(args.source)
    if len(words) > 1024:
        raise ValueError("COE image exceeds the 4 KiB instruction ROM")
    image = words + [0x00000013] * (1024 - len(words))
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text("".join(f"{word:08x}\n" for word in image))
    print(f"{args.source}: {len(words)} words ({len(words)*4} bytes) -> {args.destination}")


if __name__ == "__main__":
    main()
