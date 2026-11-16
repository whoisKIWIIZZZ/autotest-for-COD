.text
.globl main
main:

    addi	x2,x2,-16
    sw	x1,12(x2)
    sw	x8,8(x2)
    addi	x8,x2,16
    addi	x2,x0,1024
    jal	x1,L_248
    jal	x1,L_2d8
    jal	x1,L_420
    jal	x1,L_494
    jal	x1,L_658
    jal	x1,L_a24
    jal	x1,L_8c
    addi	x15,x0,0
    addi	x10,x15,0
    lw	x1,12(x2)
    lw	x8,8(x2)
    addi	x2,x2,16
    jalr	x0,0(x1)
L_48:
    addi	x2,x2,-32
    sw	x8,28(x2)
    addi	x8,x2,32
    sw	x10,-20(x8)
    lw	x15,-20(x8)
    srai	x15,x15,0x1
    sw	x15,-20(x8)
    addi	x0,x0,0
L_68:
    lw	x15,-20(x8)
    addi	x14,x15,-1
    sw	x14,-20(x8)
    bne	x15,x0,L_68
    addi	x0,x0,0
    addi	x0,x0,0
    lw	x8,28(x2)
    addi	x2,x2,32
    jalr	x0,0(x1)
L_8c:
    addi	x2,x2,-48
    sw	x1,44(x2)
    sw	x8,40(x2)
    sw	x9,36(x2)
    sw	x18,32(x2)
    sw	x19,28(x2)
    sw	x20,24(x2)
    sw	x21,20(x2)
    addi	x8,x2,48
    lui	x15,0x2
    addi	x15,x15,-1416 # 0x1a78
    lw	x12,0(x15)
    lw	x13,4(x15)
    lw	x14,8(x15)
    lw	x15,12(x15)
    sw	x12,-48(x8)
    sw	x13,-44(x8)
    sw	x14,-40(x8)
    sw	x15,-36(x8)
    addi	x18,x0,0
    addi	x20,x0,0
    addi	x19,x0,255
    addi	x9,x0,0
    addi	x21,x0,1
L_ec:
    addi	x15,x0,1
    bne	x9,x15,L_f8
    addi	x18,x0,16
L_f8:
    addi	x15,x0,2
    bne	x9,x15,L_104
    addi	x18,x0,48
L_104:
    addi	x15,x0,3
    bne	x9,x15,L_110
    addi	x18,x0,49
L_110:
    addi	x15,x0,4
    bne	x9,x15,L_11c
    addi	x18,x0,51
L_11c:
    addi	x15,x0,5
    bne	x9,x15,L_128
    addi	x18,x0,115
L_128:
    addi	x15,x0,6
    bne	x9,x15,L_134
    addi	x18,x0,119
L_134:
    addi	x15,x0,7
    bne	x9,x15,L_140
    addi	x20,x0,1
L_140:
    addi	x15,x0,8
    bne	x9,x15,L_14c
    addi	x20,x0,33
L_14c:
    addi	x15,x0,9
    bne	x9,x15,L_158
    addi	x20,x0,49
L_158:
    addi	x15,x0,10
    bne	x9,x15,L_164
    addi	x20,x0,57
L_164:
    addi	x15,x0,11
    bne	x9,x15,L_170
    addi	x19,x0,0
L_170:
    addi	x15,x0,12
    bne	x9,x15,L_17c
    addi	x19,x0,255
L_17c:
    addi	x15,x0,13
    bne	x9,x15,L_188
    addi	x19,x0,0
L_188:
    addi	x15,x0,14
    bne	x9,x15,L_194
    addi	x19,x0,255
L_194:
    addi	x15,x9,0
    addi	x9,x15,1
    addi	x14,x0,17
    bne	x15,x14,L_1b8
    addi	x20,x0,0
    addi	x18,x20,0
    addi	x19,x0,255
    addi	x9,x0,0
    addi	x21,x21,-1
