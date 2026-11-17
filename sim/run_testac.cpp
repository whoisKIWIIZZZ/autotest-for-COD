#include "Vjudge_top.h"
#include "verilated.h"
#include "monitor_config.h"
#include "trace_stream.h"

#include <chrono>
#include <cinttypes>
#include <cstdio>
#include <cstring>

namespace {

void step_board(VerilatedContext& context, Vjudge_top& top, uint64_t& half_ticks) {
    // Each full-board half-tick is 5 ns (the model precision is 1 ps).
    context.timeInc(5000);
    ++half_ticks;
    top.clk = !top.clk;
    top.eval();
}

bool parse_cycle_limit(const char* text, uint64_t& value) {
    if (!text || !*text) return false;
    value = 0;
    for (const char* p = text; *p; ++p) {
        if (*p < '0' || *p > '9') return false;
        const unsigned digit = static_cast<unsigned>(*p - '0');
        if (value > (UINT64_MAX - digit) / 10) return false;
        value = value * 10 + digit;
    }
    return value != 0;
}

int replay_stream(int argc, char** argv, uint64_t max_cycles) {
    TraceStream stream;
    if (!stream.open_fifo(argv[4])) return stream.cancelled() ? 0 : 2;
    VerilatedContext context;
    context.commandArgs(argc, argv);
    Vjudge_top top{&context};
    uint64_t half_ticks = 0, cycles = 0;
    bool simulator_failed = false;
    top.clk = 0;
    top.rstn = 0;
    top.eval();
    // Exactly the normal grader reset, even when the submitted reset PC is bad.
    for (int i = 0; i < 40 && !context.gotFinish() && !context.gotError(); ++i) {
        step_board(context, top, half_ticks);
    }
    if (!context.gotFinish() && !context.gotError()) {
        top.rstn = 1;
        top.eval();
    }
    uint32_t record[TraceStream::RECORD_WORDS] = {};
    while (cycles < max_cycles && !context.gotFinish() && !context.gotError()) {
        const bool rising = top.cpu_rising_next;
        const bool old_cpu_clk = top.cpu_clk;
        if (rising) {
            record[4] = top.pc;
            record[6] = top.instruction;
            record[7] = top.address;
            record[8] = top.store_data;
            record[9] = top.load_data;
            record[10] = top.mem_write;
            record[11] = top.dm_ctrl;
        }
        step_board(context, top, half_ticks);
        if (rising != (!old_cpu_clk && top.cpu_clk)) {
            std::fprintf(stderr, "trace replay: board CPU edge prediction mismatch\n");
            simulator_failed = true;
            break;
        }
        if (rising) {
            ++cycles;
            const uint64_t time_ns = half_ticks * 5;
            record[0] = static_cast<uint32_t>(cycles);
            record[1] = static_cast<uint32_t>(cycles >> 32);
            record[2] = static_cast<uint32_t>(time_ns);
            record[3] = static_cast<uint32_t>(time_ns >> 32);
            record[5] = top.pc;
            record[12] = top.display_word;
            record[13] = top.trace_registers_available ? 1U : 0U;
            if (top.trace_registers_available) {
                for (size_t i = 0; i < 10; ++i) record[14 + i] = top.trace_registers[i];
            }
            if (!stream.append_record(record)) break;
        }
    }
    if (context.gotFinish() || context.gotError()) {
        std::fprintf(stderr, "trace replay: simulator stopped unexpectedly at cycle %" PRIu64 "\n", cycles);
        simulator_failed = true;
    }
    top.final();
    const bool completed = stream.finish();
    if (stream.cancelled()) return 0;
    if (!completed) return 2;
    return simulator_failed ? 3 : 0;
}

int usage(const char* program) {
    std::fprintf(stderr,
        "usage: %s --case CASE [--stream FIFO_PATH --max-cycles POSITIVE_INTEGER]\n", program);
    return 2;
}

}  // namespace

