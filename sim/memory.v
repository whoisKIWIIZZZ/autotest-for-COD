`timescale 1ns/1ps

module ROM #(
    parameter INIT_FILE = "testac.hex"
)(
    input wire [29:0] a,
    output wire [31:0] spo
);
    reg [31:0] mem [0:1023];
    integer i;
    integer file_handle;
    initial begin
        for (i = 0; i < 1024; i = i + 1)
            mem[i] = 32'h00000013;
        file_handle = $fopen(INIT_FILE, "r");
        if (file_handle == 0)
            $fatal(1, "Cannot open ROM image: %s", INIT_FILE);
        $fclose(file_handle);
        $readmemh(INIT_FILE, mem);
    end
    assign spo = (a < 1024) ? mem[a[9:0]] : 32'hxxxxxxxx;
endmodule

module RAM(
    input wire [9:0] addra,
    input wire clka,
    input wire [31:0] dina,
    input wire [3:0] wea,
    output reg [31:0] douta
);
    reg [31:0] mem [0:1023];
    integer i;
    integer lane;
    initial begin
        douta = 0;
        for (i = 0; i < 1024; i = i + 1)
            mem[i] = 0;
    end
    // 同步读取、按字节写入；同地址读写时读出写入前的值。
    always @(posedge clka) begin
        for (lane = 0; lane < 4; lane = lane + 1)
            if (wea[lane])
                mem[addra][lane*8 +: 8] <= dina[lane*8 +: 8];
        douta <= mem[addra];
    end
endmodule