L_1b8:
    addi	x1,x0,0
    and	x14,x18,x19
    addi	x15,x21,1
    slli	x15,x15,0x3
    andi	x15,x15,24
    sll	x15,x14,x15
    or	x1,x1,x15
    and	x14,x20,x19
    slli	x15,x21,0x3
    andi	x15,x15,24
    sll	x15,x14,x15
    or	x1,x1,x15
    lui	x15,0xe0000
    xori	x14,x1,-1
    sw	x14,0(x15) # 0xe0000000
    lui	x15,0x7a
    addi	x10,x15,288 # 0x7a120
    jal	x1,L_48
    jal	x0,L_ec
L_204:
    lui	x14,0xf0000
    lw	x15,4(x0) # 0x4
    or	x15,x15,x14
    lui	x14,0xe0000
    sw	x15,0(x14) # 0xe0000000
L_218:
    jal	x0,L_218
L_21c:
    addi	x10,x10,10
    slli	x15,x10,0x3
    or	x15,x15,x10
    lui	x14,0xfb9bd
    addi	x14,x14,-361 # 0xfb9bce97
    add	x15,x15,x14
    srai	x14,x15,0x5
    sub	x15,x15,x14
    srli	x10,x15,0x5
    add	x10,x10,x15
    jalr	x0,0(x1)
L_248:
    addi	x2,x2,-16
    sw	x1,12(x2)
    lui	x14,0xe0000
    lui	x15,0x111
    addi	x15,x15,256 # 0x111100
    sw	x15,0(x14) # 0xe0000000
    lui	x15,0xaaaab
    addi	x15,x15,-1375 # 0xaaaaaaa1
    sw	x15,4(x0) # 0x4
    lui	x10,0x66d
    addi	x10,x10,-769 # 0x66ccff
    jal	x1,L_21c
    lui	x15,0x712f
    addi	x15,x15,1841 # 0x712f731
    bne	x10,x15,L_290
    lw	x1,12(x2)
    addi	x2,x2,16
    jalr	x0,0(x1)
L_290:
    jal	x1,L_204
L_294:
    lh	x14,0(x10)
    lhu	x15,2(x10)
    xor	x15,x14,x15
    srai	x14,x14,0x1
    xor	x15,x15,x14
    sh	x15,2(x10)
    lw	x15,0(x10)
    lui	x14,0x1c
    addi	x14,x14,-174 # 0x1bf52
    xor	x15,x15,x14
    sw	x15,0(x10)
    srai	x14,x15,0x10
    srli	x15,x15,0x10
    andi	x15,x15,255
    sub	x15,x14,x15
    sw	x15,4(x10)
    jalr	x0,0(x1)
L_2d8:
    addi	x2,x2,-16
    sw	x1,12(x2)
    sw	x9,8(x2)
    lui	x14,0xe0000
    lui	x15,0x222
    addi	x15,x15,512 # 0x222200
    sw	x15,0(x14) # 0xe0000000
    addi	x14,x0,4
    lw	x15,0(x14)
    slli	x15,x15,0x4
    ori	x15,x15,2
    sw	x15,0(x14)
    addi	x9,x0,8
    addi	x15,x0,97
    sb	x15,0(x9)
    addi	x15,x0,41
    sb	x15,9(x0) # 0x9
    addi	x15,x0,120
    sb	x15,10(x0) # 0xa
    addi	x15,x0,95
    sb	x15,11(x0) # 0xb
    addi	x10,x0,8
    jal	x1,L_294
    lw	x14,0(x9)
    lui	x15,0x62a89
    addi	x15,x15,1587 # 0x62a89633
    bne	x14,x15,L_364
    lw	x14,12(x0) # 0xc
    lui	x15,0x6
    addi	x15,x15,512 # 0x6200
    bne	x14,x15,L_368
    lw	x1,12(x2)
    lw	x9,8(x2)
    addi	x2,x2,16
    jalr	x0,0(x1)
L_364:
    jal	x1,L_204
L_368:
    jal	x1,L_204
