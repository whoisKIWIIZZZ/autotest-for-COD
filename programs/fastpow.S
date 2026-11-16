.option norvc
.option norelax
.text
.globl _start

# 计算乘积的低 32 位，使用 t2-t5 临时寄存器。
.macro MUL32 dst, lhs, rhs
    addi t2,\lhs,0
    addi t3,\rhs,0
    addi t4,zero,0
    beq t3,zero,.Lmul_done\@
.Lmul_loop\@:
    andi t5,t3,1
    beq t5,zero,.Lmul_shift\@
    add t4,t4,t2
.Lmul_shift\@:
    slli t2,t2,1
    srli t3,t3,1
    bne t3,zero,.Lmul_loop\@
.Lmul_done\@:
    addi \dst,t4,0
.endm

_start:
    addi sp,zero,1024
    addi a0,zero,2
    addi a1,zero,10
    jal ra,fastpow
    addi t0,zero,1024
    bne a0,t0,.Lfail
    li t0,0x8c889292
    jal zero,.Ldisplay
.Lfail:
    li t0,0x8e88f9c7
.Ldisplay:
    lui t1,0xe0000
    sw t0,0(t1)
.Lhalt:
    jal zero,.Lhalt

# 保留参考程序的三层展开、乘法及递归栈帧。
fastpow:
    beq a1,zero,.Lzero
    addi a3,zero,1
    addi a4,a0,0
    beq a1,a3,.Lreturn
    MUL32 a6,a0,a0
    srai a2,a1,1
    addi a5,a1,0
    addi a0,a6,0
    beq a2,a3,.Lodd_original
    MUL32 a0,a6,a6
    srai a7,a1,2
    addi t1,a0,0
    beq a7,a3,.Lodd_half
    MUL32 a0,a0,a0
    addi sp,sp,-64
    srai a1,a1,3
    sw a4,24(sp)
    sw a2,16(sp)
    sw a6,8(sp)
    sw a5,0(sp)
    sw a7,32(sp)
    sw ra,56(sp)
    sw t1,40(sp)
    jal ra,fastpow
    lw a7,32(sp)
    lw a5,0(sp)
    lw a6,8(sp)
    andi a7,a7,1
    lw a2,16(sp)
    lw a4,24(sp)
    beq a7,zero,.Lrecursive_half
    lw t1,40(sp)
    MUL32 a0,t1,a0
.Lrecursive_half:
    andi a2,a2,1
    beq a2,zero,.Lrecursive_original
    MUL32 a0,a6,a0
.Lrecursive_original:
    andi a1,a5,1
    beq a1,zero,.Lrestore
    MUL32 a0,a4,a0
.Lrestore:
    lw ra,56(sp)
    addi sp,sp,64
    jalr zero,0(ra)
.Lodd_half:
    andi a2,a2,1
    beq a2,zero,.Lodd_original
    MUL32 a0,a6,a0
.Lodd_original:
    andi a1,a5,1
    beq a1,zero,.Lreturn
    MUL32 a0,a4,a0
.Lreturn:
    jalr zero,0(ra)
.Lzero:
    addi a0,zero,1
    jalr zero,0(ra)
