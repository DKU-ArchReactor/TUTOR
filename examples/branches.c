volatile int inputs[3] = {-2, 0, 3};
int main(void) {
    int sum = 0;
    for (int i = 0; i < 3; i++) {
        int value = inputs[i];
        if (value < 0) {
            sum += 1;
        } else if (value == 0) {
            sum += 10;
        } else {
            sum += 100;
        }
    }
    return sum;
}