L_36c:
    addi	x15,x10,0
    beq	x11,x0,L_39c
    addi	x10,x0,0
    jal	x0,L_388
L_37c:
    slli	x15,x15,0x1
    srai	x11,x11,0x1
    beq	x11,x0,L_398
L_388:
    andi	x14,x11,1
    beq	x14,x0,L_37c
    add	x10,x10,x15
    jal	x0,L_37c
L_398:
    jalr	x0,0(x1)
L_39c:
    addi	x10,x11,0
    jalr	x0,0(x1)
L_3a4:
    addi	x2,x2,-32
    sw	x1,28(x2)
    sw	x9,24(x2)
    sw	x18,20(x2)
    sw	x19,16(x2)
    sw	x20,12(x2)
    addi	x20,x0,1
    beq	x10,x0,L_400
    addi	x19,x10,0
    addi	x20,x0,0
    bge	x0,x10,L_400
    addi	x9,x0,1
L_3d4:
    addi	x10,x9,-1
    jal	x1,L_3a4
    addi	x18,x10,0
    sub	x10,x19,x9
    jal	x1,L_3a4
    addi	x11,x10,0
    addi	x10,x18,0
    jal	x1,L_36c
    add	x20,x20,x10
    addi	x9,x9,1
    bge	x19,x9,L_3d4
L_400:
    addi	x10,x20,0
    lw	x1,28(x2)
    lw	x9,24(x2)
    lw	x18,20(x2)
    lw	x19,16(x2)
    lw	x20,12(x2)
    addi	x2,x2,32
    jalr	x0,0(x1)
L_420:
    addi	x2,x2,-16
    sw	x1,12(x2)
    lui	x14,0xe0000
    lui	x15,0x333
    addi	x15,x15,768 # 0x333300
    sw	x15,0(x14) # 0xe0000000
    addi	x14,x0,4
    lw	x15,0(x14)
    slli	x15,x15,0x4
    ori	x15,x15,3
    sw	x15,0(x14)
    addi	x10,x0,5
    jal	x1,L_3a4
    addi	x15,x0,42
    bne	x10,x15,L_468
    lw	x1,12(x2)
    addi	x2,x2,16
    jalr	x0,0(x1)
L_468:
    jal	x1,L_204
L_46c:
    addi	x15,x0,31
    jal	x0,L_47c
L_474:
    addi	x15,x15,-1
    beq	x15,x0,L_490
L_47c:
    sra	x14,x10,x15
    blt	x14,x11,L_474
    sll	x14,x11,x15
    sub	x10,x10,x14
    jal	x0,L_474
L_490:
    jalr	x0,0(x1)
L_494:
    addi	x2,x2,-48
    sw	x1,44(x2)
    sw	x9,40(x2)
    sw	x18,36(x2)
    sw	x19,32(x2)
    sw	x20,28(x2)
    sw	x21,24(x2)
    sw	x22,20(x2)
    sw	x23,16(x2)
    sw	x24,12(x2)
    lui	x14,0xe0000
    lui	x15,0x444
    addi	x15,x15,1024 # 0x444400
    sw	x15,0(x14) # 0xe0000000
    addi	x14,x0,4
    lw	x15,0(x14)
    slli	x15,x15,0x4
    ori	x15,x15,4
    sw	x15,0(x14)
    addi	x24,x0,100
    addi	x22,x0,1044
    addi	x20,x0,42
    addi	x19,x0,88
    addi	x18,x0,912
    addi	x9,x0,238
    lui	x21,0x2
    addi	x21,x21,1815 # 0x2717
    lui	x23,0xfffff
    addi	x23,x23,-907 # 0xffffec75
    jal	x0,L_590
L_50c:
    addi	x18,x18,4
