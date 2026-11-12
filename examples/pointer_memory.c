volatile int values[3] = {4, 7, 9};
int main(void) {
    volatile int *p = values;
    p[1] += 5;
    return p[0] + p[1] + p[2];
}
