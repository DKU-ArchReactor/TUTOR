.globl _start
_start:
    li t0, 19
    li t1, 0
    div a0, t0, t1
    rem a1, t0, t1
    li a7, 10
    ecall