L_510:
    add	x10,x9,x21
    addi	x11,x10,0
    jal	x1,L_36c
    addi	x11,x21,0
    jal	x1,L_46c
    add	x9,x10,x23
    add	x10,x18,x21
    addi	x11,x10,0
    jal	x1,L_36c
    addi	x11,x21,0
    jal	x1,L_46c
    add	x18,x10,x23
    add	x10,x19,x21
    addi	x11,x10,0
    jal	x1,L_36c
    addi	x11,x21,0
    jal	x1,L_46c
    add	x19,x10,x23
    add	x10,x20,x21
    addi	x11,x10,0
    jal	x1,L_36c
    addi	x11,x21,0
    jal	x1,L_46c
    add	x20,x10,x23
    add	x10,x22,x21
    addi	x11,x10,0
    jal	x1,L_36c
    addi	x11,x21,0
    jal	x1,L_46c
    add	x22,x10,x23
    addi	x24,x24,-1
    beq	x24,x0,L_60c
L_590:
    andi	x15,x9,1
    beq	x15,x0,L_5d8
    blt	x18,x9,L_5a4
    bgeu	x20,x22,L_5a8
    bge	x20,x9,L_5a8
L_5a4:
    addi	x19,x19,3
L_5a8:
    bge	x9,x20,L_5b0
    bltu	x19,x22,L_5b4
L_5b0:
    bge	x18,x19,L_5b8
L_5b4:
    addi	x9,x9,5
L_5b8:
    bge	x18,x20,L_5c8
    bgeu	x9,x19,L_5c8
    bge	x22,x18,L_5c8
    addi	x22,x22,2
L_5c8:
    blt	x20,x9,L_50c
    bltu	x22,x19,L_50c
    bge	x20,x18,L_510
    jal	x0,L_50c
L_5d8:
    bge	x9,x22,L_5e8
    bgeu	x18,x20,L_5e8
    bge	x9,x19,L_5e8
    addi	x9,x9,2
L_5e8:
    blt	x22,x18,L_5f4
    bltu	x9,x20,L_5f4
    bge	x22,x19,L_5f8
L_5f4:
    addi	x19,x19,4
L_5f8:
    blt	x19,x18,L_604
    bgeu	x22,x9,L_510
    bge	x22,x18,L_510
L_604:
    addi	x20,x20,3
    jal	x0,L_510
L_60c:
    xor	x15,x9,x18
    xor	x15,x15,x19
    xor	x15,x15,x20
    xor	x10,x15,x22
    lui	x15,0xffffd
    addi	x15,x15,231 # 0xffffd0e7
    bne	x10,x15,L_654
    lw	x1,44(x2)
    lw	x9,40(x2)
    lw	x18,36(x2)
    lw	x19,32(x2)
    lw	x20,28(x2)
    lw	x21,24(x2)
    lw	x22,20(x2)
    lw	x23,16(x2)
    lw	x24,12(x2)
    addi	x2,x2,48
    jalr	x0,0(x1)
L_654:
    jal	x1,L_204
L_658:
    addi	x2,x2,-16
    sw	x1,12(x2)
    lui	x14,0xe0000
    lui	x15,0x555
    addi	x15,x15,1280 # 0x555500
    sw	x15,0(x14) # 0xe0000000
    addi	x14,x0,4
    lw	x15,0(x14)
    slli	x15,x15,0x4
    ori	x15,x15,5
    sw	x15,0(x14)
    addi	x11,x0,3
    addi	x0,x11,1
    add	x15,x11,x0
    addi	x14,x0,3
    bne	x15,x14,L_6c8
    addi	x13,x0,114
    addi	x15,x0,514
    xor	x13,x13,x15
    xor	x15,x13,x15
    xor	x13,x13,x15
    addi	x14,x0,514
    bne	x13,x14,L_6cc
    addi	x14,x0,114
    bne	x15,x14,L_6cc
    lw	x1,12(x2)
    addi	x2,x2,16
    jalr	x0,0(x1)
L_6c8:
    jal	x1,L_204
L_6cc:
    jal	x1,L_204