int main(int argc, char** argv) {
    if ((argc != 3 && argc != 7) || std::strcmp(argv[1], "--case") != 0) return usage(argv[0]);
    uint64_t replay_cycles = 0;
    if (argc == 7 && (std::strcmp(argv[3], "--stream") != 0 || !*argv[4]
            || std::strcmp(argv[5], "--max-cycles") != 0
            || !parse_cycle_limit(argv[6], replay_cycles))) return usage(argv[0]);
    const CaseSpec* selected = nullptr;
    for (const auto& candidate : CASE_SPECS) {
        if (std::strcmp(argv[2], candidate.id) == 0) selected = &candidate;
    }
    if (!selected) {
        std::fprintf(stderr, "unknown case: %s\n", argv[2]);
        return 2;
    }
    if (argc == 7) return replay_stream(argc, argv, replay_cycles);
    const CaseSpec& spec = *selected;
    const bool program_test = std::strcmp(spec.id, "fastpow") == 0 || std::strcmp(spec.id, "fib") == 0;
    VerilatedContext context;
    context.commandArgs(argc, argv);
    Vjudge_top top{&context};
    FILE* frames = std::fopen("frames.jsonl", "w");
    if (!frames) return 2;
    const auto start = std::chrono::steady_clock::now();
    uint64_t cycles = 0, half_ticks = 0, last_progress = 0, same_pc = 0;
    uint32_t previous_pc = 0, previous_display = 0, last_bus = 0, pending_pc = 0;
    size_t index = 0;
    bool pending = false, held_write = false;
    const char* status = "time_limit";
    const char* reason = "cycle_limit";
    auto step = [&]() {
        step_board(context, top, half_ticks);
    };
    top.clk = 0;
    top.rstn = 0;
    top.eval();
    for (int i = 0; i < 40; ++i) step();
    if (top.pc != 0) {
        status = "wrong_answer";
        reason = "reset_pc";
    } else {
        top.rstn = 1;
        top.eval();
        previous_display = top.display_word;
        while (cycles < spec.max_cycles) {
            const bool old_cpu_clk = top.cpu_clk;
            const bool write_before = top.display_write;
            const uint32_t bus_before = top.display_bus;
            const uint32_t pc_before = top.pc;
            step();
            if (!old_cpu_clk && top.cpu_clk) ++cycles;
            if (top.pc == spec.failure_pc || pc_before == spec.failure_pc) {
                status = "wrong_answer";
                reason = "failure_pc";
                break;
            }
            if (context.gotFinish() || context.gotError()) {
                status = "wrong_answer";
                reason = "unexpected_finish";
                break;
            }
            if (!old_cpu_clk && top.cpu_clk) {
                if (top.pc == previous_pc) ++same_pc;
                else same_pc = 0;
                previous_pc = top.pc;
                if ((top.pc & 3) || top.pc >= 4096) {
                    status = "wrong_answer";
                    reason = "invalid_pc";
                    break;
                }
                if (same_pc >= 1000000) {
                    status = "wrong_answer";
                    reason = "stuck_pc";
                    break;
                }
                if (cycles - last_progress > spec.max_frame_gap) {
                    status = "time_limit";
                    reason = "display_progress_timeout";
                    break;
                }
            }
            if (old_cpu_clk && !top.cpu_clk) {
                // 两级显示寄存器：前一拍写入在本拍到达 Disp_num。
                if (pending || top.display_word != previous_display) {
                    const uint32_t actual = top.display_word;
                    const uint32_t frame_pc = pending ? pending_pc : pc_before;
                    const char* phase = program_test ? "program" : index < 6 ? "selftest" : "animation";
                    std::fprintf(frames,
                        "{\"index\":%zu,\"cycle\":%" PRIu64 ",\"time_ns\":%" PRIu64
                        ",\"pc\":\"%08x\",\"word\":\"%08x\",\"phase\":\"%s\"}\n",
                        index, cycles, half_ticks * 5, frame_pc, actual, phase);
                    std::fflush(frames);
                    std::printf("[%s] 显示帧 %zu，周期 %" PRIu64 "，PC=%08x，Disp_num=%08x\n",
                                spec.id, index, cycles, frame_pc, actual);
                    std::fflush(stdout);
                    const size_t recorded = index++;
                    if (!pending) {
                        status = "wrong_answer";
                        reason = "unsolicited_display_change";
                        break;
                    }
                    if (program_test && actual == FAIL_WORD) {
                        status = "wrong_answer";
                        reason = "failure_display";
                        break;
                    }
                    if (spec.full_animation) {
                        if (recorded >= EXPECTED_COUNT || actual != EXPECTED_WORDS[recorded]) {
                            status = "wrong_answer";
                            reason = "display_sequence";
                            break;
                        }
                        if (recorded >= 6 && top.selftest_marker != 0xaa123456) {
                            status = "wrong_answer";
                            reason = "selftest_marker";
                            break;
                        }
                    }
                    last_progress = cycles;
                    if ((spec.full_animation && index == EXPECTED_COUNT)
                            || (!spec.full_animation && actual == spec.success_word)) {
                        status = "accepted";
                        reason = spec.full_animation ? "full_animation_loop" : "display_success";
                        break;
                    }
                    if (index >= MAX_RECORDED_FRAMES) {
                        status = "wrong_answer";
                        reason = "display_frame_limit";
                        break;
                    }
                }
                // 保持中的同一写事务只计一次，独立的同值写事务分别记录。
                pending = write_before && (!held_write || bus_before != last_bus);
                pending_pc = pc_before;
                held_write = write_before;
                last_bus = bus_before;
                previous_display = top.display_word;
            }
        }
    }
    top.final();
    std::fclose(frames);
    const double duration = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    FILE* result = std::fopen("monitor_result.json", "w");
    if (!result) return 2;
    std::fprintf(result,
        "{\"case_id\":\"%s\",\"status\":\"%s\",\"reason\":\"%s\",\"cycles\":%" PRIu64
        ",\"frames\":%zu,\"pc\":\"%08x\",\"display_word\":\"%08x\",\"duration_seconds\":%.6f}\n",
        spec.id, status, reason, cycles, index, top.pc, top.display_word, duration);
    std::fclose(result);
    std::printf("[%s] 原生监测结束：%s，原因=%s，周期=%" PRIu64 "\n", spec.id, status, reason, cycles);
    return 0;
}
