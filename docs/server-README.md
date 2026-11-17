# SCPU 自动评测

学生提交 SCPU（RTL 多文件，或调试用 EDF 网表）。评测器提供 `main`、总线、外设、ROM 和测试程序，用 Verilator 编译整套板级逻辑，默认依次执行快速幂、递归 fib、testac-simple。各程序通过真实 `Disp_num` 寄存器写入给出结果，三个程序全部通过计 100 分。每次提交保留独立目录、完整日志、全部产物和 SQL 记录。

## 本地启动

```sh
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make serve
```

打开 `http://127.0.0.1:8000/`。命令行评测：

```sh
make grade KIND=edf FILES=edf_file/SCPU.edf STUDENT_ID=demo STUDENT_NAME=调试
make grade KIND=rtl FILES="core/SCPU.v core/alu.v"
```

`make check` 运行判定、存储及 Icarus/Verilator 原语行为测试。`make convert` 执行 EDF 到 Verilog 转换。

三个程序的源码和映像集中在 `programs/`：

| 用例 | 源码与映像 | 成功显示 | 程序自检 |
| --- | --- | --- | --- |
| `fastpow` | `fastpow.S`、`fastpow.coe` | PASS（`0x8c889292`） | 快速幂 `2^10 = 1024`，32 位移位加法乘法与递归调用 |
| `fib` | `fib.S`、`fib.coe` | PASS（`0x8c889292`） | 递归 `fib(5) = 8`，`fib(0) = fib(1) = 1` |
| `testac-simple` | `testac-simple.S`、`testac-simple.coe` | AC（`0xff88c6ff`） | 原 testac 程序，首次完整显示 AC 即通过 |

`testac-simple` 保留原汇编、COE 和延时循环。运行 `make programs` 使用 GNU RISC-V 工具链重新生成快速幂与 fib 映像，默认前缀为 `riscv64-unknown-elf-`，可通过 `RISCV_PREFIX` 修改。快速幂通过 RV32I 移位加法计算乘积的低 32 位，保留三层展开和递归栈帧。

命令行可指定用例，例如执行完整 AC 动画：

```sh
.venv/bin/python judge.py --kind edf edf_file/SCPU.edf --cases testac
```

## 评测规则

- 提交必须是 `SCPU` 顶层，端口与 `main.v` 中的实例一致；外设、ROM、存储器、分频器和测试程序由评测器提供，提交内容不能替换它们。
- 板级时钟保持 100 MHz，CPU 走原 `clk_div`（`clkdiv[3]`，6.25 MHz），完整执行原程序的全部延时循环与分频边沿。
- 显示证据取 `Multi_8CH32` 两级寄存器之后的 `Disp_num`，记录真实 CPU 周期与仿真时间。
- 一次提交编译一次，按 `fastpow`、`fib`、`testac-simple` 顺序分别启动仿真进程；各例独立复位 CPU、初始化 RAM、记录显示帧和计时。某例程序执行失败后继续执行其余例子。
- 快速幂与 fib 自检结果后向数码管写入 PASS；写入 FAIL（`0x8e88f9c7`）立即判该例 `wrong_answer`。
- `testac-simple` 在实际 `Disp_num` 首次达到 `0xff88c6ff` 时通过。其失败循环 `PC=0x218` 立即判 `wrong_answer`。
- 命令行可选 `testac` 复用同一程序映像，验证六项启动自检、AC 成形及完整动画：89 个实际显示帧，循环区间 72 帧，右移 4 次、闪烁 8 次。
- 各例保留非法 PC、长时间停滞、显示长时间无进展和周期上限检查，并写入日志。
- 结果是 `accepted`（100 分）、`wrong_answer`/`compile_error`/`time_limit`（0 分），环境问题为 `judge_error`（不计分）。

## 首差异诊断

`wrong_answer`、`time_limit` 用例在原评测结束后，使用原提交二进制和可信 CPU EDF 分别复放。两侧均执行真实板级逻辑、相同 ROM 和复位时序，六份 EDF 用于构建参考模型。比较器通过两个 FIFO 读取固定长度二进制记录，保留最近 10 条匹配记录；找到首差后收集其后 10 条记录，再关闭管道。后续记录只用于上下文，不再计算差异。每侧窗口最多 21 条，完整执行流不写入磁盘。