L_6d0:
    addi	x2,x2,-368
    sw	x9,364(x2)
    sw	x18,360(x2)
    sw	x19,356(x2)
    sw	x20,352(x2)
    sw	x21,348(x2)
    sw	x22,344(x2)
    sw	x23,340(x2)
    sw	x24,336(x2)
    sw	x25,332(x2)
    addi	x18,x11,0
    addi	x30,x2,0
    addi	x12,x2,64
    addi	x14,x30,0
L_708:
    lbu	x15,0(x10)
    slli	x15,x15,0x18
    lbu	x13,1(x10)
    slli	x13,x13,0x10
    or	x15,x15,x13
    lbu	x13,3(x10)
    or	x15,x15,x13
    lbu	x13,2(x10)
    slli	x13,x13,0x8
    or	x15,x15,x13
    sw	x15,0(x14)
    addi	x10,x10,4
    addi	x14,x14,4
    bne	x14,x12,L_708
    addi	x11,x30,256
    addi	x14,x30,0
L_748:
    lw	x15,52(x14)
    lw	x13,32(x14)
    xor	x15,x15,x13
    lw	x13,8(x14)
    xor	x15,x15,x13
    lw	x13,0(x14)
    xor	x15,x15,x13
    slli	x13,x15,0x1
    srli	x12,x15,0x1f
    or	x13,x13,x12
    sw	x13,64(x14)
    addi	x14,x14,4
    bne	x14,x11,L_748
    lw	x25,0(x18)
    lw	x24,4(x18)
    lw	x23,8(x18)
    lw	x22,12(x18)
    lw	x21,16(x18)
    addi	x7,x30,320
    addi	x16,x21,0
    addi	x17,x22,0
    addi	x6,x23,0
    addi	x12,x24,0
    addi	x10,x25,0
    addi	x28,x0,0
    addi	x14,x0,0
    addi	x5,x0,20
    addi	x29,x0,2
    lui	x20,0x8f1bc
    addi	x20,x20,-804 # 0x8f1bbcdc
    addi	x31,x0,3
    lui	x19,0xca62c
    addi	x19,x19,470 # 0xca62c1d6
    lui	x9,0x6ed9f
    addi	x9,x9,-1119 # 0x6ed9eba1
    lui	x11,0x5a828
    addi	x11,x11,-1639 # 0x5a827999
    jal	x0,L_870
L_7e0:
    addi	x14,x14,1
    addi	x28,x0,1
    jal	x0,L_878
L_7ec:
    bne	x14,x31,L_848
    slli	x15,x10,0x5
    srli	x13,x10,0x1b
    or	x15,x15,x13
    add	x16,x16,x19
    add	x15,x15,x16
    xor	x13,x12,x6
    xor	x13,x13,x17
    add	x15,x15,x13
    lw	x13,0(x30)
    add	x15,x15,x13
    jal	x0,L_848
L_81c:
    slli	x15,x10,0x5
    srli	x13,x10,0x1b
    or	x15,x15,x13
    add	x16,x16,x11
    add	x15,x15,x16
    lw	x13,0(x30)
    add	x15,x15,x13
    xor	x13,x6,x17
    and	x13,x13,x12
    xor	x13,x13,x17
    add	x15,x15,x13
L_848:
    srli	x16,x12,0x2
    slli	x13,x12,0x1e
    or	x13,x13,x16
    addi	x30,x30,4
    addi	x12,x10,0
    addi	x16,x17,0
    beq	x30,x7,L_8e4
    addi	x17,x6,0
    addi	x6,x13,0
    addi	x10,x15,0
L_870:
    beq	x28,x5,L_7e0
    addi	x28,x28,1
L_878:
    beq	x14,x29,L_8b0
    bltu	x29,x14,L_7ec
    beq	x14,x0,L_81c
    slli	x15,x10,0x5
    srli	x13,x10,0x1b
    or	x15,x15,x13
    add	x16,x16,x9
    add	x15,x15,x16
    xor	x13,x12,x6
    xor	x13,x13,x17
    add	x15,x15,x13
    lw	x13,0(x30)
    add	x15,x15,x13
    jal	x0,L_848
