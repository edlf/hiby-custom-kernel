#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Compiles aic_timer_ns() as it stands in the given soc_aic.c, on the host, and checks it over every
period the module accepts: a quarter of the period's own time, so that an underrun is seen well within
a period, and never under 1 ms.  usage: test_period.py path/to/soc_aic.c"""
import re, subprocess, sys, tempfile, os
src = open(sys.argv[1]).read()
m = re.search(r"/\* aic_timer_ns: begin \*/(.*?)/\* aic_timer_ns: end \*/", src, re.S)
if not m:
    sys.exit("FAIL: no aic_timer_ns in this source")
harness = r'''
#include <stdint.h>
#include <stdio.h>
typedef uint64_t u64; typedef uint32_t u32;
#define NSEC_PER_SEC 1000000000L
#define div_u64(a, b) ((u64)(a) / (u32)(b))
#define max_t(t, a, b) ((t)(a) > (t)(b) ? (t)(a) : (t)(b))
''' + m.group(1) + r'''
int main(void)
{
    static const u32 rates[] = { 8000, 11025, 12000, 16000, 22050, 24000, 32000, 37800, 44100, 48000, 64000, 88200,
                                 96000, 128000, 176400, 192000, 352800, 384000, 705600, 768000 };
    long zero = 0, early = 0, wrong = 0, n = 0;
    for (unsigned i = 0; i < sizeof rates / sizeof rates[0]; i++)
        for (u32 fb = 2; fb <= 8; fb += (fb == 2 ? 2 : 4))        /* frame bytes: 2, 4, 8 */
            for (u32 bytes = 4096; bytes <= 262144; bytes += 32) { /* the module's floor and step */
                if (bytes % fb) continue;
                u32 frames = bytes / fb, r = rates[i];
                u64 got = aic_timer_ns(frames, r), real = (u64)frames * 1000000000ULL / r / 4;
                n++;
                if (got < 1000000ULL) zero++;
                if (real >= 1000000ULL && got != real) wrong++;
                if (real < 1000000ULL && got != 1000000ULL) early++;
            }
    printf("%ld settings: %ld with a timer under 1 ms, %ld not a quarter of the period, %ld short ones not held at 1 ms\n", n, zero, wrong, early);
    /* the three that stopped the device, 24 bit stereo */
    printf("1408@176400: %llu ns, 1024@176400: %llu ns, 512@96000: %llu ns, 512@768000: %llu ns\n",
           (unsigned long long)aic_timer_ns(1408, 176400), (unsigned long long)aic_timer_ns(1024, 176400),
           (unsigned long long)aic_timer_ns(512, 96000), (unsigned long long)aic_timer_ns(512, 768000));
    /* a long period at a low rate must not wrap 32 bits */
    if (aic_timer_ns(131072, 8000) != 4096000000ULL) { puts("FAIL: a long period wraps"); wrong++; }
    return zero || wrong || early;
}
'''
with tempfile.TemporaryDirectory() as d:
    c = os.path.join(d, "t.c"); open(c, "w").write(harness)
    subprocess.run(["gcc", "-Wall", "-Werror", "-o", os.path.join(d, "t"), c], check=True)
    r = subprocess.run([os.path.join(d, "t")])
    print("PASS" if r.returncode == 0 else "FAIL"); sys.exit(r.returncode)
