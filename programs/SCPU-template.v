// Copyright 1986-2018 Xilinx, Inc. All Rights Reserved.
// --------------------------------------------------------------------------------
// Tool Version: Vivado v.2018.1 (win64) Build 2188600 Wed Apr  4 18:40:38 MDT 2018
// Date        : Tue Jun 20 18:23:52 2023
// Host        : LAPTOP-E4IJ843E running 64-bit major release  (build 9200)
// Command     : write_verilog -mode synth_stub C:/Users/user/Desktop/projects/edf_file/SCPU.v
// Design      : SCPU
// Purpose     : Stub declaration of top-level module interface
// Device      : xc7a100tcsg324-1
// --------------------------------------------------------------------------------

// This empty module with port declaration file causes synthesis tools to infer a black box for IP.
// The synthesis directives are for Synopsys Synplify support to prevent IO buffer insertion.
// Please paste the declaration into a Verilog source file or add the file as an additional source.
module SCPU(clk, reset, MIO_ready, inst_in, Data_in, mem_w, 
  PC_out, Addr_out, Data_out, dm_ctrl, CPU_MIO, INT);

  input clk;
  input reset;
  input MIO_ready;//不管这个,什么都不做(不许删掉这个input)
  input [31:0]inst_in;//指令输入（来自指令存储器）
  input [31:0]Data_in;//数据输入（来自数据存储器）
  output mem_w;//memWrite
  output [31:0]PC_out;//下一条指令的PC
  output [31:0]Addr_out;//地址总线
  output [31:0]Data_out;//数据总线
  output [2:0]dm_ctrl;
  output CPU_MIO;//设置成0即可
  input INT;//不管这个,什么都不做(不许删掉这个input)

 //TODO
 /*
 dm_ctrl是控制DataMemory读字、半字等等内容,参考 edf_file/dm_controller.v
 */
endmodule
