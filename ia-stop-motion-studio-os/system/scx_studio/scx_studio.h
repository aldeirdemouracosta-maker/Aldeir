/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Shared between the BPF scheduler and its loader.
 */
#ifndef __SCX_STUDIO_H
#define __SCX_STUDIO_H

enum studio_mode {
	STUDIO_NORMAL	= 0,
	STUDIO_CAPTURA	= 1,	/* camera + UI latency first */
	STUDIO_EDICAO	= 2,	/* smooth UI while editing */
	STUDIO_IA	= 3,	/* AI workers: throughput, UI still responsive */
	STUDIO_RENDER	= 4,	/* encoders: throughput */
};

enum studio_class {
	CLASS_OTHER	= 0,
	CLASS_UI	= 1,	/* IA Stop-Motion Studio OS itself */
	CLASS_WORKER	= 2,	/* ffmpeg, melt, sd-cli, whisper-cli, realesrgan… */
};

struct studio_cfg {
	unsigned int mode;
	unsigned int pad;
};

#endif /* __SCX_STUDIO_H */
