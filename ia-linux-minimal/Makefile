# Makefile de conveniência — cada alvo apenas delega para scripts/*.sh ou
# para o crate ai-core. Não substitui o Makefile do Buildroot em si.

.PHONY: all fetch configure-qemu configure-bios configure-uefi compile qemu \
        ai-core-check ai-core-test ai-core-lint clean-build

all: fetch configure-qemu compile

fetch:
	./scripts/fetch-buildroot.sh

configure-qemu:
	./scripts/configure.sh qemu

configure-bios:
	./scripts/configure.sh bios

configure-uefi:
	./scripts/configure.sh uefi

compile:
	./scripts/compile.sh

qemu:
	./scripts/run-qemu.sh

# Desenvolvimento do ai-core sem depender do Buildroot/QEMU:
ai-core-check:
	cd ai-core && cargo check

ai-core-test:
	cd ai-core && cargo test

ai-core-lint:
	cd ai-core && cargo clippy -- -D warnings

clean-build:
	rm -rf .build
