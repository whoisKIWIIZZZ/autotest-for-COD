`timescale 1ns/1ps

module main #(
    parameter ROM_FILE = ".sim/smoke.hex"
)(
    input wire [4:0] btn_i,
    input wire clk,
    input wire [15:0] sw_i,
    input wire rstn,
    output wire [15:0] led_o,
    output wire [7:0] disp_an_o,
    output wire [7:0] disp_seg_o
);
    wire rst = ~rstn;
    wire [4:0] BTN_out;
    wire [15:0] SW_out;
    wire Clk_CPU;
    wire [31:0] clkdiv;
    wire [31:0] PC_out, ROM_output, Addr_out, Data_out, Data_read;
    wire [2:0] dm_ctrl;
    wire mem_w, CPU_MIO;
    wire [31:0] Cpu_data4bus, Data_write, Data_write_to_dm;
    wire [3:0] wea_mem;
    wire [9:0] ram_addr;
    wire [31:0] ram_data_out;
    wire data_ram_we;
    wire GPIOf0000000_we, GPIOe0000000_we, counter_we;
    wire [31:0] Peripheral_in;
    wire [15:0] LED_out;
    wire [1:0] counter_set;
    wire [31:0] counter_out;
    wire counter0_OUT, counter1_OUT, counter2_OUT;
    wire [31:0] Disp_num;
    wire [7:0] LE_out, point_out;

    Enter U10_Enter(
        .clk(clk), .BTN(btn_i), .SW(sw_i), .BTN_out(BTN_out), .SW_out(SW_out)
    );
    clk_div U8_clk_div(
        .clk(clk), .rst(rst), .SW2(SW_out[2]), .Clk_CPU(Clk_CPU), .clkdiv(clkdiv)
    );
    SCPU U1_SCPU(
        .clk(Clk_CPU), .reset(rst), .MIO_ready(1'b1), .INT(1'b0),
        .inst_in(ROM_output), .Data_in(Data_read), .mem_w(mem_w),
        .PC_out(PC_out), .Addr_out(Addr_out), .Data_out(Data_out),
        .dm_ctrl(dm_ctrl), .CPU_MIO(CPU_MIO)
    );
    ROM #(.INIT_FILE(ROM_FILE)) U2_ROM_D(
        .a(PC_out[31:2]), .spo(ROM_output)
    );
    dm_controller U3_dm_controller(
        .mem_w(mem_w), .Addr_in(Addr_out), .Data_write(Data_write),
        .dm_ctrl(dm_ctrl), .Data_read_from_dm(Cpu_data4bus), .Data_read(Data_read),
        .Data_write_to_dm(Data_write_to_dm), .wea_mem(wea_mem)
    );
    // MIO_BUS 已输出字地址；MMIO 写入不能同时修改 RAM。
    RAM U3_RAM_B(
        .addra(ram_addr), .clka(~clk), .dina(Data_write_to_dm),
        .wea(wea_mem & {4{data_ram_we & ~rst}}), .douta(ram_data_out)
    );
    MIO_BUS U4_MIO_BUS(
        .clk(clk), .rst(rst), .BTN(BTN_out), .SW(SW_out), .PC(PC_out),
        .mem_w(mem_w), .Cpu_data2bus(Data_out), .addr_bus(Addr_out),
        .ram_data_out(ram_data_out), .led_out(LED_out), .counter_out(counter_out),
        .counter0_out(counter0_OUT), .counter1_out(counter1_OUT), .counter2_out(counter2_OUT),
        .Cpu_data4bus(Cpu_data4bus), .ram_data_in(Data_write), .ram_addr(ram_addr),
        .data_ram_we(data_ram_we), .GPIOf0000000_we(GPIOf0000000_we),
        .GPIOe0000000_we(GPIOe0000000_we), .counter_we(counter_we),
        .Peripheral_in(Peripheral_in)
    );
    SPIO U7_SPIO(
        .clk(~Clk_CPU), .rst(rst), .EN(GPIOf0000000_we), .P_Data(Peripheral_in),
        .counter_set(counter_set), .LED_out(LED_out), .led(led_o), .GPIOf0()
    );
    Counter_x U9_Counter_x(
        .clk(~Clk_CPU), .rst(rst), .clk0(clkdiv[0]), .clk1(clkdiv[10]), .clk2(clkdiv[12]),
        .counter_we(counter_we), .counter_val(Peripheral_in), .counter_ch(counter_set),
        .counter0_OUT(counter0_OUT), .counter1_OUT(counter1_OUT),
        .counter2_OUT(counter2_OUT), .counter_out(counter_out)
    );
    Multi_8CH32 U5_Multi_8CH32(
        .clk(~Clk_CPU), .rst(rst), .EN(GPIOe0000000_we), .Switch(SW_out[7:5]),
        .point_in({32'b0, clkdiv}), .LES(64'hffff_ffff_ffff_ffff),
        .data0(Peripheral_in), .data1(Data_read), .data2(ROM_output), .data3(counter_out),
        .data4(Addr_out), .data5(Data_out), .data6(Cpu_data4bus), .data7(PC_out),
        .point_out(point_out), .LE_out(LE_out), .Disp_num(Disp_num)
    );
    SSeg7 U6_SSeg7(
        .clk(clk), .rst(rst), .SW0(SW_out[0]), .flash(clkdiv[10]),
        .Hexs(Disp_num), .point(point_out), .LES(LE_out),
        .seg_an(disp_an_o), .seg_sout(disp_seg_o)
    );
endmodule
