int main(void) {
    volatile unsigned int u = 0xFFFFFFFFu;
    volatile int s = -1;
    int result = 0;
    if (u > 1u) {
        result += 1;
    }
    if (s < 1) {
        result += 10;
    }
    if ((unsigned int)s > 1u) {
        result += 100;
    }
    return result;
}
