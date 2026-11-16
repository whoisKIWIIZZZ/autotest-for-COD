`timescale 1ns/1ps

module judge_top(
    input wire clk,
    input wire rstn,
    output wire cpu_clk,
    output wire [31:0] pc,
    output wire [31:0] display_word,
    output wire display_write,
    output wire [31:0] display_bus,
    output wire [31:0] selftest_marker
);
    // 保留原板级连线和分频器；不导出扫描引脚，使未使用的下游驱动可被优化。
    main #(.ROM_FILE("program.hex")) dut(
        .clk(clk), .rstn(rstn), .btn_i(5'b0), .sw_i(16'h0001),
        .led_o(), .disp_an_o(), .disp_seg_o()
    );
    assign cpu_clk = dut.Clk_CPU;
    assign pc = dut.PC_out;
    assign display_word = dut.Disp_num;
    assign display_write = dut.GPIOe0000000_we;
    assign display_bus = dut.Peripheral_in;
    assign selftest_marker = dut.U3_RAM_B.mem[1];
endmodule
