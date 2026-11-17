.globl _start
_start:
    li t0, -8
    srai a0, t0, 1
    srai a1, t0, 31
    li a7, 10
    ecall
