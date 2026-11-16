int main(void) {
    int sum = 0;
    for (int i = 0; i < 4; i++) {
        switch (i) {
            case 0:
                sum += 1;
            case 1:
                sum += 2;
                break;
            case 2:
                sum += 4;
                break;
            default:
                sum += 8;
                break;
        }
        if (i == 2) {
            continue;
        }
        sum += 10;
    }
    return sum;
}