比较项为 PC、next_pc、指令、写使能、显示字，以及 load/store 的有效地址、访存控制和读写数据。SB/SH 仅比较有效的低 8/16 位写数据；非访存指令的总线值只作上下文。每条记录的指令、PC 和访存信号采于 CPU 上升沿前，next_pc、显示字与参考寄存器采于上升沿后。按 CPU 周期进行比较，流水线或停顿策略可能改变首差位置；该诊断不参与成绩判定。

可信 EDF 可读取实际触发器中的 ra、sp、s0/s1、a0–a3、s2/s3。通用提交 CPU 没有标准 RF 接口，错误侧展示其公开信号，寄存器字段为 null。编译失败、缺少执行周期或原始归档、复放环境错误均输出原因；仅已比较前缀相同的报告使用 `identical_prefix` 状态。执行起点或结束处不足十条上下文时保留实际可用条数。

每例 `work/runtime/<case_id>/first_diff.json` 和 `first_diff.txt` 保存窗口、首次差异字段、参考 EDF SHA-256、参考构建键和 ROM SHA-256。结果中的 `cases[].first_diff` 提供页面所需数据，顶层 `first_diff` 指向首个失败用例的报告。学生页和后台展示 `[预期行为]`、`[错误行为]`，并提供原有归档下载。任务在编译或控制阶段终止时，`work/runtime/run/` 保存不可用说明。

参考模型只在需要失败复放时构建，内容缓存位于 `.work/first-diff-reference/`。缓存键覆盖模型源码、转换器、六份 EDF、监测配置、Verilator 版本及架构；复用前检查二进制 SHA-256。缓存二进制复制进该次运行后按原沙箱规则执行。每个运行仍保留自己的输入快照和诊断文件。

补充所有历史失败记录：

```sh
.venv/bin/python sim/backfill_diagnostics.py
# 也可指定一条历史记录
.venv/bin/python sim/backfill_diagnostics.py --run-id 10
```

补充程序等待线上评测空闲，复用原归档中的板级源码、外设和实际 ROM，重新编译原提交以启用传输器，只更新诊断、文件索引与结果 JSON。原状态、分数和评测时间保持不变。已存在诊断的记录跳过。

## 运行归档与数据库

每次运行写入 `data/runs/<时间戳>-<随机串>/`：

- `submission/`：上传的原文件；`submission.json` 记录文件名、大小、SHA-256 和本次 `suite`。
- `logs/run.log`：评测器 stdout/stderr，包含编译命令、完整编译输出、各例显示帧和最终结论。
- `work/src`、`work/edf`、`work/netlist`、`work/build`：可信源码与程序快照、外设 EDF、转换后的网表和一次构建的 Verilator 产物。
- `work/runtime/<case_id>/`：每例独立的 `program.hex`、`frames.jsonl`、`monitor_result.json` 和 `result.json`；`work/runtime/progress.json` 提供实时逐例状态。
- `tmp/`：该次运行的临时目录（`TMPDIR`/`TMP`/`TEMP`）。
- `result.json`、`manifest.json`：最终结果与全部文件的大小和 SHA-256。

最终结果的 `suite` 保存用例顺序，`cases` 保存各例状态、检查项、周期、耗时、实际帧数、原生监测结果和成功显示码；顶层 `cycles` 为各例周期之和。全部用例均有通过证据时可记 100 分。历史单程序运行仍按原归档读取。

SQLite 数据库 `data/submissions.sqlite3` 保存两类表：

- `runs`：学号、姓名、`kind`（`rtl`/`edf`）、`is_debug`、状态、分数、摘要、时间、`duration_seconds`、`directory`、`result_json` 等。
- `artifacts`：每个运行的相对路径、大小、SHA-256；页面下载与后台审计都以此为准。

`kind=edf` 会强制 `is_debug=1`，结果中标为 **EDF 调试成绩**，不会冒充 RTL 正式成绩。服务重启时，遗留的排队或运行中记录会被标记为 `interrupted`，已有日志和文件保留。

## 页面

