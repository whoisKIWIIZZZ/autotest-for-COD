PYTHON ?= .venv/bin/python
RISCV_PREFIX ?= riscv64-unknown-elf-
PORT ?= 8000
KIND ?= edf
FILES ?= edf_file/SCPU.edf
STUDENT_ID ?= local
STUDENT_NAME ?= 本机评测

.PHONY: serve grade convert check programs

serve:
	$(PYTHON) server.py --port $(PORT)

# 使用 RV32I 工具链构建程序，原 testac-simple 映像保持不变。
programs:
	$(PYTHON) sim/build_programs.py --riscv-prefix "$(RISCV_PREFIX)"

grade:
	$(PYTHON) judge.py --kind $(KIND) --student-id "$(STUDENT_ID)" --student-name "$(STUDENT_NAME)" $(FILES)

convert:
	mkdir -p .work/netlist
	$(PYTHON) sim/convert_edif.py --output .work/netlist

check:
	mkdir -p .work/tmp .work/pytest
	TMPDIR="$(CURDIR)/.work/tmp" $(PYTHON) -m pytest --basetemp=.work/pytest -p no:cacheprovider tests
