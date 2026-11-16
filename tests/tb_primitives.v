`timescale 1ns/1ps

module lut_truth_check #(parameter WIDTH = 1)(output reg done = 0);
    localparam ROWS = 1 << WIDTH;
    reg [5:0] pins = 0;
    wire [ROWS-1:0] decoded;
    for (genvar row = 0; row < ROWS; row = row + 1) begin: truth_row
        localparam [ROWS-1:0] MASK = {{(ROWS-1){1'b0}}, 1'b1} << row;
        if (WIDTH == 1) LUT1 #(.INIT(MASK)) cell_under_test(decoded[row], pins[0]);
        if (WIDTH == 2) LUT2 #(.INIT(MASK)) cell_under_test(decoded[row], pins[0], pins[1]);
        if (WIDTH == 3) LUT3 #(.INIT(MASK)) cell_under_test(decoded[row], pins[0], pins[1], pins[2]);
        if (WIDTH == 4) LUT4 #(.INIT(MASK)) cell_under_test(decoded[row], pins[0], pins[1], pins[2], pins[3]);
        if (WIDTH == 5) LUT5 #(.INIT(MASK)) cell_under_test(decoded[row], pins[0], pins[1], pins[2], pins[3], pins[4]);
        if (WIDTH == 6) LUT6 #(.INIT(MASK)) cell_under_test(decoded[row], pins[0], pins[1], pins[2], pins[3], pins[4], pins[5]);
    end
    integer address, bit_number;
    initial begin
        // 每个 INIT 位分别置一，穷举输入以检查真值表位序与独立性。
        for (address = 0; address < ROWS; address = address + 1) begin
            pins = 6'(address);
            #1;
            for (bit_number = 0; bit_number < ROWS; bit_number = bit_number + 1)
                if (decoded[bit_number] !== (address == bit_number))
                    $fatal(1, "LUT%0d address=%0d INIT_bit=%0d", WIDTH, address, bit_number);
        end
        done = 1;
    end
endmodule

module flip_flop_check #(
    parameter INITIAL = 1'b0,
    parameter C_INV = 1'b0,
    parameter D_INV = 1'b0,
    parameter CONTROL_INV = 1'b0,
    parameter CE_INV = 1'b0
)(output reg done = 0);
    reg clk = 0, enable = 0, data = 0, reset = 0, set_value = 0;
    wire c_pin = clk ^ C_INV;
    wire n_pin = ~clk ^ C_INV;
    wire d_pin = data ^ D_INV;
    wire r_pin = reset ^ CONTROL_INV;
    wire s_pin = set_value ^ CONTROL_INV;
    wire ce_pin = enable ^ CE_INV;
    wire [9:0] q;
    reg [9:0] expected;

    FDRE #(.INIT(INITIAL), .IS_C_INVERTED(C_INV), .IS_D_INVERTED(D_INV), .IS_R_INVERTED(CONTROL_INV))
        fdre(q[0], c_pin, enable, d_pin, r_pin);
    FDRE_1 #(.INIT(INITIAL)) fdre_1(q[1], ~clk, enable, data, reset);
    FDSE #(.INIT(INITIAL), .IS_C_INVERTED(C_INV), .IS_D_INVERTED(D_INV), .IS_S_INVERTED(CONTROL_INV))
        fdse(q[2], c_pin, enable, d_pin, s_pin);
    FDSE_1 #(.INIT(INITIAL)) fdse_1(q[3], ~clk, enable, data, set_value);
    FDRSE #(.INIT(INITIAL), .IS_C_INVERTED(C_INV), .IS_CE_INVERTED(CE_INV),
            .IS_D_INVERTED(D_INV), .IS_R_INVERTED(CONTROL_INV), .IS_S_INVERTED(CONTROL_INV))
        fdrse(q[4], c_pin, ce_pin, d_pin, r_pin, s_pin);
    FDRSE_1 #(.INIT(INITIAL), .IS_C_INVERTED(C_INV), .IS_CE_INVERTED(CE_INV),
              .IS_D_INVERTED(D_INV), .IS_R_INVERTED(CONTROL_INV), .IS_S_INVERTED(CONTROL_INV))
        fdrse_1(q[5], n_pin, ce_pin, d_pin, r_pin, s_pin);
    FDCE #(.INIT(INITIAL), .IS_C_INVERTED(C_INV), .IS_D_INVERTED(D_INV), .IS_CLR_INVERTED(CONTROL_INV))
        fdce(q[6], c_pin, enable, r_pin, d_pin);
    FDCE_1 #(.INIT(INITIAL)) fdce_1(q[7], ~clk, enable, reset, data);
    FDPE #(.INIT(INITIAL), .IS_C_INVERTED(C_INV), .IS_D_INVERTED(D_INV), .IS_PRE_INVERTED(CONTROL_INV))
        fdpe(q[8], c_pin, enable, d_pin, s_pin);
    FDPE_1 #(.INIT(INITIAL)) fdpe_1(q[9], ~clk, enable, data, set_value);

    task check;
        begin
            if (q !== expected)
                $fatal(1, "FF INIT=%b C_INV=%b D_INV=%b CONTROL_INV=%b CE_INV=%b controls=%b expected=%b actual=%b",
                       INITIAL, C_INV, D_INV, CONTROL_INV, CE_INV, {enable, data, reset, set_value}, expected, q);
        end
    endtask

    integer controls, pass;
    initial begin
        expected = {10{INITIAL}};
        #2;
        check();
        // 正反顺序各遍历一次，覆盖保持、同步/异步控制和 reset/set 优先级。
        for (pass = 0; pass < 2; pass = pass + 1) begin
            for (controls = 0; controls < 16; controls = controls + 1) begin
                {enable, data, reset, set_value} = pass ? ~4'(controls) : 4'(controls);
                if (reset) expected[7:6] = 2'b00;
                if (set_value) expected[9:8] = 2'b11;
                #2;
                check();
                clk = 1;
                if (reset) expected[1:0] = 2'b00;
                else if (enable) expected[1:0] = {2{data}};
                if (set_value) expected[3:2] = 2'b11;
                else if (enable) expected[3:2] = {2{data}};
                if (reset) expected[5:4] = 2'b00;
                else if (set_value) expected[5:4] = 2'b11;
                else if (enable) expected[5:4] = {2{data}};
                if (!reset && enable) expected[7:6] = {2{data}};
                if (!set_value && enable) expected[9:8] = {2{data}};
                #2;
                check();
                clk = 0;
                #2;
                check();
            end
        end
        done = 1;
    end
endmodule

module tb_primitives;
    wire [5:0] lut_done;
    wire [31:0] ff_done;
    for (genvar width = 1; width <= 6; width = width + 1) begin: widths
        lut_truth_check #(.WIDTH(width)) check_lut(lut_done[width-1]);
    end
    for (genvar setting = 0; setting < 32; setting = setting + 1) begin: settings
        flip_flop_check #(.INITIAL(setting[0]), .C_INV(setting[1]), .D_INV(setting[2]),
                          .CONTROL_INV(setting[3]), .CE_INV(setting[4])) check_ff(ff_done[setting]);
    end
    initial begin
        wait ((&lut_done) && (&ff_done));
        $display("PRIMITIVES PASS");
        $finish;
    end
    initial begin
        #1000;
        $fatal(1, "Primitive checks did not finish");
    end
endmodule
