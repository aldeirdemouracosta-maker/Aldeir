"""
IAVOX - Leitor de PDF em Áudio
================================
CLI acessível: todas as perguntas são feitas passo a passo, com valores
padrão sensatos, para funcionar bem junto com leitores de tela / DOSVOX.

Uso rápido (não interativo):
    python -m iavox_pdf_audio.cli.main documento.pdf --modo resumo --densidade curto --tts automatico

Uso interativo (recomendado para quem usa leitor de tela):
    python -m iavox_pdf_audio.cli.main
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..core.reader import IAVOXPDFReader, ReadingOptions
from ..tts.selector import ENGINE_CHOICES

logging.basicConfig(level=logging.INFO, format="[IAVOX] %(message)s")
logger = logging.getLogger("iavox.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="IAVOX - transforma um PDF em áudio, com audiodescrição de imagens."
    )
    parser.add_argument("pdf", nargs="?", help="Caminho do arquivo PDF a ser lido.")
    parser.add_argument(
        "--modo", choices=["completo", "resumo"], default=None,
        help="Ler o texto completo ou um resumo gerado por IA.",
    )
    parser.add_argument(
        "--densidade", choices=["curto", "medio", "detalhado"], default=None,
        help="Nível de detalhe do resumo (só vale com --modo resumo).",
    )
    parser.add_argument(
        "--imagens", choices=["sim", "nao"], default=None,
        help="Gerar audiodescrição das imagens do PDF.",
    )
    parser.add_argument(
        "--tts", choices=list(ENGINE_CHOICES), default=None,
        help="Motor de voz: offline, piper, ia ou automatico.",
    )
    parser.add_argument(
        "--salvar-audio", choices=["sim", "nao"], default=None,
        help="Salvar o resultado como arquivo de áudio (.wav).",
    )
    parser.add_argument(
        "--saida", default="./iavox_saida",
        help="Pasta onde salvar o áudio gerado.",
    )
    parser.add_argument(
        "--ler-agora", action="store_true",
        help="Além de (ou em vez de) salvar, já lê o texto em voz alta.",
    )
    parser.add_argument(
        "--tesseract-cmd", default=None,
        help="Caminho do executável do Tesseract (Windows, se não estiver no PATH). "
             "Ex: C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    )
    parser.add_argument(
        "--poppler-path", default=None,
        help="Pasta 'bin' do Poppler (Windows, se não estiver no PATH). "
             "Ex: C:\\poppler-24.02.0\\Library\\bin",
    )
    parser.add_argument(
        "--piper-model", default=None,
        help="Caminho do modelo de voz .onnx do Piper (motor --tts piper).",
    )
    parser.add_argument(
        "--kokoro-model", default=None,
        help="Caminho do modelo kokoro-v1.0*.onnx (motor --tts kokoro). "
             "Padrão: ~/.iavox/kokoro/kokoro-v1.0.onnx",
    )
    parser.add_argument(
        "--kokoro-voices", default=None,
        help="Caminho do arquivo voices-v1.0.bin (motor --tts kokoro). "
             "Padrão: ~/.iavox/kokoro/voices-v1.0.bin",
    )
    parser.add_argument(
        "--espeak-cmd", default=None,
        help="Caminho do executável do espeak-ng (Windows, se não estiver no PATH). "
             "Ex: C:\\Program Files\\eSpeak NG\\espeak-ng.exe",
    )
    return parser


def ask(prompt: str, default: str, choices: list[str] | None = None) -> str:
    """Pergunta interativa simples e acessível — sempre com valor padrão anunciado."""
    choices_hint = f" (opções: {', '.join(choices)})" if choices else ""
    resposta = input(f"{prompt}{choices_hint} [padrão: {default}]: ").strip().lower()
    return resposta or default


def run_interactive(args: argparse.Namespace) -> ReadingOptions:
    print("=== IAVOX - Leitor de PDF em Áudio ===\n")
    pdf_path = args.pdf or input("Caminho do arquivo PDF: ").strip()
    if not pdf_path:
        print("Nenhum arquivo informado. Encerrando.")
        sys.exit(1)
    args.pdf = pdf_path

    modo = args.modo or ask("Ler completo ou resumo?", "completo", ["completo", "resumo"])
    densidade = "medio"
    if modo == "resumo":
        densidade = args.densidade or ask(
            "Densidade do resumo", "medio", ["curto", "medio", "detalhado"]
        )
    imagens = args.imagens or ask("Descrever as imagens do PDF?", "sim", ["sim", "nao"])
    tts = args.tts or ask("Motor de voz", "automatico", list(ENGINE_CHOICES))
    salvar = args.salvar_audio or ask("Salvar como arquivo de áudio?", "sim", ["sim", "nao"])

    return ReadingOptions(
        mode=modo,
        density=densidade,
        describe_images=(imagens == "sim"),
        tts_choice=tts,
        save_audio=(salvar == "sim"),
        output_dir=args.saida,
        piper_model_path=args.piper_model,
        kokoro_model_path=args.kokoro_model,
        kokoro_voices_path=args.kokoro_voices,
        espeak_binary_path=args.espeak_cmd,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    interactive = args.modo is None and args.tts is None and args.imagens is None
    if interactive:
        options = run_interactive(args)
    else:
        if not args.pdf:
            parser.error("informe o caminho do PDF (ou rode sem argumentos para o modo interativo)")
        options = ReadingOptions(
            mode=args.modo or "completo",
            density=args.densidade or "medio",
            describe_images=(args.imagens != "nao"),
            tts_choice=args.tts or "automatico",
            save_audio=(args.salvar_audio != "nao"),
            output_dir=args.saida,
            piper_model_path=args.piper_model,
            kokoro_model_path=args.kokoro_model,
            kokoro_voices_path=args.kokoro_voices,
            espeak_binary_path=args.espeak_cmd,
        )

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        logger.error("Arquivo não encontrado: %s", pdf_path)
        return 1

    reader = IAVOXPDFReader()
    if args.tesseract_cmd or args.poppler_path:
        reader.extractor.poppler_path = args.poppler_path
        if args.tesseract_cmd:
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = args.tesseract_cmd
            except ImportError:
                pass

    def progress(current: int, total: int, stage: str) -> None:
        logger.info("Página %s/%s — %s", current, total, stage)

    logger.info("Extraindo e preparando o texto de %s ...", pdf_path.name)
    script = reader.build_script(pdf_path, options, progress_cb=progress)

    logger.info(
        "Roteiro pronto: %s páginas, %s imagens descritas, OCR usado: %s",
        script.pages_count, script.image_descriptions_count, "sim" if script.used_ocr else "não",
    )

    try:
        audio_path = None
        if options.save_audio:
            audio_path = reader.synthesize(script, options)
            logger.info("Áudio salvo em: %s", audio_path)

        if args.ler_agora or (not options.save_audio):
            logger.info("Lendo em voz alta agora...")
            reader.speak_live(script, options)
    except RuntimeError as exc:
        logger.error("%s", exc)
        logger.error(
            "Dica: tente --tts offline (sempre disponível) ou --tts automatico."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
