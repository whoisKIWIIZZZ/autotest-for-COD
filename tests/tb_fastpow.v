`timescale 1ns/1ps

module tb_fastpow;
    parameter EXPECT_CASES = 0;
    reg clk = 0;
    reg rstn = 0;
    integer results = 0;
    main #(.ROM_FILE("program.hex")) dut(
        .clk(clk), .rstn(rstn), .btn_i(5'b0), .sw_i(16'h0001),
        .led_o(), .disp_an_o(), .disp_seg_o()
    );
    always #5 clk = ~clk;
    initial begin
        #200 rstn = 1;
        #50000000 $fatal(1, "verification timeout");
    end
    always @(negedge dut.Clk_CPU) begin
        if (rstn) begin
            if (dut.mem_w && dut.Addr_out >= 32'h200
                    && dut.Addr_out < 32'h200 + EXPECT_CASES * 4) begin
                if (dut.Addr_out !== 32'h200 + results * 4)
                    $fatal(1, "unexpected result address");
                $display("result[%0d]=%08x", results, dut.Data_write);
                results = results + 1;
            end
            if (dut.Disp_num === 32'h8e88f9c7)
                $fatal(1, "CPU self-check displayed FAIL");
            if (dut.Disp_num === 32'h8c889292) begin
                if (results != EXPECT_CASES)
                    $fatal(1, "expected %0d results, observed %0d", EXPECT_CASES, results);
                $display("Disp_num=%08x", dut.Disp_num);
                $finish;
            end
        end
    end
endmodule
