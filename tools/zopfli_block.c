/* A bounded-size raw DEFLATE block. Return its exact bit length before bytes. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <zopfli/zopfli.h>
#include <zopfli/deflate.h>

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    size_t capacity = 1024 * 1024, length = 0;
    unsigned char *input = malloc(capacity);
    if (!input) return 3;
    for (;;) {
        if (length == capacity) {
            capacity *= 2;
            unsigned char *next = realloc(input, capacity);
            if (!next) return 3;
            input = next;
        }
        size_t read = fread(input + length, 1, capacity - length, stdin);
        length += read;
        if (!read) break;
    }
    if (ferror(stdin)) return 4;
    ZopfliOptions options;
    ZopfliInitOptions(&options);
    options.numiterations = 3;
    unsigned char bit_pointer = 0, *output = NULL;
    size_t output_length = 0;
    ZopfliDeflate(&options, 2, atoi(argv[1]) ? 1 : 0, input, length,
                  &bit_pointer, &output, &output_length);
    uint64_t bits = bit_pointer ? (output_length - 1) * 8 + bit_pointer : output_length * 8;
    unsigned char header[8];
    for (int i = 0; i < 8; i++) header[i] = (unsigned char)(bits >> (8 * i));
    int failed = fwrite(header, 1, 8, stdout) != 8 ||
                 fwrite(output, 1, output_length, stdout) != output_length;
    free(input);
    free(output);
    return failed ? 5 : 0;
}