- `/`：学号/姓名、RTL 或 EDF 调试模式、多文件选择、三个程序的独立结果与检查项、历史记录。选择测试程序可切换其真实显示帧回放（四字节七段码，低电平点亮，位 0–6 为 a–g）；各例时间独立，支持逐帧滑杆。具有完整循环证据的用例提供循环回放。页面另提供增量日志和全部产物下载。
- `/leaderboard`：公开排行榜，不需要 token。只统计有分数的 RTL 正式提交，按最高分、通过次数、首次通过时间排序；`judge_error`/`interrupted` 这类未计分记录不参与排名，EDF 调试提交只显示总次数。
- `/dashboard`：需要 token。首次启动生成 `data/dashboard-token`（权限 0600，启动时打印文件路径），也可用 `SCPU_DASHBOARD_TOKEN` 覆盖。可查看全部运行、按学号/类型/成绩属性/状态筛选、逐项检查、完整日志和任意产物下载；下载走 `Authorization` 请求，不依赖 owner cookie。

静态资源使用页面中的 `v` 查询参数指定版本；修改脚本或样式时同步更新该版本。

## 主要接口

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
| GET | `/api/dashboard/runs` | 后台列表与统计，需 Bearer token |
| GET | `/api/dashboard/runs/{id}` | 后台详情、日志大小、文件索引 |
| GET | `/api/dashboard/runs/{id}/log`、`…/files/{path}` | 后台日志与下载，需 Bearer token |

## 部署（Linux）

依赖 Python ≥ 3.11、带 `--no-timing` 的 Verilator ≥ 5、`g++`/`make`、`bubblewrap`。服务监听地址和 Host 白名单通过参数与环境变量设置：

```sh
SCPU_ALLOWED_HOSTS=203.0.113.10,localhost,127.0.0.1 SCPU_BUILD_JOBS=1 \
  .venv/bin/python server.py --host 0.0.0.0 --port 8100
```

`SCPU_BUILD_JOBS` 控制 Verilator 构建并行度，默认 1。CentOS 8 的 GCC 8 在 ASLR 下无法复用 Verilator 生成的预编译头，会报 `had text segment at different address` 和 `PCH ... invalid`；需要把 `/usr/local/share/verilator/include/verilated.mk` 中的 `CXX = g++` 改为 `CXX = setarch x86_64 -R g++`（重装 Verilator 后需重新设置）。未设置 `SCPU_ALLOWED_HOSTS` 时只接受本机访问。超时上限为编译 20 分钟、仿真 90 分钟、整次运行 2 小时。服务器实测性能见下节。

## 仿真性能

`sim/vendor/xilinx_cells_sim.v` 的 `VERILATOR` 二态分支采用直接 `INIT` 位索引计算 LUT1–LUT6，并以阻塞赋值设置触发器初值，减少多级选择器临时节点和逐位多驱动调度。`INIT`、时钟边沿、使能、复位/置位及其反相参数保持原定义。Icarus 使用上游四态选择器和初始化调度。

`tests/tb_primitives.v` 穷举 LUT1–LUT6 的所有输入和单独置一的 `INIT` 位；十类触发器覆盖两种初值、时钟/数据/控制/使能反相、保持以及同步/异步 reset/set 优先级。两种实际仿真器分别执行这些检查。

服务器 `113.44.180.58`（2 vCPU、3736 MiB RAM）使用提交 2 的同一份 EDF、ROM 和监测器完成全循环实测：

| 纯仿真耗时 | 原模型 | 优化模型 |
| --- | ---: | ---: |
| 秒 | 2157.05 | 515.23 |

提速 4.19 倍。两次均执行 82,141,122 个 CPU 周期并判定 `accepted`；89 帧的显示值、PC、周期、仿真时间逐项一致。优化构建与完整仿真合计约 9 分钟。失败路径实测仍在 `PC=0x218` 的第 1 个 CPU 周期判定 `wrong_answer`。

## 隔离

- 编译和仿真都在沙箱内运行：macOS 使用 `sandbox-exec`，Linux 使用 `bubblewrap`（`--unshare-all`，独立网络命名空间，根文件系统只读）。写入仅限本次运行目录（编译：`work/`、`tmp/`；仿真：`work/runtime/`、`tmp/`），网络全部禁止；macOS 仿真进程只能执行自身，不能再 fork。
- 源文件检查拒绝 `force`/`release`/`bind`、DPI、`protect` 等控制指令，`include` 只能引用本次提交内的文件；提交的 RTL 先做 Verilator 预处理再复查，宏不能绕过后置检查。
- EDF 提交必须顶层为 `SCPU`、只含支持的原语；转换器校验标识符和 `INIT` 数值属性，防止网表注入生成代码。

