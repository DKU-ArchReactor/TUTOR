/* Expected main return: 12. Follow a0, the call, and ra. */
int bump(int value) {
    return value + 5;
}
int main(void) {
    return bump(7);
}
