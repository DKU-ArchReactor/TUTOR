volatile signed char negative = -1;
volatile unsigned char positive = 255;
int main(void) {
    return (int)negative + (int)positive;
}