L_8b0:
    slli	x15,x10,0x5
    srli	x13,x10,0x1b
    or	x15,x15,x13
    add	x16,x16,x20
    add	x15,x15,x16
    lw	x13,0(x30)
    add	x15,x15,x13
    or	x13,x6,x17
    and	x13,x13,x12
    and	x16,x6,x17
    or	x13,x13,x16
    add	x15,x15,x13
    jal	x0,L_848
L_8e4:
    add	x15,x15,x25
    sw	x15,0(x18)
    add	x24,x24,x10
    sw	x24,4(x18)
    add	x23,x23,x13
    sw	x23,8(x18)
    add	x22,x22,x6
    sw	x22,12(x18)
    add	x21,x21,x17
    sw	x21,16(x18)
    lw	x9,364(x2)
    lw	x18,360(x2)
    lw	x19,356(x2)
    lw	x20,352(x2)
    lw	x21,348(x2)
    lw	x22,344(x2)
    lw	x23,340(x2)
    lw	x24,336(x2)
    lw	x25,332(x2)
    addi	x2,x2,368
    jalr	x0,0(x1)
L_938:
    addi	x2,x2,-112
    sw	x1,108(x2)
    lui	x15,0x67452
    addi	x15,x15,769 # 0x67452301
    sw	x15,12(x2)
    lui	x15,0xefcdb
    addi	x15,x15,-1143 # 0xefcdab89
    sw	x15,16(x2)
    lui	x15,0x98bae
    addi	x15,x15,-770 # 0x98badcfe
    sw	x15,20(x2)
    lui	x15,0x10325
    addi	x15,x15,1142 # 0x10325476
    sw	x15,24(x2)
    lui	x15,0xc3d2e
    addi	x15,x15,496 # 0xc3d2e1f0
    sw	x15,28(x2)
    addi	x11,x2,24
    addi	x15,x2,32
    addi	x12,x0,57
    jal	x0,L_9a0
L_98c:
    addi	x14,x14,87
    sb	x14,7(x15)
L_994:
    srli	x10,x10,0x4
    addi	x15,x15,-1
    beq	x11,x15,L_9b4
L_9a0:
    andi	x14,x10,15
    addi	x13,x14,48
    bltu	x12,x13,L_98c
    sb	x13,7(x15)
    jal	x0,L_994
L_9b4:
    addi	x15,x0,-128
    sb	x15,40(x2)
    addi	x15,x0,64
    sb	x15,95(x2)
    addi	x15,x2,41
    addi	x14,x2,95
L_9cc:
    sb	x0,0(x15)
    addi	x15,x15,1
    bne	x15,x14,L_9cc
    addi	x11,x2,12
    addi	x10,x2,32
    jal	x1,L_6d0
    lw	x10,12(x2)
    srli	x15,x10,0x18
    slli	x15,x15,0x8
    srli	x14,x10,0x10
    andi	x14,x14,255
    or	x14,x14,x15
    slli	x14,x14,0x8
    srli	x15,x10,0x8
    andi	x15,x15,255
    or	x15,x15,x14
    slli	x15,x15,0x8
    andi	x10,x10,255
    or	x10,x10,x15
    lw	x1,108(x2)
    addi	x2,x2,112
    jalr	x0,0(x1)
L_a24:
    addi	x2,x2,-16
    sw	x1,12(x2)
    lui	x14,0xe0000
    lui	x15,0x666
    addi	x15,x15,1536 # 0x666600
    sw	x15,0(x14) # 0xe0000000
    addi	x14,x0,4
    lw	x15,0(x14)
    slli	x15,x15,0x4
    ori	x15,x15,6
    sw	x15,0(x14)
    lui	x10,0x12345
    addi	x10,x10,1656 # 0x12345678
    jal	x1,L_938
    lui	x15,0x7c223
    addi	x15,x15,-78 # 0x7c222fb2
    bne	x10,x15,L_a74
    lw	x1,12(x2)
    addi	x2,x2,16
    jalr	x0,0(x1)
L_a74:
    jal	x1,L_204
