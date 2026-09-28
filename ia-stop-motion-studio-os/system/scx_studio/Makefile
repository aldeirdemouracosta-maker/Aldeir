# scx_studio — sched_ext scheduler of IA Stop-Motion Studio OS.
#
#   make SCX=<checkout of github.com/sched-ext/scx> [LIBBPF=<libbpf prefix>] [BPFTOOL=<bpftool>]
#
# Needs clang, libelf-dev, zlib and a recent bpftool/libbpf (bpftool ≥ 7.5,
# libbpf ≥ 1.5 — newer than Ubuntu 24.04's; scripts/instalar-scx-studio.sh
# builds them). The kernel must have CONFIG_SCHED_CLASS_EXT (Linux 6.12+).
SCX       ?= scx
ARCH      ?= $(shell uname -m | sed -e 's/x86_64/x86/' -e 's/aarch64/arm64/')
# Ubuntu's /usr/sbin/bpftool is a wrapper that only works for the running
# kernel's linux-tools; a versioned binary works for any kernel.
BPFTOOL   ?= $(shell ls /usr/lib/linux-tools/*/bpftool 2>/dev/null | tail -1 | grep . || command -v bpftool)
CLANG     ?= clang
CC        ?= cc
LIBBPF    ?=
ifneq ($(LIBBPF),)
LIBBPF_INC := -I$(LIBBPF)/include
LIBBPF_LIB := $(wildcard $(LIBBPF)/lib64/libbpf.a $(LIBBPF)/lib/libbpf.a)
else
LIBBPF_LIB := -lbpf
endif
INCLUDES  := $(LIBBPF_INC) -I. -I$(SCX)/scheds/include -I$(SCX)/scheds/vmlinux/arch/$(ARCH) \
             -I$(SCX)/scheds/include/bpf-compat

all: scx_studio

scx_studio.bpf.o: scx_studio.bpf.c scx_studio.h
	$(CLANG) -g -O2 -Wall -Wno-compare-distinct-pointer-types -target bpf -mcpu=v3 \
		-D__TARGET_ARCH_$(ARCH) $(INCLUDES) -c $< -o $@

scx_studio.bpf.skel.h: scx_studio.bpf.o
	$(BPFTOOL) gen skeleton $< name scx_studio > $@

scx_studio: scx_studio.c scx_studio.bpf.skel.h scx_studio.h
	$(CC) -O2 -Wall $(INCLUDES) $< -o $@ $(LIBBPF_LIB) -lelf -lz

clean:
	rm -f scx_studio scx_studio.bpf.o scx_studio.bpf.skel.h

.PHONY: all clean
# Never keep a half-written skeleton after a failed bpftool run.
.DELETE_ON_ERROR:
