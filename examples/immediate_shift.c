/* Expected main return: 9. Inspect slli, andi, and addi. */
volatile unsigned int input = 13;
int main(void) {
    unsigned int shifted = input << 2;
    unsigned int masked = shifted & 15u;
    return (int)(masked + 5u);
}