## 三程序实测

本机网页提交 `edf_file/SCPU.edf`，一次构建后完成三个独立程序：

| 用例 | 结果 | CPU 周期 | 实际显示帧数 | 最终显示字 |
| --- | --- | ---: | ---: | --- |
| `fastpow` | `accepted` | 170 | 1 | `8c889292`（PASS） |
| `fib` | `accepted` | 183 | 1 | `8c889292`（PASS） |
| `testac-simple` | `accepted` | 10136150 | 17 | `ff88c6ff`（AC） |

总周期为 10136503，三个程序全部通过，成绩为 100。首次完整 AC 在第 17 个实际显示帧出现，`testac-simple` 随即通过。可选 `testac` 另已执行 82141122 个 CPU 周期，完成 89 帧动画并通过。

本次运行 `tests/test_cases.py`、`tests/test_storage.py`、`tests/test_native_monitor.py`：31 项通过。`tests/test_programs.py` 另通过实际 CPU EDF 与 Icarus 检查 10 组快速幂输入，覆盖零指数、零底数、负底数、奇偶指数和 32 位溢出。

## 原完整动画验证记录

真实网页提交（本机 Chromium）：

- EDF 调试提交：`accepted`，EDF 调试成绩 100，101 个归档文件，621.06 秒，82,141,122 个 CPU 周期。
- 两文件 RTL 提交（`SCPU.v` 包含 `SCPU_core.vh`）：`accepted`，RTL 成绩 100，103 个归档文件，589.84 秒，同样的 82,141,122 个周期。
- 两次运行都记录 89 帧，循环区间 16→88（72 帧），右移 4 次，闪烁 8 次；关键位置帧为 `ff88c6ff`、`ffff88c6`、`c6ffff88`、`88c6ffff`，首尾同帧。
- 归档校验：`artifacts` 索引与磁盘文件集合一致，逐文件 SHA-256 匹配；日志包含 `原因=full_animation_loop` 与 `status=accepted score=100`。
- 排行榜只显示该 RTL 学生 1 人，EDF 调试提交显示为 3 次且不进入排名。
- 同一页面上的第三次 EDF 提交也得到 `accepted`（100 分，588.4 秒），说明判定可重复。
- 后台无 token 与错误 token 均返回 401；有效 token 可查看检查项、读取 1.05 MiB 日志、下载 `result.json`（1326 字节）；运行中的记录日志按增量持续增长。
- 后台筛选实测：EDF 3 条、正式成绩 2 条、`compile_error` 1 条、按学号搜索 1 条；窄屏排行榜保留列宽并横向滚动。
- 沙箱实测：运行目录内写入成功，目录外写入 `Operation not permitted`。

确定性测试：`tests/test_cases.py` 覆盖首次完整 AC 通过、部分字符与 FAIL 拒绝、失败 PC、时间顺序；`tests/test_native_monitor.py` 检查可选完整动画用例的显示序列、闭环、闪烁、方向、时间与失败 PC；`tests/test_storage.py` 检查逐例证据完整性和周期合计、EDF 与正式排行分离、最高分保留、统计和归档路径。

## 边界

零延迟功能仿真，仅为二态（不含 `X/Z` 传播）；不含器件时序、扫描引脚波形和中断行为。ROM/RAM 是补充的功能实现，原存储器 IP 配置未提供。原 `IO/Counter_3_IO.v` 的通道 1、2 执行逻辑被注释，相关输出未初始化。

## 上游来源

- [SpyDrNet 1.13.0](https://byuccl.github.io/spydrnet/docs/stable/)
- [Verilator 诊断说明](https://verilator.org/guide/latest/warnings.html)
- [Yosys Xilinx cells_sim.v，固定修订 198bf261fc65ebfa1413f199f536d6009d21d323](https://github.com/YosysHQ/yosys/blob/198bf261fc65ebfa1413f199f536d6009d21d323/techlibs/xilinx/cells_sim.v)

当前原语模型（含二态仿真优化）SHA-256：`8994eef8e534c9113dbe5e0764aa9ca6f59e99cfd808d793075eb8324088cf55`。
