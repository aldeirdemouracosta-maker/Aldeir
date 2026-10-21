# Protótipo no PC: malha (app) × inswapper (IA)

Compara, **no seu clipe e na sua foto**, a troca de rosto do app (malha) com o inswapper, e mede o tempo por quadro.
Uso **pessoal/avaliação**. Todos os vídeos saem com o selo "CONTEUDO ALTERADO - IA".

> Só use com a **sua** foto (ou de quem autorizou) e com vídeo que você pode usar. O script exige `--i-have-consent`.
> O `inswapper_128.onnx` é de **pesquisa não comercial** (InsightFace): você baixa por conta própria; ele **não** vai para o repositório.

## 1. Instalar (Windows ou Linux, Python 3.10+)
```
pip install mediapipe opencv-python numpy
pip install insightface onnxruntime        # só para o inswapper
```
No Linux, o MediaPipe pode pedir `libegl1` e `libgles2` (`sudo apt install libegl1 libgles2`).

## 2. Compilar a biblioteca da malha (mesmo código C++ do app)
```
cmake -S tools/pc_prototype -B build_pc
cmake --build build_pc --config Release
```
(precisa de CMake e de um compilador C++: Visual Studio Build Tools no Windows, `g++` no Linux)

## 3. Baixar o modelo de pontos do rosto (3,7 MB)
```
sh tools/fetch_face_model.sh
```
No Windows sem `sh`: baixe https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
e salve em `app/src/main/assets/face_landmarker.task`.

## 4. Rodar
Só a malha:
```
python tools/pc_prototype/compare_swap.py --video meu_clipe.mp4 --photo minha_foto.jpg --out saida --i-have-consent
```
Com o inswapper (baixe o `inswapper_128.onnx` ou a versão `fp16`, de ~277 MB, por sua conta):
```
python tools/pc_prototype/compare_swap.py --video meu_clipe.mp4 --photo minha_foto.jpg --out saida ^
       --inswapper C:\caminho\inswapper_128_fp16.onnx --i-have-consent
```
(no Linux use `\` no lugar de `^`)

Saída em `saida/`: `mesh.mp4`, `inswapper.mp4`, `compare_XX.png` (original | malha | inswapper) e `report.txt` (tempo por quadro).
Na primeira execução com `--inswapper`, o InsightFace baixa sozinho o pacote de detecção `buffalo_l` (~280 MB; também de uso não comercial).

## O que olhar
- **Naturalidade**: bordas, tom de pele, boca e olhos acompanhando o vídeo.
- **Tempo por quadro**: o inswapper em CPU de PC já é bem mais lento que a malha; no celular seria pior.
- **Falhas**: rosto de lado, pequeno, coberto ou com vários rostos.

## Estado de verificação
- Parte da **malha**: testada de ponta a ponta (vídeo sintético com movimento, MediaPipe real, biblioteca compilada): 34/36 quadros trocados, ~40 ms/quadro.
- Parte do **inswapper**: escrita com a API padrão do InsightFace, mas **não executada** (o modelo não pôde ser baixado/testado no ambiente de desenvolvimento).
