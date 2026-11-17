`timescale 1ns/1ps

module judge_top(
    input wire clk,
    input wire rstn,
    output wire cpu_clk,
    output wire [31:0] pc,
    output wire [31:0] display_word,
    output wire display_write,
    output wire [31:0] display_bus,
    output wire [31:0] selftest_marker,
    output wire [31:0] instruction,
    output wire [31:0] address,
    output wire [31:0] store_data,
    output wire [31:0] load_data,
    output wire mem_write,
    output wire [2:0] dm_ctrl,
    output wire cpu_rising_next,
    output wire trace_registers_available,
    output wire [319:0] trace_registers
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
    assign instruction = dut.ROM_output;
    assign address = dut.Addr_out;
    assign store_data = dut.Data_out;
    assign load_data = dut.Data_read;
    assign mem_write = dut.mem_w;
    assign dm_ctrl = dut.dm_ctrl;
    // Sample public CPU inputs before eval() advances the divided-clock edge.
    assign cpu_rising_next = rstn && !clk &&
        (dut.SW_out[2] ? dut.clkdiv[24:0] == 25'h0ffffff : dut.clkdiv[3:0] == 4'h7);
`ifdef SCPU_REFERENCE
    // These are Q nets from the trusted, flattened EDF, never student hierarchy.
    // Least-significant word first: ra, sp, s0, s1, a0-a3, s2, s3.
    assign trace_registers_available = 1'b1;
    assign trace_registers = {
        dut.U1_SCPU.\U_RF/rf_reg[19]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[18]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[13]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[12]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[11]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[10]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[9]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[8]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[2]__0 ,
        dut.U1_SCPU.\U_RF/rf_reg[1]__0
    };
`else
    assign trace_registers_available = 1'b0;
    assign trace_registers = 320'b0;
`endif
endmodule
