/* Expected main return: 65532. Compare lh and lhu. */
volatile signed short negative = -2;
volatile unsigned short positive = 65534;
int main(void) {
    return (int)negative + (int)positive;
}
