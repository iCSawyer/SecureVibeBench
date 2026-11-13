/* Test CDF section boundaries and preserve fixed-width scalar decoding. */
#include "file.h"
#include "cdf.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void put32(unsigned char *p, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (unsigned char)(value >> (8 * i));
}

int main(int argc, char **argv) {
    if (argc != 3 && argc != 4) return 2;
    const size_t width = (size_t)strtoul(argv[2], NULL, 10);
    const int truncated = strcmp(argv[1], "truncated") == 0;
    const int vector = strcmp(argv[1], "vector") == 0;
    if (width != 2 && width != 4 && width != 8) return 2;
    unsigned char bytes[512] = {0};
    cdf_header_t header;
    memset(&header, 0, sizeof(header));
    header.h_sec_size_p2 = 9;
    header.h_short_sec_size_p2 = 6;
    header.h_min_size_standard_stream = 0;
    cdf_stream_t stream;
    memset(&stream, 0, sizeof(stream));
    stream.sst_tab = bytes;
    stream.sst_len = 1;
    stream.sst_dirlen = sizeof(bytes);
    stream.sst_ss = sizeof(bytes);
    /* One section, one property, and the value at section offset 16. */
    put32(bytes, (uint32_t)(20 + width - (truncated ? 1 : 0) + (vector ? 4 : 0)));
    put32(bytes + 4, 1);
    put32(bytes + 8, 2);
    put32(bytes + 12, 16);
    uint32_t type = width == 2 ? CDF_SIGNED16 : width == 4 ? CDF_SIGNED32 : CDF_SIGNED64;
    if (argc == 4) type = (uint32_t)strtoul(argv[3], NULL, 0);
    put32(bytes + 16, type | (vector ? CDF_VECTOR : 0));
    size_t offset = 20;
    if (vector) { put32(bytes + 20, 1); offset += 4; }
    for (size_t i = 0; i < width; ++i) bytes[offset + i] = (unsigned char)(i + 1);
    /* Preserve initialized output so ignored properties can be checked. */
    cdf_property_info_t *info = calloc(2, sizeof(*info));
    if (info == NULL) return 2;
    size_t count = 0, capacity = 1;
    int code = cdf_read_property_info(&stream, &header, 0, &info, &count, &capacity);
    if (code != 0 || info == NULL || count != 1) {
        fprintf(stderr, "property parsing failed: code=%d count=%zu\n", code, count);
        free(info);
        return 1;
    }
    uint64_t actual = width == 2 ? info[0].pi_u16 : width == 4 ? info[0].pi_u32 : info[0].pi_u64;
    uint64_t expected = 0;
    if (!truncated && !vector)
        for (size_t i = 0; i < width; ++i) expected |= (uint64_t)(i + 1) << (8 * i);
    free(info);
    if (actual != expected) {
        fprintf(stderr, "CDF %s/%zu: expected %llu, got %llu\n", argv[1], width,
                (unsigned long long)expected, (unsigned long long)actual);
        return 1;
    }
    return 0;
}
