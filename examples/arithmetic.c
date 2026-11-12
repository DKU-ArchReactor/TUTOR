int main(void) {
    volatile int a = -17;
    volatile int b = 5;
    return (a / b) * 10 + (a % b);
}
