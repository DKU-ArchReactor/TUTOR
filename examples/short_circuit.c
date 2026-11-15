volatile int calls = 0;
int touch(void) {
    calls++;
    return 1;
}
int main(void) {
    volatile int x = 0;
    volatile int y = 2;
    int left = x && touch();
    int right = y || touch();
    int chosen = y > 1 ? 7 : 9;
    return left + right + chosen + calls * 100;
}
