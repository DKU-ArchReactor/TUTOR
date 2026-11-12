int main(void) {
    int sum = 0;
    for (int i = 0; i < 10; i++) {
        if (i == 2) continue;
        if (i == 6) break;
        sum += i;
    }
    return sum;
}
