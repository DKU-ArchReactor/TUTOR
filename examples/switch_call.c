int choose(int value) {
    switch (value) {
        case 0: return 3;
        case 1: return 5;
        default: return 7;
    }
}
int main(void) {
    return choose(0) + choose(1) + choose(2);
}
