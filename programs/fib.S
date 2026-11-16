.option norvc
.option norelax
.text
.globl _start
_start:
    addi sp,zero,1024
    addi a0,zero,5
.Lstartup_call:
    auipc t1,%pcrel_hi(fib)
    jalr ra,%pcrel_lo(.Lstartup_call)(t1)
    addi t0,zero,8
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

# 保留参考程序的 AUIPC/JALR 递归调用及寄存器保存恢复。
fib:
    addi a5,zero,1
    bgeu a5,a0,.Lbase
    addi sp,sp,-16
    sw ra,12(sp)
    sw s0,8(sp)
    sw s1,4(sp)
    addi s0,a0,0
    addi a0,a0,-1
.Lcall_previous:
    auipc t1,%pcrel_hi(fib)
    jalr ra,%pcrel_lo(.Lcall_previous)(t1)
    addi s1,a0,0
    addi a0,s0,-2
.Lcall_before_previous:
    auipc t1,%pcrel_hi(fib)
    jalr ra,%pcrel_lo(.Lcall_before_previous)(t1)
    add a0,s1,a0
    lw ra,12(sp)
    lw s0,8(sp)
    lw s1,4(sp)
    addi sp,sp,16
    jalr zero,0(ra)
.Lbase:
    addi a0,zero,1
    jalr zero,0(ra)
