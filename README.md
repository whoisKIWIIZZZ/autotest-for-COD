# autotest for COD

Behavior simulation using Verilator. 
Contributed @[whoisKIWIIZZZ](https://github.com/whoisKIWIIZZZ),@[Larry](https://github.com/Larryyyyyyy).

Cases:
- Fast Exponentiation. [Check this](./programs/fastpow.coe) [and this](./programs/fastpow.S).
- Fib.[Check this](./programs/fib.coe) [and this](./programs/fib.S).
- testAC. [Check this](./programs/testac-simple.coe) [and this](./programs/testac-simple.S). Hard case.

| 用例 | 源码与映像 | 成功显示 | 程序自检 |
| --- | --- | --- | --- |
| `fastpow` | `fastpow.S`、`fastpow.coe` | PASS（`0x8c889292`） | 快速幂 `2^10 = 1024`,32 位移位加法乘法与递归调用 |
| `fib` | `fib.S`、`fib.coe` | PASS（`0x8c889292`） | 递归 `fib(5) = 8`,`fib(0) = fib(1) = 1` |
| `testac-simple` | `testac-simple.S`、`testac-simple.coe` | AC（`0xff88c6ff`） | 原 testac 程序,首次完整显示 AC 即通过 |

## Submit
Your CPU should be warpped in the file like [this](./programs/SCPU-template.v).
Some to note:
- the CPU doesn't contain the DataMemory Module. However, it wrapped in `dm_controller.v` in [here](./edf_file/dm_controller.v).
- you **should not** submit ROM/RAM/clk_div file.
- Remember, this is just **behavioral simulation**. This just test whether your CPU is logically right, which ignoring timing constraints.

## eval offline

**Only tested in Unix-based OS!**

```sh
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make serve
```

open `http://127.0.0.1:8000/`.

Or you could test CLI:

```sh
make grade KIND=edf FILES=edf_file/SCPU.edf STUDENT_ID=demo STUDENT_NAME=调试
make grade KIND=rtl FILES="core/SCPU.v core/alu.v" # of course, FILE should include all your SCPU files.
.venv/bin/python judge.py --kind edf edf_file/SCPU.edf --cases testac
```

`make check` 运行判定、存储及 Icarus/Verilator 原语行为测试.`make convert` 执行 EDF 到 Verilog 转换.`testac-simple` 保留原汇编、COE 和延时循环.运行 `make programs` 使用 GNU RISC-V 工具链重新生成快速幂与 fib 映像,默认前缀为 `riscv64-unknown-elf-`,可通过 `RISCV_PREFIX` 修改.快速幂通过 RV32I 移位加法计算乘积的低 32 位,保留三层展开和递归栈帧.

As for students, you could ignore `edf`.


## 失败诊断

失败用例会与可信 `edf_file/SCPU.edf` 复放结果逐 CPU 周期比较，保存首个差异及双方前后各 10 条指令。学生页面和后台分别展示 `[预期行为]`、`[错误行为]`，运行文件提供 `first_diff.txt`、`first_diff.json` 下载。

比较 PC 转移、写使能、显示字及有效访存行为。参考寄存器取自 EDF 触发器；提交侧展示 SCPU 公开接口。流水线或停顿策略会影响首差位置，诊断不参与成绩判定。编译失败、执行证据缺失及复放错误会说明具体原因。

复放通过有界管道传输，只保存最多 21 条记录的窗口；参考模型按内容缓存。历史失败记录可运行 `.venv/bin/python sim/backfill_diagnostics.py` 补充诊断，原成绩和评测时间保持不变。详见 [服务器说明](./docs/server-README.md#首差异诊断)。

## APIs

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/config` | 题目、文件上限、允许类型、CPU 时钟、默认 `cases` |
| POST | `/api/runs` | `multipart/form-data`：`student_id`、`student_name`、`kind`、重复 `files` |
| GET | `/api/runs` | 当前浏览器 owner cookie 的历史记录 |
| GET | `/api/runs/{id}` | 记录详情、逐例 `cases`、当前 `active_case` 与最终结果 |
| GET | `/api/runs/{id}/events?case_id=…` | 所选用例的真实帧、`case_complete` 及整次运行 `complete`；省略参数时选择活动例或首例 |
| GET | `/api/runs/{id}/log?offset=…` | 增量日志 |
| GET | `/api/runs/{id}/artifacts` | 归档文件索引 |
| GET | `/api/runs/{id}/files/{path}` | 下载归档文件 |
| GET | `/api/leaderboard` | 公开排行与汇总 |
| GET | `/api/dashboard/runs` | 后台列表与统计,需 Bearer token |
| GET | `/api/dashboard/runs/{id}` | 后台详情、日志大小、文件索引 |
| GET | `/api/dashboard/runs/{id}/log`、`…/files/{path}` | 后台日志与下载,需 Bearer token |

## Server

依赖 Python ≥ 3.11、带 `--no-timing` 的 Verilator ≥ 5、`g++`/`make`、`bubblewrap`.服务监听地址和 Host 白名单通过参数与环境变量设置：

```sh
SCPU_ALLOWED_HOSTS=203.0.113.10,localhost,127.0.0.1 SCPU_BUILD_JOBS=1 \
  .venv/bin/python server.py --host 0.0.0.0 --port 8100
```

`SCPU_BUILD_JOBS` 控制 Verilator 构建并行度,默认 1.CentOS 8 的 GCC 8 在 ASLR 下无法复用 Verilator 生成的预编译头,会报 `had text segment at different address` 和 `PCH ... invalid`；需要把 `/usr/local/share/verilator/include/verilated.mk` 中的 `CXX = g++` 改为 `CXX = setarch x86_64 -R g++`（重装 Verilator 后需重新设置）.未设置 `SCPU_ALLOWED_HOSTS` 时只接受本机访问.超时上限为编译 20 分钟、仿真 90 分钟、整次运行 2 小时.服务器实测性能见下节.

## wtf is this

- 编译和仿真都在沙箱内运行：macOS 使用 `sandbox-exec`,Linux 使用 `bubblewrap`（`--unshare-all`,独立网络命名空间,根文件系统只读）.写入仅限本次运行目录（编译：`work/`、`tmp/`；仿真：`work/runtime/`、`tmp/`）,网络全部禁止；macOS 仿真进程只能执行自身,不能再 fork.
- 源文件检查拒绝 `force`/`release`/`bind`、DPI、`protect` 等控制指令,`include` 只能引用本次提交内的文件；提交的 RTL 先做 Verilator 预处理再复查,宏不能绕过后置检查.
- EDF 提交必须顶层为 `SCPU`、只含支持的原语；转换器校验标识符和 `INIT` 数值属性,防止网表注入生成代码.


## Acknowlegement

- [SpyDrNet 1.13.0](https://byuccl.github.io/spydrnet/docs/stable/)
- [Verilator 诊断说明](https://verilator.org/guide/latest/warnings.html)
- [Yosys Xilinx cells_sim.v,固定修订 198bf261fc65ebfa1413f199f536d6009d21d323](https://github.com/YosysHQ/yosys/blob/198bf261fc65ebfa1413f199f536d6009d21d323/techlibs/xilinx/cells_sim.v)

